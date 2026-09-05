"""
Instruction suggestion service

Generates a next instruction text (detailed situation/story text) based on the
user's past history (history + conversation) and current session state.
"""

from __future__ import annotations

import logging

from .custom_sessions import load_custom_session_metadata
from .llm_json import strip_code_fence

logger = logging.getLogger(__name__)

_FILTERABLE_TYPES = {"dress_up", "reality_alter", "action"}


def _resolve_type_filter(instruction_type: str | None) -> str | None:
    """フィルタ対象の instruction_type を正規化する。

    dress_up/reality_alter/action のいずれかのみフィルタ対象とし、
    それ以外（None/"all"/"conversation"等）は全種類統合(None)として扱う。
    """
    if instruction_type in _FILTERABLE_TYPES:
        return instruction_type
    return None


def _strip_llm_wrapper(raw: str) -> str:
    """LLM出力からコードフェンス・前後の引用符/空白を除去する。"""
    text = strip_code_fence(raw)
    if len(text) >= 2 and text[0] in "\"'「『" and text[-1] in "\"'」』":
        text = text[1:-1].strip()
    return text


async def _build_character_context(session, language: str) -> str:
    """キャラクター/セルフプロフィールの文脈テキストを構築する。"""
    from .characters import character_manager
    from .session import session_store

    if getattr(session, "self_mode", False):
        self_profile = await session_store.get_self_profile()
        if self_profile:
            name = self_profile.get("display_name") or ""
            personality = self_profile.get("personality") or ""
            reaction = self_profile.get("reaction_style") or ""
            if language == "en":
                return f"Self-mode profile: name={name}, personality={personality}, reaction_style={reaction}"
            return f"セルフモードプロフィール: 名前={name}, 性格={personality}, リアクション={reaction}"
        return ""

    if session.character_id:
        character = character_manager.get_by_id(session.character_id)
        if character:
            if language == "en":
                return f"Character: {character.name}. {character.personality or character.description}"
            return f"キャラクター: {character.name}。{character.personality or character.description}"
        return ""

    # カスタム画像セッション: メタデータがあれば名前程度を利用
    try:
        custom_metadata = load_custom_session_metadata(session.id)
    except Exception:  # pragma: no cover - defensive, avoid hard failure
        custom_metadata = {}
    name = custom_metadata.get("name") if custom_metadata else None
    if name:
        return f"Character: {name}" if language == "en" else f"キャラクター: {name}"
    return ""


async def generate_instruction_suggestion(
    session_id: str,
    instruction_type: str | None,
    language: str = "ja",
    keyword: str | None = None,
    use_memory: bool = False,
    use_play_memory: bool = False,
) -> str:
    """過去の履歴と現在のセッション状態から次の指示テキストを生成する。

    Args:
        session_id: セッションID
        instruction_type: dress_up/reality_alter/action のいずれか、または None/"all"（全種類統合）
        language: "ja" or "en"
        keyword: ユーザーが入力欄に入力した自由テキスト/キーワード（任意、生成に反映される）
        use_memory: Trueの場合、保存済みメモリテキスト（ユーザーの嗜好傾向）を取得して生成に反映する

    Returns:
        生成された指示テキスト

    Raises:
        ValueError: セッションが存在しない、または対象の履歴が0件かつkeyword未指定の場合
    """
    from .instruction_suggestion_prompts import build_instruction_suggestion_prompt
    from .llm_service import llm_service
    from .session import session_store
    from .settings_service import settings_service

    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise ValueError(f"session not found: {session_id}")

    stats = await session_store.get_session_stats(session_id)
    attributes = await session_store.get_session_attribute_texts(session_id)
    character_context = await _build_character_context(session, language)

    type_filter = _resolve_type_filter(instruction_type)
    timeline = await session_store.get_recent_instructions(
        session_id,
        instruction_types=[type_filter] if type_filter else None,
        limit=30,
    )
    has_keyword = bool(keyword and keyword.strip())
    if not timeline and not has_keyword:
        raise ValueError("no history available for suggestion")

    memory_text = await settings_service.get_memory_text() if use_memory else None
    if use_play_memory:
        from .play_memory_service import play_memory_service

        play_context = await play_memory_service.build_context(
            session_id, enabled=True, language=language
        )
        if play_context:
            memory_text = f"{play_context}\n\n{memory_text or ''}".strip()

    system_prompt, user_prompt = build_instruction_suggestion_prompt(
        character_context=character_context,
        stats=stats,
        attributes=attributes,
        timeline=timeline,
        instruction_type_filter=type_filter,
        language=language,
        keyword=keyword,
        memory_text=memory_text,
    )

    result = await llm_service.generate_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    suggestion = _strip_llm_wrapper(result.content)
    max_len = 800
    if len(suggestion) > max_len:
        suggestion = suggestion[:max_len].rstrip()

    return suggestion
