from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..consts.language import DEFAULT_LANGUAGE, normalize_language
from ..databases.base import async_session_factory
from ..databases.models import User

DEFAULT_USER_ID = "default-user"


class SettingsService:
    def __init__(self) -> None:
        self._current_settings: dict[str, object] = {}

    def get_settings_for_session(
        self, session_id: str, settings_model_cls: type
    ) -> object:
        if session_id not in self._current_settings:
            self._current_settings[session_id] = settings_model_cls()
        return self._current_settings[session_id]

    def update_settings_for_session(
        self,
        session_id: str,
        updates: object,
        settings_model_cls: type,
        inpaint_model_cls: type,
        change_model_cls: type,
    ) -> object:
        current = self.get_settings_for_session(session_id, settings_model_cls)
        update_data = updates.model_dump(exclude_none=True)

        for key, value in update_data.items():
            if hasattr(current, key):
                if key == "inpaint_settings" and isinstance(value, dict):
                    setattr(current, key, inpaint_model_cls(**value))
                elif key == "change_settings" and isinstance(value, dict):
                    setattr(current, key, change_model_cls(**value))
                else:
                    setattr(current, key, value)

        self._current_settings[session_id] = current
        return current

    def reset_settings_for_session(self, session_id: str) -> dict[str, str]:
        if session_id in self._current_settings:
            del self._current_settings[session_id]

        return {"message": "Settings reset to defaults", "session_id": session_id}

    @staticmethod
    def _default_user_settings() -> dict:
        return {
            "nsfw_mode": False,
            "difficulty": "normal",
            "language": DEFAULT_LANGUAGE,
        }

    @staticmethod
    def _serialize_user_settings(user: User) -> dict:
        return {
            "nsfw_mode": bool(user.nsfw_mode),
            "difficulty": user.difficulty or "normal",
            "language": normalize_language(user.language),
        }

    async def _get_user_settings_with_session(
        self,
        user_id: str,
        session: AsyncSession,
    ) -> dict:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return self._default_user_settings()
        return self._serialize_user_settings(user)

    async def get_user_settings(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        async with async_session_factory() as session:
            return await self._get_user_settings_with_session(user_id, session)

    async def update_user_settings(
        self,
        user_id: str = DEFAULT_USER_ID,
        nsfw_mode: bool | None = None,
        difficulty: str | None = None,
        language: str | None = None,
    ) -> dict:
        has_updates = any(
            value is not None for value in (nsfw_mode, difficulty, language)
        )

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user is None and not has_updates:
                return self._default_user_settings()

            if user is None:
                user = User(
                    id=user_id,
                    nsfw_mode=0,
                    difficulty="normal",
                    language=DEFAULT_LANGUAGE,
                )
                session.add(user)

            if nsfw_mode is not None:
                user.nsfw_mode = 1 if nsfw_mode else 0
            if difficulty is not None:
                user.difficulty = difficulty
            if language is not None:
                user.language = normalize_language(language)

            if has_updates:
                await session.commit()

            return self._serialize_user_settings(user)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.utcnow().isoformat()


settings_service = SettingsService()
