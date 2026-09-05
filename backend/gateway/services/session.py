"""
セッション管理

SQLAlchemy ORMでゲームセッションと履歴を永続化するストア。
変身回数の追跡、履歴からのベース画像選択、50件上限削除をサポート。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, delete, desc, exists, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..databases.base import async_session_factory
from ..databases.models import (
    AchievedEnding as AchievedEndingORM,
)
from ..databases.models import (
    Conversation as ConversationORM,
)
from ..databases.models import (
    History as HistoryORM,
)
from ..databases.models import (
    Session as SessionORM,
)
from ..databases.models import (
    SessionAttribute as SessionAttributeORM,
)
from ..databases.models import (
    SessionStats as SessionStatsORM,
)
from ..databases.models import (
    TransformationTag as TransformationTagORM,
)
from ..databases.parameter_change_log_repo import (
    StatChange,
    insert_change_logs,
)
from ..models import (
    AchievedEnding,
    ConversationMessage,
    PersistedHistory,
    PersistedSession,
    SessionStats,
    TransformationTag,
)
from ..schemas.session import (
    PlayMemoryResponse,
    SessionResponse,
)
from ..settings.config import settings
from . import history_revert_service, session_response
from .image_paths import resolve_stored_image_path
from .settings_service import settings_service

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default-user"


def _to_datetime(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.now()


def _to_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now().isoformat()


class DatabaseSessionStore:
    """SQLiteベースのセッションストア

    セッションと履歴をSQLiteで永続化する。
    画像ファイルはファイルシステムに保存し、パスのみDBに記録。
    """

    def __init__(
        self,
        history_images_dir: Path | None = None,
        history_max_count: int = 50,
    ) -> None:
        """初期化

        Args:
            history_images_dir: 履歴画像の保存先ディレクトリ
            history_max_count: セッション毎の履歴上限数
        """
        self._history_images_dir = history_images_dir or settings.history_images_dir
        self._history_max_count = history_max_count
        self._history_images_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _to_persisted_session(orm_session: SessionORM) -> PersistedSession:
        return PersistedSession(
            id=orm_session.id,
            user_id=orm_session.user_id,
            character_id=orm_session.character_id,
            current_image_path=orm_session.current_image_path,
            transformation_count=orm_session.transformation_count,
            is_active=bool(orm_session.is_active),
            created_at=_to_datetime(orm_session.created_at),
            updated_at=_to_datetime(orm_session.updated_at),
            self_mode=bool(getattr(orm_session, "self_mode", False)),
            play_memory_system_text=orm_session.play_memory_system_text,
            play_memory_user_text=orm_session.play_memory_user_text,
            play_memory_system_enabled=bool(orm_session.play_memory_system_enabled),
            play_memory_user_enabled=bool(orm_session.play_memory_user_enabled),
            play_memory_system_updated_at=orm_session.play_memory_system_updated_at,
        )

    @staticmethod
    def _to_persisted_history(orm_history: HistoryORM) -> PersistedHistory:
        return PersistedHistory(
            id=orm_history.id,
            session_id=orm_history.session_id,
            instruction=orm_history.instruction,
            image_path=orm_history.image_path,
            feeling_text=orm_history.feeling_text,
            before_description=orm_history.before_description,
            after_description=orm_history.after_description,
            created_at=_to_datetime(orm_history.created_at),
            instruction_type=orm_history.instruction_type,
            seed=orm_history.seed,
            surroundings_image_path=orm_history.surroundings_image_path,
        )

    async def get_active_session(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> PersistedSession | None:
        """アクティブなセッションを取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(SessionORM)
                .where(SessionORM.user_id == user_id, SessionORM.is_active.is_(True))
                .order_by(desc(SessionORM.created_at))
                .limit(1)
            )
            orm_session = (await db_session.execute(stmt)).scalars().first()
            if orm_session is None:
                return None
            return self._to_persisted_session(orm_session)

    async def get_all_sessions(
        self,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """過去セッション一覧を取得（最新順）"""
        async with async_session_factory() as db_session:
            count_stmt = (
                select(func.count())
                .select_from(SessionORM)
                .where(SessionORM.user_id == user_id)
            )
            total_count = (await db_session.execute(count_stmt)).scalar_one() or 0

            latest_history_id_subq = (
                select(HistoryORM.id)
                .where(HistoryORM.session_id == SessionORM.id)
                .order_by(desc(HistoryORM.created_at), desc(HistoryORM.id))
                .limit(1)
                .scalar_subquery()
            )

            last_instruction_subq = (
                select(HistoryORM.instruction)
                .where(HistoryORM.session_id == SessionORM.id)
                .order_by(desc(HistoryORM.created_at), desc(HistoryORM.id))
                .limit(1)
                .scalar_subquery()
            )

            stmt = (
                select(
                    SessionORM,
                    last_instruction_subq.label("last_instruction"),
                    latest_history_id_subq.label("last_history_id"),
                )
                .where(SessionORM.user_id == user_id)
                .order_by(desc(SessionORM.updated_at))
                .limit(limit)
                .offset(offset)
            )
            rows = (await db_session.execute(stmt)).all()

            sessions = []
            for orm_session, last_instruction, last_history_id in rows:
                thumbnail_url = None
                if last_history_id:
                    thumbnail_url = f"/history/images/{last_history_id}"
                elif orm_session.current_image_path:
                    thumbnail_url = f"/game/session/image/{orm_session.id}"

                sessions.append(
                    {
                        "session_id": orm_session.id,
                        "character_id": orm_session.character_id,
                        "thumbnail_url": thumbnail_url,
                        "transformation_count": orm_session.transformation_count,
                        "is_active": bool(orm_session.is_active),
                        "created_at": _to_iso(orm_session.created_at),
                        "updated_at": _to_iso(orm_session.updated_at),
                        "last_instruction": last_instruction,
                    }
                )

            return sessions, total_count

    async def get_session_by_id(
        self,
        session_id: str,
    ) -> PersistedSession | None:
        """セッションIDで取得"""
        async with async_session_factory() as db_session:
            stmt = select(SessionORM).where(SessionORM.id == session_id)
            orm_session = (await db_session.execute(stmt)).scalars().first()
            if orm_session is None:
                return None
            return self._to_persisted_session(orm_session)

    async def create_session(
        self,
        image_path: str,
        character_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
        self_mode: bool = False,
    ) -> PersistedSession:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.now()

        async with async_session_factory() as db_session:
            orm_session = SessionORM(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                current_image_path=image_path,
                transformation_count=0,
                is_active=True,
                self_mode=self_mode,
                created_at=now,
                updated_at=now,
            )
            db_session.add(orm_session)
            await db_session.commit()

        return PersistedSession(
            id=session_id,
            user_id=user_id,
            character_id=character_id,
            current_image_path=image_path,
            transformation_count=0,
            is_active=True,
            self_mode=self_mode,
            created_at=now,
            updated_at=now,
        )

    async def update_session(
        self,
        session_id: str,
        current_image_path: str | None = None,
        transformation_count: int | None = None,
    ) -> None:
        """セッションを更新"""
        now = datetime.now()

        update_values: dict[str, object] = {"updated_at": now}
        if current_image_path is not None:
            update_values["current_image_path"] = current_image_path
        if transformation_count is not None:
            update_values["transformation_count"] = transformation_count

        async with async_session_factory() as db_session:
            stmt = (
                update(SessionORM)
                .where(SessionORM.id == session_id)
                .values(**update_values)
            )
            await db_session.execute(stmt)
            await db_session.commit()

    async def get_play_memory(self, session_id: str) -> PlayMemoryResponse | None:
        """セッションのプレイメモを取得する。"""
        session = await self.get_session_by_id(session_id)
        if session is None:
            return None
        return PlayMemoryResponse(
            system_enabled=session.play_memory_system_enabled,
            user_enabled=session.play_memory_user_enabled,
            system_text=session.play_memory_system_text,
            user_text=session.play_memory_user_text,
            system_updated_at=(
                session.play_memory_system_updated_at.isoformat()
                if session.play_memory_system_updated_at
                else None
            ),
        )

    async def update_play_memory(
        self,
        session_id: str,
        *,
        system_enabled: bool | None = None,
        user_enabled: bool | None = None,
        user_text: str | None = None,
        update_user_text: bool = False,
    ) -> PlayMemoryResponse | None:
        """ユーザーが変更可能なプレイメモ設定を更新する。"""
        values: dict[str, object] = {"updated_at": datetime.now()}
        if system_enabled is not None:
            values["play_memory_system_enabled"] = system_enabled
        if user_enabled is not None:
            values["play_memory_user_enabled"] = user_enabled
        if update_user_text:
            values["play_memory_user_text"] = user_text
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                update(SessionORM).where(SessionORM.id == session_id).values(**values)
            )
            await db_session.commit()
            if not result.rowcount:
                return None
        return await self.get_play_memory(session_id)

    async def save_play_memory_system_text(
        self, session_id: str, text: str
    ) -> PlayMemoryResponse | None:
        """自動生成したプレイメモを保存する。"""
        now = datetime.now()
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                update(SessionORM)
                .where(SessionORM.id == session_id)
                .values(
                    play_memory_system_text=text,
                    play_memory_system_updated_at=now,
                    updated_at=now,
                )
            )
            await db_session.commit()
            if not result.rowcount:
                return None
        return await self.get_play_memory(session_id)

    async def copy_play_memory(
        self,
        source_session_id: str,
        target_session_id: str,
    ) -> bool:
        """プレイメモ（自動・ユーザー本文と有効フラグ）を別セッションへコピーする。"""
        source = await self.get_session_by_id(source_session_id)
        if source is None:
            return False
        now = datetime.now()
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                update(SessionORM)
                .where(SessionORM.id == target_session_id)
                .values(
                    play_memory_system_text=source.play_memory_system_text,
                    play_memory_user_text=source.play_memory_user_text,
                    play_memory_system_enabled=source.play_memory_system_enabled,
                    play_memory_user_enabled=source.play_memory_user_enabled,
                    play_memory_system_updated_at=source.play_memory_system_updated_at,
                    updated_at=now,
                )
            )
            await db_session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def update_history_surroundings(
        self,
        history_id: str,
        surroundings_image_path: str,
    ) -> None:
        """履歴の周囲状況画像パスを更新 (US2 用)"""
        async with async_session_factory() as db_session:
            stmt = (
                update(HistoryORM)
                .where(HistoryORM.id == history_id)
                .values(surroundings_image_path=surroundings_image_path)
            )
            await db_session.execute(stmt)
            await db_session.commit()

    async def reset_session(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        """セッションをリセット (非アクティブ化)"""
        now = datetime.now()

        async with async_session_factory() as db_session:
            stmt = (
                update(SessionORM)
                .where(SessionORM.user_id == user_id, SessionORM.is_active.is_(True))
                .values(is_active=False, updated_at=now)
            )
            result = await db_session.execute(stmt)
            await db_session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def activate_session(
        self,
        session_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        """指定したセッションをアクティブに設定"""
        now = datetime.now()

        async with async_session_factory() as db_session:
            deactivate_stmt = (
                update(SessionORM)
                .where(SessionORM.user_id == user_id, SessionORM.is_active.is_(True))
                .values(is_active=False, updated_at=now)
            )
            await db_session.execute(deactivate_stmt)

            activate_stmt = (
                update(SessionORM)
                .where(SessionORM.id == session_id, SessionORM.user_id == user_id)
                .values(is_active=True, updated_at=now)
            )
            result = await db_session.execute(activate_stmt)
            await db_session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def increment_transformation_count(
        self,
        session_id: str,
    ) -> int:
        """変身回数をインクリメント"""
        now = datetime.now()

        async with async_session_factory() as db_session:
            orm_session = (
                (
                    await db_session.execute(
                        select(SessionORM).where(SessionORM.id == session_id).limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if orm_session is None:
                return 0

            orm_session.transformation_count += 1
            orm_session.updated_at = now
            await db_session.commit()
            return orm_session.transformation_count

    async def add_history(
        self,
        session_id: str,
        instruction: str,
        image_data: bytes,
        feeling_text: str | None = None,
        before_description: str | None = None,
        after_description: str | None = None,
        instruction_type: str | None = None,
        seed: int | None = None,
        surroundings_image_path: str | None = None,
    ) -> PersistedHistory:
        """履歴を追加"""
        history_id = str(uuid.uuid4())
        now = datetime.now()

        image_filename = f"{history_id}.png"
        image_path = self._history_images_dir / image_filename
        image_path.write_bytes(image_data)
        relative_path = str(image_path.relative_to(settings.history_images_dir.parent))

        async with async_session_factory() as db_session:
            orm_history = HistoryORM(
                id=history_id,
                session_id=session_id,
                instruction=instruction,
                image_path=relative_path,
                feeling_text=feeling_text,
                before_description=before_description,
                after_description=after_description,
                created_at=now,
                instruction_type=instruction_type,
                seed=seed,
                surroundings_image_path=surroundings_image_path,
            )
            db_session.add(orm_history)
            await db_session.commit()

        # 自動削除は廃止: ユーザーが個別に削除する運用に変更
        # await self._cleanup_old_history(session_id)

        return PersistedHistory(
            id=history_id,
            session_id=session_id,
            instruction=instruction,
            image_path=relative_path,
            feeling_text=feeling_text,
            before_description=before_description,
            after_description=after_description,
            created_at=now,
            instruction_type=instruction_type,
            seed=seed,
            surroundings_image_path=surroundings_image_path,
        )

    async def get_history(
        self,
        session_id: str,
    ) -> list[PersistedHistory]:
        """セッションの履歴を取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(HistoryORM)
                .where(HistoryORM.session_id == session_id)
                .order_by(HistoryORM.created_at.asc(), HistoryORM.id.asc())
            )
            rows = (await db_session.execute(stmt)).scalars().all()
            return [self._to_persisted_history(row) for row in rows]

    async def get_latest_history(
        self,
        session_id: str,
    ) -> PersistedHistory | None:
        """セッションの最新履歴を取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(HistoryORM)
                .where(HistoryORM.session_id == session_id)
                .order_by(HistoryORM.created_at.desc(), HistoryORM.id.desc())
                .limit(1)
            )
            row = (await db_session.execute(stmt)).scalars().first()
            if row is None:
                return None
            return self._to_persisted_history(row)

    async def get_history_by_id(
        self,
        history_id: str,
    ) -> PersistedHistory | None:
        """履歴IDで取得"""
        async with async_session_factory() as db_session:
            row = (
                (
                    await db_session.execute(
                        select(HistoryORM).where(HistoryORM.id == history_id).limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            return self._to_persisted_history(row)

    async def select_history_as_base(
        self,
        history_id: str,
    ) -> str | None:
        """履歴の画像をベース画像として選択"""
        history = await self.get_history_by_id(history_id)
        if history is None:
            return None

        await self.update_session(
            session_id=history.session_id,
            current_image_path=history.image_path,
        )
        return history.image_path

    async def delete_latest_history(
        self,
        session_id: str,
    ) -> dict | None:
        """最新の履歴エントリを削除し、セッションを1つ前の状態に戻す

        実体は history_revert_service。互換のためストアのメソッドとして残す。
        """
        return await history_revert_service.delete_latest_history(session_id)

    async def get_session_with_history(
        self,
        session_id: str,
    ) -> PersistedSession | None:
        """セッションと履歴を一緒に取得"""
        session = await self.get_session_by_id(session_id)
        if session is None:
            return None
        session.history = await self.get_history(session_id)
        return session

    async def get_full_session_response(
        self,
        session_id: str,
    ) -> SessionResponse | None:
        """API用のセッションレスポンスを取得(組立は session_response)"""
        return await session_response.build_session_response(self, session_id)

    async def _cleanup_old_history(
        self,
        session_id: str,
    ) -> int:
        """古い履歴を削除 (上限50件)"""
        async with async_session_factory() as db_session:
            stmt = (
                select(HistoryORM)
                .where(HistoryORM.session_id == session_id)
                .order_by(HistoryORM.created_at.desc(), HistoryORM.id.desc())
                .offset(self._history_max_count)
            )
            rows = (await db_session.execute(stmt)).scalars().all()
            if not rows:
                return 0

            for row in rows:
                image_path = settings.history_images_dir.parent / row.image_path
                if image_path.exists():
                    try:
                        os.remove(image_path)
                    except OSError as exc:
                        logger.warning("Failed to delete image %s: %s", image_path, exc)

            ids_to_delete = [row.id for row in rows]
            await db_session.execute(
                delete(HistoryORM).where(HistoryORM.id.in_(ids_to_delete))
            )
            await db_session.commit()

            logger.info(
                "Cleaned up %s old history entries for session %s",
                len(rows),
                session_id,
            )
            return len(rows)

    def get_history_image_path(
        self,
        history_id: str,
    ) -> Path:
        """履歴画像のファイルパスを取得"""
        return self._history_images_dir / f"{history_id}.png"

    async def get_session_stats(
        self,
        session_id: str,
    ) -> SessionStats | None:
        """セッション統計を取得"""
        async with async_session_factory() as db_session:
            orm_stats = (
                (
                    await db_session.execute(
                        select(SessionStatsORM)
                        .where(SessionStatsORM.session_id == session_id)
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if orm_stats is None:
                return None

            return SessionStats.from_row(
                {
                    "session_id": orm_stats.session_id,
                    "bloom": orm_stats.bloom,
                    "shame": orm_stats.shame,
                    "adaptation": orm_stats.adaptation,
                    "passed_critical_points": orm_stats.passed_critical_points,
                    "difficulty": orm_stats.difficulty,
                    "nsfw_mode": orm_stats.nsfw_mode,
                }
            )

    async def create_session_stats(
        self,
        session_id: str,
        difficulty: str = "normal",
        nsfw_mode: bool = False,
    ) -> SessionStats:
        """セッション統計を作成"""
        stats = SessionStats.create_with_difficulty(session_id, difficulty, nsfw_mode)
        async with async_session_factory() as db_session:
            orm_stats = SessionStatsORM(
                session_id=session_id,
                bloom=stats.bloom,
                shame=stats.shame,
                adaptation=stats.adaptation,
                passed_critical_points=json.dumps(stats.passed_critical_points),
                difficulty=stats.difficulty,
                nsfw_mode=1 if stats.nsfw_mode else 0,
            )
            db_session.add(orm_stats)
            await db_session.commit()
        return stats

    async def update_session_stats(
        self,
        stats: SessionStats,
    ) -> None:
        """セッション統計を更新"""
        async with async_session_factory() as db_session:
            stmt = (
                update(SessionStatsORM)
                .where(SessionStatsORM.session_id == stats.session_id)
                .values(
                    bloom=stats.bloom,
                    shame=stats.shame,
                    adaptation=stats.adaptation,
                    passed_critical_points=json.dumps(stats.passed_critical_points),
                    difficulty=stats.difficulty,
                    nsfw_mode=1 if stats.nsfw_mode else 0,
                )
            )
            await db_session.execute(stmt)
            await db_session.commit()

    async def record_parameter_change_log(
        self,
        session_id: str,
        history_id: str,
        stat_changes: list[StatChange],
        reason: str | None,
    ) -> int:
        """`(session_id, history_id)` 単位で stat 変動ログを記録する.

        Args:
            session_id: 対象セッション ID.
            history_id: 対象 history エントリ ID.
            stat_changes: ``(stat_name, delta, prev_value, new_value)`` のリスト.
                ``delta == 0`` の要素はスキップされる.
            reason: アクション種別 (``dress_up``/``reality_alter``/``action`` 等).

        Returns:
            実際に INSERT された行数.
        """
        async with async_session_factory() as db_session:
            inserted = await insert_change_logs(
                db_session,
                session_id=session_id,
                history_id=history_id,
                stat_changes=stat_changes,
                reason=reason,
            )
            await db_session.commit()
            return inserted

    async def get_or_create_session_stats(
        self,
        session_id: str,
        difficulty: str = "normal",
        nsfw_mode: bool = False,
    ) -> SessionStats:
        """セッション統計を取得、なければ作成"""
        stats = await self.get_session_stats(session_id)
        if stats is None:
            stats = await self.create_session_stats(session_id, difficulty, nsfw_mode)
        return stats

    async def save_transformation_tag(
        self,
        history_id: str,
        costume_category: str,
        exposure_level: str,
        age_impression: str,
    ) -> TransformationTag:
        """変身タグを保存"""
        async with async_session_factory() as db_session:
            stmt = sqlite_insert(TransformationTagORM).values(
                history_id=history_id,
                costume_category=costume_category,
                exposure_level=exposure_level,
                age_impression=age_impression,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[TransformationTagORM.history_id],
                set_={
                    "costume_category": costume_category,
                    "exposure_level": exposure_level,
                    "age_impression": age_impression,
                },
            )
            await db_session.execute(stmt)
            await db_session.commit()

        return TransformationTag(
            history_id=history_id,
            costume_category=costume_category,
            exposure_level=exposure_level,
            age_impression=age_impression,
        )

    async def get_transformation_tag(
        self,
        history_id: str,
    ) -> TransformationTag | None:
        """変身タグを取得"""
        async with async_session_factory() as db_session:
            orm_tag = (
                (
                    await db_session.execute(
                        select(TransformationTagORM)
                        .where(TransformationTagORM.history_id == history_id)
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if orm_tag is None:
                return None
            return TransformationTag(
                history_id=orm_tag.history_id,
                costume_category=orm_tag.costume_category,
                exposure_level=orm_tag.exposure_level,
                age_impression=orm_tag.age_impression,
            )

    async def get_session_tag_counts(
        self,
        session_id: str,
    ) -> dict[str, int]:
        """セッション内のタグカテゴリ別カウントを取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(
                    TransformationTagORM.costume_category, func.count().label("count")
                )
                .join(HistoryORM, TransformationTagORM.history_id == HistoryORM.id)
                .where(HistoryORM.session_id == session_id)
                .group_by(TransformationTagORM.costume_category)
            )
            rows = (await db_session.execute(stmt)).all()
            return {category: count for category, count in rows}

    async def save_achieved_ending(
        self,
        ending_id: str,
        session_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> AchievedEnding:
        """達成エンディングを保存する"""
        now = datetime.now(UTC)
        achieved_ending_id = str(uuid.uuid4())

        async with async_session_factory() as db_session:
            stmt = sqlite_insert(AchievedEndingORM).values(
                id=achieved_ending_id,
                ending_id=ending_id,
                session_id=session_id,
                user_id=user_id,
                achieved_at=now,
            )
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[AchievedEndingORM.user_id, AchievedEndingORM.ending_id]
            )
            await db_session.execute(stmt)
            await db_session.commit()

        return AchievedEnding(
            ending_id=ending_id,
            session_id=session_id,
            achieved_at=now.isoformat(),
        )

    async def get_achieved_endings(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> list[AchievedEnding]:
        """ユーザーの達成エンディング一覧を取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(AchievedEndingORM)
                .where(AchievedEndingORM.user_id == user_id)
                .order_by(desc(AchievedEndingORM.achieved_at))
            )
            rows = (await db_session.execute(stmt)).scalars().all()
            return [
                AchievedEnding(
                    ending_id=row.ending_id,
                    session_id=row.session_id,
                    achieved_at=_to_iso(row.achieved_at),
                )
                for row in rows
            ]

    async def get_achieved_ending_ids(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> list[str]:
        """ユーザーの達成エンディングIDリストを取得"""
        endings = await self.get_achieved_endings(user_id)
        return [ending.ending_id for ending in endings]

    async def has_achieved_ending_for_session(
        self,
        session_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        """指定セッションで既にエンディング達成済みかを判定"""
        async with async_session_factory() as db_session:
            stmt = select(
                exists().where(
                    and_(
                        AchievedEndingORM.session_id == session_id,
                        AchievedEndingORM.user_id == user_id,
                    )
                )
            )
            return bool((await db_session.execute(stmt)).scalar())

    async def add_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
        instruction_type: str | None = None,
        attached_image_url: str | None = None,
        related_history_id: str | None = None,
    ) -> ConversationMessage:
        """会話メッセージを追加"""
        message_id = str(uuid.uuid4())
        now = datetime.now()

        async with async_session_factory() as db_session:
            orm_message = ConversationORM(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                created_at=now,
                instruction_type=instruction_type,
                attached_image_url=attached_image_url,
                related_history_id=related_history_id,
            )
            db_session.add(orm_message)
            await db_session.commit()

        return ConversationMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now.isoformat(),
            instruction_type=instruction_type,
            attached_image_url=attached_image_url,
            related_history_id=related_history_id,
        )

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        """直近の会話履歴を時系列順で取得する。"""
        async with async_session_factory() as db_session:
            stmt = (
                select(ConversationORM)
                .where(ConversationORM.session_id == session_id)
                .order_by(ConversationORM.created_at.desc(), ConversationORM.id.desc())
                .limit(limit)
            )
            rows = (await db_session.execute(stmt)).scalars().all()
            rows.reverse()
            return [
                ConversationMessage(
                    id=row.id,
                    session_id=row.session_id,
                    role=row.role,
                    content=row.content,
                    created_at=_to_iso(row.created_at),
                    instruction_type=row.instruction_type,
                    attached_image_url=row.attached_image_url,
                    related_history_id=row.related_history_id,
                )
                for row in rows
            ]

    async def get_session_timeline(
        self,
        session_id: str,
        limit: int = 30,
    ) -> list[tuple[str, str]]:
        """history + conversation から指示を時系列でマージ取得する。

        Returns:
            (instruction_type, instruction_text) のタプルリスト。
            created_at 昇順（古い順 = 時系列順）で最大 limit 件。
        """
        return await self.get_session_timeline_until(
            session_id,
            until_created_at=None,
            limit=limit,
        )

    async def get_session_timeline_until(
        self,
        session_id: str,
        until_created_at: datetime | None = None,
        limit: int = 30,
    ) -> list[tuple[str, str]]:
        """history + conversation を時系列マージし、任意の時刻以前に制限する。

        Args:
            session_id: 対象セッション
            until_created_at: 指定時はこの時刻以前のみ（分岐点サマリー用）
            limit: 最大件数（古い順の先頭から）

        Returns:
            (instruction_type, instruction_text) のタプルリスト。古い順。
        """
        async with async_session_factory() as db_session:
            h_stmt = select(
                HistoryORM.instruction_type,
                HistoryORM.instruction,
                HistoryORM.created_at,
            ).where(HistoryORM.session_id == session_id)
            if until_created_at is not None:
                h_stmt = h_stmt.where(HistoryORM.created_at <= until_created_at)
            h_rows = (await db_session.execute(h_stmt)).all()

            c_stmt = select(
                ConversationORM.instruction_type,
                ConversationORM.content,
                ConversationORM.created_at,
            ).where(
                ConversationORM.session_id == session_id,
                ConversationORM.role == "user",
            )
            if until_created_at is not None:
                c_stmt = c_stmt.where(ConversationORM.created_at <= until_created_at)
            c_rows = (await db_session.execute(c_stmt)).all()

        merged = [(r[0] or "unknown", r[1], r[2]) for r in h_rows] + [
            (r[0] or "conversation", r[1], r[2]) for r in c_rows
        ]
        merged.sort(key=lambda x: x[2], reverse=False)
        return [(m[0], m[1]) for m in merged[:limit]]

    def resolve_history_image_file(self, history: PersistedHistory) -> Path | None:
        """履歴に紐づく画像ファイルパスを解決する。

        保存されたパス文字列で見つからなければ履歴 ID 由来のファイル名を試す。
        """
        resolved = resolve_stored_image_path(
            history.image_path, history_images_dir=self._history_images_dir
        )
        if resolved is not None:
            return resolved
        fallback = self.get_history_image_path(history.id)
        try:
            return fallback if fallback.is_file() else None
        except OSError:
            return None

    async def reconstruct_stats_at_history(
        self,
        session_id: str,
        history_id: str,
        *,
        difficulty: str = "normal",
        nsfw_mode: bool = False,
    ) -> SessionStats:
        """parameter_change_log から分岐点時点の stats を再構築する。

        実体は history_revert_service。互換のためストアのメソッドとして残す。
        """
        return await history_revert_service.reconstruct_stats_at_history(
            self,
            session_id,
            history_id,
            difficulty=difficulty,
            nsfw_mode=nsfw_mode,
        )

    async def count_transformations_until(
        self,
        session_id: str,
        history_id: str,
    ) -> int:
        """分岐点以前の dress_up / reality_alter 件数を数える。"""
        transform_types = {"dress_up", "reality_alter", "reality"}
        count = 0
        for row in await self.get_history(session_id):
            itype = (row.instruction_type or "").strip()
            if itype in transform_types:
                count += 1
            elif (
                itype == ""
                and row.instruction
                and row.instruction not in ("初期状態", "(初期状態)")
                and not row.instruction.startswith("(")
            ):
                # 古いデータで type が空の変身履歴は件数に含める
                count += 1
            if row.id == history_id:
                break
        return count

    async def get_recent_instructions(
        self,
        session_id: str,
        instruction_types: list[str] | None = None,
        limit: int = 30,
    ) -> list[tuple[str, str]]:
        """history + conversation から直近の指示を取得する（種類フィルタ対応）。

        `get_session_timeline` とは異なり、created_at 降順で直近 `limit` 件を取得した後
        時系列順（古い順）に並び替えて返す。指示テキスト生成機能のように直近の傾向を
        優先したい用途向け。

        Args:
            session_id: セッションID
            instruction_types: 指定時はこの集合の instruction_type のみを対象にする
            limit: 取得件数上限

        Returns:
            (instruction_type, instruction_text) のタプルリスト。古い順に最大 limit 件。
        """
        async with async_session_factory() as db_session:
            h_stmt = select(
                HistoryORM.instruction_type,
                HistoryORM.instruction,
                HistoryORM.created_at,
            ).where(HistoryORM.session_id == session_id)
            h_rows = (await db_session.execute(h_stmt)).all()

            c_stmt = select(
                ConversationORM.instruction_type,
                ConversationORM.content,
                ConversationORM.created_at,
            ).where(
                ConversationORM.session_id == session_id,
                ConversationORM.role == "user",
            )
            c_rows = (await db_session.execute(c_stmt)).all()

        merged = [(r[0] or "unknown", r[1], r[2]) for r in h_rows] + [
            (r[0] or "conversation", r[1], r[2]) for r in c_rows
        ]

        if instruction_types:
            type_set = set(instruction_types)
            merged = [m for m in merged if m[0] in type_set]

        # created_at 降順で直近 limit 件を取り、古い順に戻す
        merged.sort(key=lambda x: x[2], reverse=True)
        recent = merged[:limit]
        recent.reverse()
        return [(m[0], m[1]) for m in recent]

    async def clear_conversation(
        self,
        session_id: str,
    ) -> int:
        """会話履歴をクリア"""
        async with async_session_factory() as db_session:
            stmt = delete(ConversationORM).where(
                ConversationORM.session_id == session_id
            )
            result = await db_session.execute(stmt)
            await db_session.commit()
            return result.rowcount or 0

    async def delete_conversation_by_history_id(
        self,
        session_id: str,
        history_id: str,
    ) -> int:
        """指定した history_id に紐づく会話レコードのみ削除する

        History レコードや画像ファイルは削除しない。
        History.feeling_text もクリアする。

        Returns:
            削除された Conversation レコード数
        """
        async with async_session_factory() as db_session:
            # 対象 History がセッションに属するか確認
            history_row = (
                await db_session.execute(
                    select(HistoryORM.id).where(
                        HistoryORM.id == history_id,
                        HistoryORM.session_id == session_id,
                    )
                )
            ).first()
            if history_row is None:
                return -1  # not found

            # Conversation レコード削除
            result = await db_session.execute(
                delete(ConversationORM).where(
                    ConversationORM.related_history_id == history_id
                )
            )
            deleted_count = result.rowcount or 0

            # History.feeling_text をクリア
            await db_session.execute(
                update(HistoryORM)
                .where(HistoryORM.id == history_id)
                .values(feeling_text=None)
            )

            await db_session.commit()
            return deleted_count

    async def delete_conversation_message(
        self,
        session_id: str,
        conversation_id: str,
    ) -> bool:
        """会話メッセージを1件削除する (conversation.id 直接指定)

        History レコードや画像ファイルは一切触らない。

        Returns:
            削除成功: True, 見つからない: False
        """
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                delete(ConversationORM).where(
                    ConversationORM.id == conversation_id,
                    ConversationORM.session_id == session_id,
                )
            )
            await db_session.commit()
            return (result.rowcount or 0) > 0

    async def delete_history_entry(
        self,
        session_id: str,
        history_id: str,
    ) -> dict | None:
        """指定した history_id の履歴エントリを完全削除する

        実体は history_revert_service。互換のためストアのメソッドとして残す。
        """
        return await history_revert_service.delete_history_entry(session_id, history_id)

    async def add_session_attribute(
        self,
        session_id: str,
        attribute_text: str,
    ) -> dict:
        """セッションに属性を追加"""
        attribute_id = str(uuid.uuid4())
        now = datetime.now()

        async with async_session_factory() as db_session:
            orm_attr = SessionAttributeORM(
                id=attribute_id,
                session_id=session_id,
                attribute_text=attribute_text,
                created_at=now,
            )
            db_session.add(orm_attr)
            await db_session.commit()

        return {
            "id": attribute_id,
            "attribute_text": attribute_text,
            "created_at": now.isoformat(),
        }

    async def remove_session_attribute(
        self,
        attribute_id: str,
    ) -> bool:
        """属性を削除"""
        async with async_session_factory() as db_session:
            stmt = delete(SessionAttributeORM).where(
                SessionAttributeORM.id == attribute_id
            )
            result = await db_session.execute(stmt)
            await db_session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def get_session_attributes(
        self,
        session_id: str,
    ) -> list[dict]:
        """セッションの属性一覧を取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(SessionAttributeORM)
                .where(SessionAttributeORM.session_id == session_id)
                .order_by(
                    SessionAttributeORM.created_at.asc(), SessionAttributeORM.id.asc()
                )
            )
            rows = (await db_session.execute(stmt)).scalars().all()
            return [
                {
                    "id": row.id,
                    "attribute_text": row.attribute_text,
                    "created_at": _to_iso(row.created_at),
                }
                for row in rows
            ]

    async def get_session_attribute_texts(
        self,
        session_id: str,
    ) -> list[str]:
        """セッションの属性テキストのみを取得"""
        attrs = await self.get_session_attributes(session_id)
        return [attr["attribute_text"] for attr in attrs]

    async def get_user_settings(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        """ユーザー設定を取得"""
        return await settings_service.get_user_settings(user_id=user_id)

    async def get_self_profile(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Return the parsed self_profile_json for the given user, or None."""
        return await settings_service.get_self_profile(user_id=user_id)

    async def update_user_settings(
        self,
        user_id: str = DEFAULT_USER_ID,
        nsfw_mode: bool | None = None,
        difficulty: str | None = None,
        language: str | None = None,
    ) -> dict:
        """ユーザー設定を更新"""
        result = await settings_service.update_user_settings(
            user_id=user_id,
            nsfw_mode=nsfw_mode,
            difficulty=difficulty,
            language=language,
        )

        logger.info(
            "User settings updated: user_id=%s, nsfw_mode=%s, difficulty=%s, language=%s",
            user_id,
            nsfw_mode,
            difficulty,
            language,
        )
        return result


session_store = DatabaseSessionStore()
