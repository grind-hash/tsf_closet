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


def _normalize_feeling_mode_value(mode: str | None) -> str:
    """feeling_mode を API 向けに正規化する。"""
    from .gender_congruence import normalize_feeling_mode

    return normalize_feeling_mode(mode)


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
            "bloom_calc_method": "legacy",
            "feeling_mode": "legacy",  # legacy | gender_aware
            "gender_congruence_llm_enabled": False,
            "language": DEFAULT_LANGUAGE,
            "novelai_text_model": "glm-4-6",
            "tts_enabled": False,
            "tts_use_gpu": False,
            "tts_engine_dir": None,
            "tts_model_dir": None,
            "tts_speaker_id": None,
            "tts_style_id": None,
            "tts_output_format": "wav",
        }

    @staticmethod
    def _serialize_user_settings(user: User) -> dict:
        return {
            "nsfw_mode": bool(user.nsfw_mode),
            "difficulty": user.difficulty or "normal",
            "bloom_calc_method": user.bloom_calc_method or "legacy",
            "feeling_mode": _normalize_feeling_mode_value(
                getattr(user, "feeling_mode", None)
            ),
            "gender_congruence_llm_enabled": bool(
                getattr(user, "gender_congruence_llm_enabled", 0)
            ),
            "language": normalize_language(user.language),
            "novelai_text_model": user.novelai_text_model or "glm-4-6",
            "tts_enabled": bool(user.tts_enabled),
            "tts_use_gpu": bool(user.tts_use_gpu),
            "tts_engine_dir": user.tts_engine_dir,
            "tts_model_dir": user.tts_model_dir,
            "tts_speaker_id": user.tts_speaker_id,
            "tts_style_id": user.tts_style_id,
            "tts_output_format": user.tts_output_format or "wav",
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
        bloom_calc_method: str | None = None,
        feeling_mode: str | None = None,
        gender_congruence_llm_enabled: bool | None = None,
        language: str | None = None,
        novelai_text_model: str | None = None,
        tts_enabled: bool | None = None,
        tts_use_gpu: bool | None = None,
        tts_engine_dir: str | None = None,
        tts_model_dir: str | None = None,
        tts_speaker_id: str | None = None,
        tts_style_id: str | None = None,
        tts_output_format: str | None = None,
    ) -> dict:
        has_updates = any(
            value is not None
            for value in (
                nsfw_mode,
                difficulty,
                bloom_calc_method,
                feeling_mode,
                gender_congruence_llm_enabled,
                language,
                novelai_text_model,
                tts_enabled,
                tts_use_gpu,
                tts_engine_dir,
                tts_model_dir,
                tts_speaker_id,
                tts_style_id,
                tts_output_format,
            )
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
                    tts_enabled=0,
                    tts_use_gpu=0,
                    tts_output_format="wav",
                )
                session.add(user)

            if nsfw_mode is not None:
                user.nsfw_mode = 1 if nsfw_mode else 0
            if difficulty is not None:
                user.difficulty = difficulty
            if bloom_calc_method is not None:
                user.bloom_calc_method = bloom_calc_method
            if feeling_mode is not None:
                from .gender_congruence import (
                    VALID_FEELING_MODES,
                    normalize_feeling_mode,
                )

                # new/experimental は誤って保存された別名として受け入れる
                allowed = set(VALID_FEELING_MODES) | {"new", "experimental"}
                if feeling_mode not in allowed:
                    raise ValueError(
                        f"Invalid feeling_mode: {feeling_mode}. "
                        "Use 'legacy' or 'gender_aware'."
                    )
                user.feeling_mode = normalize_feeling_mode(feeling_mode)
            if gender_congruence_llm_enabled is not None:
                user.gender_congruence_llm_enabled = (
                    1 if gender_congruence_llm_enabled else 0
                )
            if language is not None:
                user.language = normalize_language(language)
            if novelai_text_model is not None:
                user.novelai_text_model = novelai_text_model
            if tts_enabled is not None:
                user.tts_enabled = 1 if tts_enabled else 0
            if tts_use_gpu is not None:
                user.tts_use_gpu = 1 if tts_use_gpu else 0
            if tts_engine_dir is not None:
                user.tts_engine_dir = tts_engine_dir.strip() or None
            if tts_model_dir is not None:
                user.tts_model_dir = tts_model_dir.strip() or None
            if tts_speaker_id is not None:
                user.tts_speaker_id = tts_speaker_id.strip() or None
            if tts_style_id is not None:
                user.tts_style_id = tts_style_id.strip() or None
            if tts_output_format is not None:
                user.tts_output_format = tts_output_format

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

    async def get_memory_text(
        self,
        user_id: str = DEFAULT_USER_ID,
    ) -> str | None:
        """Return the stored memory text for the given user, or None."""
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.memory_text:
                return None
            return user.memory_text

    async def save_memory_text(
        self,
        memory_text: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> str:
        """Save the memory text (user preference/kink summary) to the user record.

        Args:
            memory_text: Free-form text describing the user's preferences
            user_id: User identifier

        Returns:
            The saved memory text
        """
        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    id=user_id,
                    nsfw_mode=0,
                    difficulty="normal",
                    language=DEFAULT_LANGUAGE,
                    memory_text=memory_text,
                )
                session.add(user)
            else:
                user.memory_text = memory_text

            await session.commit()

        logger.info(
            "Saved memory text for user %s (%d chars)", user_id, len(memory_text)
        )
        return memory_text


settings_service = SettingsService()
