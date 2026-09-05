"""キャラクターとの会話（通常ゲームのチャット）。

ルーターは入力の受け取りと HTTP / SSE への変換だけを行い、セッション・履歴の
読み込み、プロンプト組み立て、生成、保存、プレイメモ更新はここに置く。
"""

from __future__ import annotations

import logging
import math
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from ..consts.language import normalize_language
from .characters import character_manager
from .conversation import (
    build_conversation_prompt,
    get_fallback_response,
    get_stage_display_name,
    get_stage_name,
    is_response_language_valid,
)
from .custom_sessions import load_custom_session_metadata
from .history_context import resolve_history_lookback_enabled
from .llm_service import llm_service
from .session import session_store
from .settings_service import settings_service

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    """指定されたセッションが存在しない。"""


@dataclass
class ChatContext:
    """1 発言分の会話に必要な、解決済みの状態とプロンプト。"""

    session_id: str
    message: str
    language: str
    use_play_memory: bool
    session: Any
    stats: Any
    pronoun: str
    system_prompt: str
    user_prompt: str
    novelai_text_model: str | None
    # 発言はプロンプト組み立て時に保存済み（過去履歴に含めないため）
    user_conversation_id: str | None


class ConversationService:
    async def generate_with_language_retry(
        self,
        llm_service,
        system_prompt: str,
        user_prompt: str,
        language: str,
        novelai_model_override: str | None = None,
    ) -> str | None:
        current_user_prompt = user_prompt
        for _ in range(2):
            result = await llm_service.generate_feeling(
                system_prompt=system_prompt,
                user_prompt=current_user_prompt,
                novelai_model_override=novelai_model_override,
            )
            candidate = result.content
            if is_response_language_valid(candidate, language):
                return candidate
            current_user_prompt = f"{user_prompt}\n\nIMPORTANT: Respond in {'English only' if language == 'en' else 'Japanese only'}."
        return None

    async def build_chat_context(
        self,
        *,
        session_id: str,
        message: str,
        language: str | None,
        enable_multiple_people: bool,
        use_play_memory: bool,
        use_history_lookback: bool | None,
    ) -> ChatContext:
        """セッションと履歴を読み、プロンプトを組み立て、ユーザー発言を保存する。

        Raises:
            SessionNotFoundError: セッションが無い
        """
        session = await session_store.get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        stats = await session_store.get_session_stats(session_id)
        if stats is None:
            stats = await session_store.create_session_stats(session_id)

        self_mode = bool(getattr(session, "self_mode", False))
        lookback_enabled = resolve_history_lookback_enabled(
            use_history_lookback, instruction_type="conversation"
        )
        lookback_count = settings_service.get_history_lookback_count(session_id)
        conversation_limit = (
            math.ceil(lookback_count * 1.2) if self_mode else lookback_count
        )
        conversation_history = (
            await session_store.get_conversation_history(session_id, conversation_limit)
            if lookback_enabled
            else []
        )

        # キャラクター情報（self_mode はプロフィール、テンプレ、カスタムの順）
        character_name = "キャラクター"
        pronoun = "僕"
        self_profile = None
        if self_mode:
            self_profile = await session_store.get_self_profile()
            if self_profile:
                character_name = self_profile.get("display_name") or character_name
                pronoun = self_profile.get("pronoun") or pronoun
        elif session.character_id:
            character = character_manager.get_by_id(session.character_id)
            if character:
                character_name = character.name
                pronoun = character.pronoun
        else:
            custom_metadata = load_custom_session_metadata(session_id)
            if custom_metadata:
                character_name = custom_metadata.get("name", character_name)
                pronoun = custom_metadata.get("pronoun", pronoun)

        # 現在の衣装説明（直近の履歴から）
        current_outfit_desc = ""
        history = await session_store.get_history(session_id)
        if history:
            current_outfit_desc = history[-1].after_description or ""

        attributes = await session_store.get_session_attribute_texts(session_id)
        user_settings = await session_store.get_user_settings()
        effective_language = normalize_language(
            language or user_settings.get("language")
        )
        novelai_text_model = user_settings.get("novelai_text_model")

        timeline_limit = math.ceil(lookback_count * 1.6)
        session_timeline = (
            await session_store.get_recent_instructions(
                session_id, limit=timeline_limit
            )
            if lookback_enabled
            else []
        )

        # 現在の発言を過去履歴へ含めないよう、タイムライン取得後に保存する
        user_conv = await session_store.add_conversation(
            session_id, "user", message, instruction_type="conversation"
        )
        # プロンプトを構築（self_mode はプロフィールベース、通常はステージベース）
        if self_mode and self_profile:
            from .self_mode_prompts import build_self_mode_conversation_prompt

            system_prompt, user_prompt = build_self_mode_conversation_prompt(
                message=message,
                conversation_history=conversation_history,
                current_outfit_desc=current_outfit_desc,
                self_profile=self_profile,
                nsfw_mode=stats.nsfw_mode,
                language=effective_language,
                session_timeline=session_timeline,
                enable_multiple_people=enable_multiple_people,
                lookback_count=lookback_count,
            )
        else:
            system_prompt, user_prompt = build_conversation_prompt(
                message=message,
                conversation_history=conversation_history,
                stats=stats,
                current_outfit_desc=current_outfit_desc,
                character_name=character_name,
                pronoun=pronoun,
                attributes=attributes,
                nsfw_mode=stats.nsfw_mode,
                transformation_count=session.transformation_count,
                language=effective_language,
                session_timeline=session_timeline,
                lookback_count=lookback_count,
            )
        if use_play_memory:
            from .play_memory_service import play_memory_service

            system_prompt += await play_memory_service.build_context(
                session_id, enabled=True, language=effective_language
            )

        return ChatContext(
            session_id=session_id,
            message=message,
            language=effective_language,
            use_play_memory=use_play_memory,
            session=session,
            stats=stats,
            pronoun=pronoun,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            novelai_text_model=novelai_text_model,
            user_conversation_id=getattr(user_conv, "id", None),
        )

    async def _record_reply(
        self, ctx: ChatContext, response_text: str, *, update_memory: bool = True
    ) -> tuple[str | None, str]:
        """キャラクター応答を保存し、必要ならプレイメモを更新する。

        Returns:
            (保存した会話 ID, プレイメモ更新の結果 updated / failed / skipped)
        """
        char_conv = await session_store.add_conversation(
            ctx.session_id, "character", response_text
        )
        memory_status = "skipped"
        if update_memory and ctx.use_play_memory:
            from .play_memory_service import play_memory_service

            updated = await play_memory_service.update_rolling(
                ctx.session_id,
                interaction_type="conversation",
                user_input=ctx.message,
                result_text=response_text,
                language=ctx.language,
            )
            memory_status = "updated" if updated else "failed"
        return getattr(char_conv, "id", None), memory_status

    def _fallback_response(self, ctx: ChatContext) -> str:
        return get_fallback_response(ctx.stats.bloom, ctx.pronoun, ctx.stats.nsfw_mode)

    @staticmethod
    def _stage_display(ctx: ChatContext) -> str:
        if ctx.session.transformation_count == 0:
            return "未変身"
        return get_stage_display_name(get_stage_name(ctx.stats.bloom))

    async def chat(self, ctx: ChatContext) -> dict[str, Any]:
        """応答を一括生成して保存する（POST /chat）。"""
        response_text = ""
        try:
            response_text = (
                await self.generate_with_language_retry(
                    llm_service=llm_service,
                    system_prompt=ctx.system_prompt,
                    user_prompt=ctx.user_prompt,
                    language=ctx.language,
                    novelai_model_override=ctx.novelai_text_model,
                )
                or ""
            )
        except Exception:
            response_text = ""
        if not response_text:
            response_text = self._fallback_response(ctx)

        char_conversation_id, play_memory_update = await self._record_reply(
            ctx, response_text
        )
        return {
            "session_id": ctx.session_id,
            "character_response": response_text,
            "psychological_state": self._stage_display(ctx),
            "language": ctx.language,
            "user_conversation_id": ctx.user_conversation_id,
            "character_conversation_id": char_conversation_id,
            "play_memory_update": play_memory_update,
        }

    async def chat_stream(
        self, ctx: ChatContext
    ) -> AsyncGenerator[dict[str, Any], None]:
        """応答をストリーミングする（GET /chat/stream）。

        Yields:
            {"type": "text", "chunk"} → 最後に {"type": "done", ...}。
            言語が合わない・生成に失敗したときは {"type": "error", "fallback", ...}
            を 1 件だけ送って終える
        """
        full_response = ""
        try:
            async for chunk in llm_service.generate_feeling_stream(
                system_prompt=ctx.system_prompt,
                user_prompt=ctx.user_prompt,
                novelai_model_override=ctx.novelai_text_model,
            ):
                full_response += chunk
                yield {"type": "text", "chunk": chunk}

            if not is_response_language_valid(full_response, ctx.language):
                retry_prompt = f"{ctx.user_prompt}\n\nIMPORTANT: Respond in {'English only' if ctx.language == 'en' else 'Japanese only'}."
                try:
                    retry_text = await self.generate_with_language_retry(
                        llm_service=llm_service,
                        system_prompt=ctx.system_prompt,
                        user_prompt=retry_prompt,
                        language=ctx.language,
                        novelai_model_override=ctx.novelai_text_model,
                    )
                    if retry_text and is_response_language_valid(
                        retry_text, ctx.language
                    ):
                        yield await self._fallback_payload(ctx, retry_text)
                        return
                except Exception:
                    pass
                yield await self._fallback_payload(ctx, self._fallback_response(ctx))
                return

            char_conversation_id, memory_status = await self._record_reply(
                ctx, full_response
            )
            yield {
                "type": "done",
                "full_response": full_response,
                "language": ctx.language,
                "user_conversation_id": ctx.user_conversation_id,
                "character_conversation_id": char_conversation_id,
                "play_memory_update": memory_status,
            }
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            # 生成中の例外はフォールバック応答で締める（プレイメモは更新しない）
            char_conversation_id, _ = await self._record_reply(
                ctx, self._fallback_response(ctx), update_memory=False
            )
            yield {
                "type": "error",
                "fallback": self._fallback_response(ctx),
                "language": ctx.language,
                "user_conversation_id": ctx.user_conversation_id,
                "character_conversation_id": char_conversation_id,
            }

    async def _fallback_payload(self, ctx: ChatContext, text: str) -> dict[str, Any]:
        """言語不一致時の代替応答を保存して error ペイロードにする。"""
        char_conversation_id, memory_status = await self._record_reply(ctx, text)
        return {
            "type": "error",
            "fallback": text,
            "language": ctx.language,
            "user_conversation_id": ctx.user_conversation_id,
            "character_conversation_id": char_conversation_id,
            "play_memory_update": memory_status,
        }


conversation_service = ConversationService()
