"""
セッション管理

SQLiteでゲームセッションと履歴を永続化するストア。
変身回数の追跡、履歴からのベース画像選択、50件上限削除をサポート。
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .database import get_connection
from .models import (
    AchievedEnding,
    Character,
    ConversationMessage,
    HistoryItem,
    PersistedHistory,
    PersistedSession,
    SessionResponse,
    SessionStats,
    TransformationTag,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default-user"


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
        # ディレクトリ作成
        self._history_images_dir.mkdir(parents=True, exist_ok=True)

    async def get_active_session(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> PersistedSession | None:
        """アクティブなセッションを取得

        Args:
            user_id: ユーザーID

        Returns:
            アクティブなセッション、なければNone
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, user_id, character_id, current_image_path,
                   transformation_count, is_active, created_at, updated_at
            FROM sessions
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PersistedSession.from_row(dict(row))

    async def get_session_by_id(
        self,
        session_id: str,
    ) -> PersistedSession | None:
        """セッションIDで取得

        Args:
            session_id: セッションID

        Returns:
            セッション、なければNone
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, user_id, character_id, current_image_path,
                   transformation_count, is_active, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PersistedSession.from_row(dict(row))

    async def create_session(
        self,
        image_path: str,
        character_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> PersistedSession:
        """新しいセッションを作成

        Args:
            image_path: 初期画像のパス
            character_id: キャラクターID
            user_id: ユーザーID

        Returns:
            作成されたセッション
        """
        conn = await get_connection()
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        await conn.execute(
            """
            INSERT INTO sessions (id, user_id, character_id, current_image_path,
                                  transformation_count, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, 1, ?, ?)
            """,
            (session_id, user_id, character_id, image_path, now, now),
        )
        await conn.commit()

        return PersistedSession(
            id=session_id,
            user_id=user_id,
            character_id=character_id,
            current_image_path=image_path,
            transformation_count=0,
            is_active=True,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
        )

    async def update_session(
        self,
        session_id: str,
        current_image_path: str | None = None,
        transformation_count: int | None = None,
    ) -> None:
        """セッションを更新

        Args:
            session_id: セッションID
            current_image_path: 新しい画像パス
            transformation_count: 新しい変身回数
        """
        conn = await get_connection()
        now = datetime.now().isoformat()

        updates = ["updated_at = ?"]
        params: list = [now]

        if current_image_path is not None:
            updates.append("current_image_path = ?")
            params.append(current_image_path)
        if transformation_count is not None:
            updates.append("transformation_count = ?")
            params.append(transformation_count)

        params.append(session_id)

        await conn.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await conn.commit()

    async def reset_session(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        """セッションをリセット (非アクティブ化)

        Args:
            user_id: ユーザーID

        Returns:
            リセットしたセッションがあればTrue
        """
        conn = await get_connection()
        now = datetime.now().isoformat()

        result = await conn.execute(
            """
            UPDATE sessions
            SET is_active = 0, updated_at = ?
            WHERE user_id = ? AND is_active = 1
            """,
            (now, user_id),
        )
        await conn.commit()
        return result.rowcount > 0

    async def increment_transformation_count(
        self,
        session_id: str,
    ) -> int:
        """変身回数をインクリメント

        Args:
            session_id: セッションID

        Returns:
            インクリメント後の変身回数
        """
        conn = await get_connection()
        now = datetime.now().isoformat()

        await conn.execute(
            """
            UPDATE sessions
            SET transformation_count = transformation_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (now, session_id),
        )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT transformation_count FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        return row["transformation_count"] if row else 0

    async def add_history(
        self,
        session_id: str,
        instruction: str,
        image_data: bytes,
        feeling_text: str | None = None,
        before_description: str | None = None,
        after_description: str | None = None,
    ) -> PersistedHistory:
        """履歴を追加

        Args:
            session_id: セッションID
            instruction: 変身指示
            image_data: 画像バイナリ
            feeling_text: 心境テキスト
            before_description: 変身前説明
            after_description: 変身後説明

        Returns:
            作成された履歴
        """
        conn = await get_connection()
        history_id = str(uuid.uuid4())
        now = datetime.now()

        # 画像をファイルに保存
        image_filename = f"{history_id}.png"
        image_path = self._history_images_dir / image_filename
        image_path.write_bytes(image_data)
        relative_path = str(image_path.relative_to(settings.history_images_dir.parent))

        await conn.execute(
            """
            INSERT INTO history (id, session_id, instruction, image_path,
                                feeling_text, before_description, after_description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                session_id,
                instruction,
                relative_path,
                feeling_text,
                before_description,
                after_description,
                now.isoformat(),
            ),
        )
        await conn.commit()

        # 履歴上限を超えた分を削除
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
        )

    async def get_history(
        self,
        session_id: str,
    ) -> list[PersistedHistory]:
        """セッションの履歴を取得

        Args:
            session_id: セッションID

        Returns:
            履歴リスト (古い順)
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, session_id, instruction, image_path, feeling_text,
                   before_description, after_description, created_at
            FROM history
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [PersistedHistory.from_row(dict(row)) for row in rows]

    async def get_history_by_id(
        self,
        history_id: str,
    ) -> PersistedHistory | None:
        """履歴IDで取得

        Args:
            history_id: 履歴ID

        Returns:
            履歴、なければNone
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, session_id, instruction, image_path, feeling_text,
                   before_description, after_description, created_at
            FROM history
            WHERE id = ?
            """,
            (history_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return PersistedHistory.from_row(dict(row))

    async def select_history_as_base(
        self,
        history_id: str,
    ) -> str | None:
        """履歴の画像をベース画像として選択

        Args:
            history_id: 履歴ID

        Returns:
            画像パス、見つからなければNone
        """
        history = await self.get_history_by_id(history_id)
        if history is None:
            return None

        # セッションのcurrent_image_pathを更新
        await self.update_session(
            session_id=history.session_id,
            current_image_path=history.image_path,
        )
        return history.image_path

    async def get_session_with_history(
        self,
        session_id: str,
    ) -> PersistedSession | None:
        """セッションと履歴を一緒に取得

        Args:
            session_id: セッションID

        Returns:
            履歴付きセッション
        """
        session = await self.get_session_by_id(session_id)
        if session is None:
            return None
        session.history = await self.get_history(session_id)
        return session

    async def get_full_session_response(
        self,
        session_id: str,
    ) -> SessionResponse | None:
        """API用のセッションレスポンスを取得

        Args:
            session_id: セッションID

        Returns:
            SessionResponse、なければNone
        """
        session = await self.get_session_with_history(session_id)
        if session is None:
            return None

        # 現在の画像URLを生成（履歴IDから）
        current_image_url = ""
        if session.history:
            # 最新の履歴の画像URLを使用
            current_image_url = f"/history/images/{session.history[-1].id}"
        elif session.current_image_path:
            # 履歴がない場合はキャラクター画像のパスを使用
            # /characters/image/{session_id} エンドポイントで配信
            current_image_url = f"/game/character-image/{session.id}"

        # 履歴をAPIモデルに変換（画像はURLのみ）
        history_items = []
        for h in session.history:
            # T025: タグ情報を取得
            tag = await self.get_transformation_tag(h.id)

            history_items.append(
                HistoryItem(
                    id=h.id,
                    instruction=h.instruction,
                    image_url=f"/history/images/{h.id}",
                    feeling_text=h.feeling_text or "",
                    before_description=h.before_description or "",
                    after_description=h.after_description or "",
                    timestamp=h.created_at.isoformat(),
                    costume_category=tag.costume_category if tag else None,
                    sparkle_level=tag.sparkle_level if tag else None,
                    age_impression=tag.age_impression if tag else None,
                )
            )

        # statsを取得
        stats = await self.get_session_stats(session_id)
        stats_dict = None
        if stats:
            stats_dict = {
                "excitement": stats.excitement,
                "immersion": stats.immersion,
                "challenge": stats.challenge,
            }

        return SessionResponse(
            session_id=session.id,
            character_id=session.character_id,
            current_image_url=current_image_url,
            transformation_count=session.transformation_count,
            history=history_items,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            stats=stats_dict,
        )

    async def _cleanup_old_history(
        self,
        session_id: str,
    ) -> int:
        """古い履歴を削除 (上限50件)

        Args:
            session_id: セッションID

        Returns:
            削除した件数
        """
        conn = await get_connection()

        # 削除対象を取得
        cursor = await conn.execute(
            """
            SELECT id, image_path FROM history
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT -1 OFFSET ?
            """,
            (session_id, self._history_max_count),
        )
        rows = await cursor.fetchall()

        if not rows:
            return 0

        # 画像ファイルを削除
        for row in rows:
            image_path = settings.history_images_dir.parent / row["image_path"]
            if image_path.exists():
                try:
                    os.remove(image_path)
                except OSError as e:
                    logger.warning(f"Failed to delete image {image_path}: {e}")

        # DB から削除
        ids_to_delete = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(ids_to_delete))
        await conn.execute(
            f"DELETE FROM history WHERE id IN ({placeholders})",
            ids_to_delete,
        )
        await conn.commit()

        logger.info(
            f"Cleaned up {len(rows)} old history entries for session {session_id}"
        )
        return len(rows)

    def get_history_image_path(
        self,
        history_id: str,
    ) -> Path:
        """履歴画像のファイルパスを取得

        Args:
            history_id: 履歴ID

        Returns:
            画像ファイルパス
        """
        return self._history_images_dir / f"{history_id}.png"

    # =========================================================================
    # SessionStats 管理 (T013, T014)
    # =========================================================================

    async def get_session_stats(
        self,
        session_id: str,
    ) -> SessionStats | None:
        """セッション統計を取得

        Args:
            session_id: セッションID

        Returns:
            セッション統計、なければNone
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT session_id, excitement, immersion, challenge,
                   passed_critical_points, difficulty
            FROM session_stats
            WHERE session_id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return SessionStats.from_row(dict(row))

    async def create_session_stats(
        self,
        session_id: str,
        difficulty: str = "normal",
    ) -> SessionStats:
        """セッション統計を作成

        Args:
            session_id: セッションID
            difficulty: 難易度

        Returns:
            作成されたセッション統計
        """
        import json as json_module

        stats = SessionStats.create_with_difficulty(session_id, difficulty)
        conn = await get_connection()

        await conn.execute(
            """
            INSERT INTO session_stats
                (session_id, excitement, immersion, challenge, passed_critical_points, difficulty)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                stats.excitement,
                stats.immersion,
                stats.challenge,
                json_module.dumps(stats.passed_critical_points),
                stats.difficulty,
            ),
        )
        await conn.commit()
        return stats

    async def update_session_stats(
        self,
        stats: SessionStats,
    ) -> None:
        """セッション統計を更新

        Args:
            stats: 更新するセッション統計
        """
        import json as json_module

        conn = await get_connection()
        await conn.execute(
            """
            UPDATE session_stats
            SET excitement = ?, immersion = ?, challenge = ?,
                passed_critical_points = ?, difficulty = ?
            WHERE session_id = ?
            """,
            (
                stats.excitement,
                stats.immersion,
                stats.challenge,
                json_module.dumps(stats.passed_critical_points),
                stats.difficulty,
                stats.session_id,
            ),
        )
        await conn.commit()

    async def get_or_create_session_stats(
        self,
        session_id: str,
        difficulty: str = "normal",
    ) -> SessionStats:
        """セッション統計を取得、なければ作成

        Args:
            session_id: セッションID
            difficulty: 難易度（新規作成時のみ使用）

        Returns:
            セッション統計
        """
        stats = await self.get_session_stats(session_id)
        if stats is None:
            stats = await self.create_session_stats(session_id, difficulty)
        return stats

    # =========================================================================
    # TransformationTag 管理 (T022)
    # =========================================================================

    async def save_transformation_tag(
        self,
        history_id: str,
        costume_category: str,
        sparkle_level: str,
        age_impression: str,
    ) -> TransformationTag:
        """変身タグを保存

        Args:
            history_id: 履歴ID
            costume_category: 衣装カテゴリ
            sparkle_level: きらめき度
            age_impression: 年齢印象

        Returns:
            保存された変身タグ
        """
        conn = await get_connection()
        await conn.execute(
            """
            INSERT INTO transformation_tags
                (history_id, costume_category, sparkle_level, age_impression)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(history_id) DO UPDATE SET
                costume_category = excluded.costume_category,
                sparkle_level = excluded.sparkle_level,
                age_impression = excluded.age_impression
            """,
            (history_id, costume_category, sparkle_level, age_impression),
        )
        await conn.commit()

        return TransformationTag(
            history_id=history_id,
            costume_category=costume_category,
            sparkle_level=sparkle_level,
            age_impression=age_impression,
        )

    async def get_transformation_tag(
        self,
        history_id: str,
    ) -> TransformationTag | None:
        """変身タグを取得

        Args:
            history_id: 履歴ID

        Returns:
            変身タグ、なければNone
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT history_id, costume_category, sparkle_level, age_impression
            FROM transformation_tags
            WHERE history_id = ?
            """,
            (history_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return TransformationTag.from_row(dict(row))

    async def get_session_tag_counts(
        self,
        session_id: str,
    ) -> dict[str, int]:
        """セッション内のタグカテゴリ別カウントを取得

        Args:
            session_id: セッションID

        Returns:
            カテゴリ別カウント辞書
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT t.costume_category, COUNT(*) as count
            FROM transformation_tags t
            JOIN history h ON t.history_id = h.id
            WHERE h.session_id = ?
            GROUP BY t.costume_category
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
        return {row["costume_category"]: row["count"] for row in rows}

    # =========================================================================
    # AchievedEnding 管理 (T047)
    # =========================================================================

    async def save_achieved_ending(
        self,
        ending_id: str,
        session_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> AchievedEnding:
        """達成エンディングを保存する

        Args:
            ending_id: エンディングID
            session_id: セッションID
            user_id: ユーザーID

        Returns:
            保存されたAchievedEnding
        """
        conn = await get_connection()
        now = datetime.now(timezone.utc).isoformat()

        await conn.execute(
            """
            INSERT OR IGNORE INTO achieved_endings (
                ending_id, session_id, user_id, achieved_at
            ) VALUES (?, ?, ?, ?)
            """,
            (ending_id, session_id, user_id, now),
        )
        await conn.commit()

        return AchievedEnding(
            ending_id=ending_id,
            session_id=session_id,
            achieved_at=now,
        )

    async def get_achieved_endings(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> list[AchievedEnding]:
        """ユーザーの達成エンディング一覧を取得

        Args:
            user_id: ユーザーID

        Returns:
            達成エンディングリスト
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT ending_id, session_id, achieved_at
            FROM achieved_endings
            WHERE user_id = ?
            ORDER BY achieved_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [AchievedEnding.from_row(row) for row in rows]

    async def get_achieved_ending_ids(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> list[str]:
        """ユーザーの達成エンディングIDリストを取得

        Args:
            user_id: ユーザーID

        Returns:
            達成エンディングIDリスト
        """
        endings = await self.get_achieved_endings(user_id)
        return [e.ending_id for e in endings]

    # =========================================================================
    # 会話メッセージ管理 (Conversation)
    # =========================================================================

    async def add_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> ConversationMessage:
        """会話メッセージを追加

        Args:
            session_id: セッションID
            role: 発言者 ("user" or "character")
            content: メッセージ内容

        Returns:
            作成された会話メッセージ
        """
        conn = await get_connection()
        message_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        await conn.execute(
            """
            INSERT INTO conversation (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, now),
        )
        await conn.commit()

        return ConversationMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        """会話履歴を取得

        Args:
            session_id: セッションID
            limit: 取得件数上限

        Returns:
            会話メッセージリスト (古い順)
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM conversation
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [ConversationMessage.from_row(dict(row)) for row in rows]

    async def clear_conversation(
        self,
        session_id: str,
    ) -> int:
        """会話履歴をクリア

        Args:
            session_id: セッションID

        Returns:
            削除した件数
        """
        conn = await get_connection()
        result = await conn.execute(
            "DELETE FROM conversation WHERE session_id = ?",
            (session_id,),
        )
        await conn.commit()
        return result.rowcount

    # =========================================================================
    # セッション属性管理 (カスタム属性付与機能)
    # =========================================================================

    async def add_session_attribute(
        self,
        session_id: str,
        attribute_text: str,
    ) -> dict:
        """セッションに属性を追加

        Args:
            session_id: セッションID
            attribute_text: 属性テキスト

        Returns:
            作成された属性 {id, attribute_text, created_at}
        """
        conn = await get_connection()
        attribute_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        await conn.execute(
            """
            INSERT INTO session_attributes (id, session_id, attribute_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (attribute_id, session_id, attribute_text, now),
        )
        await conn.commit()

        return {
            "id": attribute_id,
            "attribute_text": attribute_text,
            "created_at": now,
        }

    async def remove_session_attribute(
        self,
        attribute_id: str,
    ) -> bool:
        """属性を削除

        Args:
            attribute_id: 属性ID

        Returns:
            削除成功したかどうか
        """
        conn = await get_connection()
        result = await conn.execute(
            "DELETE FROM session_attributes WHERE id = ?",
            (attribute_id,),
        )
        await conn.commit()
        return result.rowcount > 0

    async def get_session_attributes(
        self,
        session_id: str,
    ) -> list[dict]:
        """セッションの属性一覧を取得

        Args:
            session_id: セッションID

        Returns:
            属性リスト [{id, attribute_text, created_at}, ...]
        """
        conn = await get_connection()
        cursor = await conn.execute(
            """
            SELECT id, attribute_text, created_at
            FROM session_attributes
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "attribute_text": row["attribute_text"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def get_session_attribute_texts(
        self,
        session_id: str,
    ) -> list[str]:
        """セッションの属性テキストのみを取得

        Args:
            session_id: セッションID

        Returns:
            属性テキストリスト
        """
        attrs = await self.get_session_attributes(session_id)
        return [a["attribute_text"] for a in attrs]


# グローバルセッションストアインスタンス
session_store = DatabaseSessionStore()


# 後方互換性のためのエイリアス
# 既存のインメモリ GameSession/Character を使う既存コードとの互換
class SessionStore:
    """後方互換性のためのラッパー (非推奨)

    新しいコードは DatabaseSessionStore を直接使用してください。
    """

    def __init__(self) -> None:
        from .models import GameSession as GameSessionModel

        self._sessions: dict[str, "GameSessionModel"] = {}  # type: ignore[type-arg]

    def get(self, session_id: str) -> "object | None":
        return self._sessions.get(session_id)

    def create(
        self,
        image: bytes,
        character_id: str | None = None,
        character: "Character | None" = None,
    ) -> object:
        from .models import GameSession as GameSessionModel

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
