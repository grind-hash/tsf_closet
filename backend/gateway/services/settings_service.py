from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..consts.history_lookback import (
    HISTORY_LOOKBACK_DEFAULT,
    HISTORY_LOOKBACK_MAX,
    HISTORY_LOOKBACK_MIN,
)
from ..consts.language import DEFAULT_LANGUAGE, normalize_language
from ..databases.base import async_session_factory
from ..databases.models import User

DEFAULT_USER_ID = "default-user"

logger = logging.getLogger(__name__)


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

    def get_history_lookback_count(self, session_id: str = "default") -> int:
        """Return the per-session history lookback count, clamped to [MIN, MAX].

        Falls back to HISTORY_LOOKBACK_DEFAULT when the session has no
        explicit value (e.g. legacy sessions or in-memory store reset).
        """
        current = self._current_settings.get(session_id)
        if current is None:
            return HISTORY_LOOKBACK_DEFAULT
        value = getattr(current, "history_lookback_count", HISTORY_LOOKBACK_DEFAULT)
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return HISTORY_LOOKBACK_DEFAULT
        if ivalue < HISTORY_LOOKBACK_MIN:
            return HISTORY_LOOKBACK_MIN
        if ivalue > HISTORY_LOOKBACK_MAX:
            return HISTORY_LOOKBACK_MAX
        return ivalue

    @staticmethod
    def _default_user_settings() -> dict:
        return {
            "nsfw_mode": False,
            "difficulty": "normal",
            "language": DEFAULT_LANGUAGE,
            "novelai_text_model": "glm-4-6",
        }

    @staticmethod
    def _serialize_user_settings(user: User) -> dict:
        return {
            "nsfw_mode": bool(user.nsfw_mode),
            "difficulty": user.difficulty or "normal",
            "language": normalize_language(user.language),
            "novelai_text_model": user.novelai_text_model or "glm-4-6",
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
        novelai_text_model: str | None = None,
    ) -> dict:
        has_updates = any(
            value is not None
            for value in (nsfw_mode, difficulty, language, novelai_text_model)
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
            if novelai_text_model is not None:
                user.novelai_text_model = novelai_text_model

            if has_updates:
                await session.commit()

            return self._serialize_user_settings(user)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.utcnow().isoformat()

    async def get_self_profile(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Return the parsed self_profile_json for the given user, or None."""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.self_profile_json:
                return None
            try:
                return json.loads(user.self_profile_json)
            except (json.JSONDecodeError, TypeError):
                return None

    async def generate_self_profile(self, input_text: str) -> dict:
        """Generate a SelfProfile JSON from free-form user text via LLM (R-008).

        Args:
            input_text: User's self-introduction or personality description

        Returns:
            Parsed SelfProfile dict

        Raises:
            ValueError: If LLM output is not valid JSON
        """
        from .self_mode_prompts import build_self_profile_generation_prompt
        from .llm_service import llm_service

        system_prompt, user_prompt = build_self_profile_generation_prompt(input_text)
        result = await llm_service.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # Parse the JSON output from LLM
        raw = result.content.strip()
        # Handle markdown code blocks
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first and last lines (``` markers)
            lines = [line for line in lines if not line.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        try:
            profile = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("LLM returned invalid JSON for profile generation: %s", raw)
            raise ValueError(f"Failed to parse generated profile: {e}") from e

        # Attach raw_input for traceability
        profile["raw_input"] = input_text[:1000]
        return profile

    async def save_self_profile(
        self,
        profile: dict,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        """Save a SelfProfile JSON to the user record.

        Args:
            profile: SelfProfile dict to persist
            user_id: User identifier

        Returns:
            The saved profile dict
        """
        profile_json = json.dumps(profile, ensure_ascii=False)

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    id=user_id,
                    nsfw_mode=0,
                    difficulty="normal",
                    language=DEFAULT_LANGUAGE,
                    self_profile_json=profile_json,
                )
                session.add(user)
            else:
                user.self_profile_json = profile_json

            await session.commit()

        logger.info("Saved self profile for user %s", user_id)
        return profile


settings_service = SettingsService()
