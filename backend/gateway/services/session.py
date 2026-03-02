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
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, delete, desc, exists, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..settings.config import settings
from ..databases.base import async_session_factory
from ..databases.models import (
    AchievedEnding as AchievedEndingORM,
    Conversation as ConversationORM,
    History as HistoryORM,
    Session as SessionORM,
    SessionAttribute as SessionAttributeORM,
    SessionStats as SessionStatsORM,
    TransformationTag as TransformationTagORM,
)
from ..models import (
    AchievedEnding,
    Character,
    ConversationMessage,
    ConversationMessageResponse,
    HistoryItem,
    PersistedHistory,
    PersistedSession,
    SessionAttributeResponse,
    SessionResponse,
    SessionStats,
    SessionStatsResponse,
    TransformationTag,
)
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

        await self._cleanup_old_history(session_id)

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
        """API用のセッションレスポンスを取得"""
        session = await self.get_session_with_history(session_id)
        if session is None:
            return None

        current_image_url = ""
        if session.history:
            selected_history = None
            for history_item in session.history:
                if history_item.image_path == session.current_image_path:
                    selected_history = history_item
                    break

            if selected_history:
                current_image_url = f"/history/images/{selected_history.id}"
            else:
                current_image_url = f"/history/images/{session.history[-1].id}"
        elif session.current_image_path:
            current_image_url = f"/game/session/image/{session.id}"

        history_items = []
        for history_item in session.history:
            tag = await self.get_transformation_tag(history_item.id)
            # Build surroundings image URL if path exists
            surroundings_url = None
            if history_item.surroundings_image_path:
                surroundings_url = f"/history/surroundings/{history_item.id}"
            history_items.append(
                HistoryItem(
                    id=history_item.id,
                    instruction=history_item.instruction,
                    image_url=f"/history/images/{history_item.id}",
                    feeling_text=history_item.feeling_text or "",
                    before_description=history_item.before_description or "",
                    after_description=history_item.after_description or "",
                    timestamp=history_item.created_at.isoformat(),
                    instruction_type=history_item.instruction_type,
                    costume_category=tag.costume_category if tag else None,
                    exposure_level=tag.exposure_level if tag else None,
                    age_impression=tag.age_impression if tag else None,
                    seed=history_item.seed,
                    surroundings_image_url=surroundings_url,
                )
            )

        stats = await self.get_session_stats(session_id)
        stats_response = None
        if stats:
            stats.enable_prompt_preview = settings.enable_prompt_preview
            stats_response = SessionStatsResponse(
                bloom=stats.bloom,
                shame=stats.shame,
                adaptation=stats.adaptation,
                passed_critical_points=stats.passed_critical_points,
                difficulty=stats.difficulty,
                nsfw_mode=stats.nsfw_mode,
                enable_prompt_preview=stats.enable_prompt_preview,
            )

        attributes_raw = await self.get_session_attributes(session_id)
        attributes = [
            SessionAttributeResponse(
                id=attr["id"],
                text=attr["attribute_text"],
            )
            for attr in attributes_raw
        ]

        conversations = await self.get_conversation_history(session_id)
        conversation_history = [
            ConversationMessageResponse(
                id=conv.id,
                role=conv.role,
                content=conv.content,
                created_at=conv.created_at,
                instruction_type=conv.instruction_type,
            )
            for conv in conversations
        ]

        return SessionResponse(
            session_id=session.id,
            character_id=session.character_id,
            current_image_url=current_image_url,
            transformation_count=session.transformation_count,
            history=history_items,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            stats=stats_response,
            attributes=attributes,
            conversation_history=conversation_history,
            self_mode=session.self_mode,
        )

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
        now = datetime.now(timezone.utc)
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
        """会話履歴を取得"""
        async with async_session_factory() as db_session:
            stmt = (
                select(ConversationORM)
                .where(ConversationORM.session_id == session_id)
                .order_by(ConversationORM.created_at.asc(), ConversationORM.id.asc())
                .limit(limit)
            )
            rows = (await db_session.execute(stmt)).scalars().all()
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
            created_at 降順（新しい順）で最大 limit 件。
        """
        async with async_session_factory() as db_session:
            # 履歴テーブル: 着替・現実改変・行動
            h_stmt = select(
                HistoryORM.instruction_type,
                HistoryORM.instruction,
                HistoryORM.created_at,
            ).where(HistoryORM.session_id == session_id)
            h_rows = (await db_session.execute(h_stmt)).all()

            # 会話テーブル: ユーザー発言のみ
            c_stmt = select(
                ConversationORM.instruction_type,
                ConversationORM.content,
                ConversationORM.created_at,
            ).where(
                ConversationORM.session_id == session_id,
                ConversationORM.role == "user",
            )
            c_rows = (await db_session.execute(c_stmt)).all()

        # created_at 降順でマージソート（新しい順）
        merged = [(r[0] or "unknown", r[1], r[2]) for r in h_rows] + [
            (r[0] or "conversation", r[1], r[2]) for r in c_rows
        ]
        merged.sort(key=lambda x: x[2], reverse=True)
        # (type, text) タプルを最大 limit 件返す
        return [(m[0], m[1]) for m in merged[:limit]]

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


class SessionStore:
    """後方互換性のためのラッパー (非推奨)

    新しいコードは DatabaseSessionStore を直接使用してください。
    """

    def __init__(self) -> None:
        from ..models import GameSession as GameSessionModel

        self._sessions: dict[str, "GameSessionModel"] = {}  # type: ignore[type-arg]

    def get(self, session_id: str) -> "object | None":
        return self._sessions.get(session_id)

    def create(
        self,
        image: bytes,
        character_id: str | None = None,
        character: "Character | None" = None,
    ) -> object:
        from ..models import GameSession as GameSessionModel

        session = GameSessionModel(
            character_id=character_id,
            character=character,
            current_image=image,
        )
        self._sessions[session.session_id] = session
        return session

    def update(self, session: object) -> None:
        session_id = getattr(session, "session_id", None)
        if session_id and session_id in self._sessions:
            self._sessions[session_id] = session  # type: ignore[assignment]

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
