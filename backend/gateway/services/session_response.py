"""
API 用セッションレスポンスの組立

永続化されたセッション・履歴・統計・属性・会話を `SessionResponse` DTO へ変換する。
DatabaseSessionStore.get_full_session_response から切り出したもので、
ストアは互換のため同名メソッドからここへ委譲する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import PersistedHistory, PersistedSession, SessionStats
from ..schemas.conversation import ConversationMessageResponse
from ..schemas.parameters import SessionStatsResponse
from ..schemas.session import (
    HistoryItem,
    PlayMemoryResponse,
    SessionAttributeResponse,
    SessionResponse,
)
from ..settings.config import settings

if TYPE_CHECKING:
    from .session import DatabaseSessionStore


def current_image_url(session: PersistedSession) -> str:
    """現在画像の URL。履歴に現在画像があればその履歴、無ければ最新履歴を指す。"""
    if session.history:
        for history_item in session.history:
            if history_item.image_path == session.current_image_path:
                return f"/history/images/{history_item.id}"
        return f"/history/images/{session.history[-1].id}"
    if session.current_image_path:
        return f"/game/session/image/{session.id}"
    return ""


async def build_history_item(
    store: DatabaseSessionStore, history_item: PersistedHistory
) -> HistoryItem:
    tag = await store.get_transformation_tag(history_item.id)
    surroundings_url = None
    if history_item.surroundings_image_path:
        surroundings_url = f"/history/surroundings/{history_item.id}"
    return HistoryItem(
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


def build_stats_response(stats: SessionStats) -> SessionStatsResponse:
    stats.enable_prompt_preview = settings.enable_prompt_preview
    return SessionStatsResponse(
        bloom=stats.bloom,
        shame=stats.shame,
        adaptation=stats.adaptation,
        passed_critical_points=stats.passed_critical_points,
        difficulty=stats.difficulty,
        nsfw_mode=stats.nsfw_mode,
        enable_prompt_preview=stats.enable_prompt_preview,
    )


def build_play_memory_response(session: PersistedSession) -> PlayMemoryResponse:
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


async def build_session_response(
    store: DatabaseSessionStore, session_id: str
) -> SessionResponse | None:
    """API用のセッションレスポンスを取得"""
    session = await store.get_session_with_history(session_id)
    if session is None:
        return None

    history_items = [
        await build_history_item(store, history_item)
        for history_item in session.history
    ]

    stats = await store.get_session_stats(session_id)
    stats_response = build_stats_response(stats) if stats else None

    attributes_raw = await store.get_session_attributes(session_id)
    attributes = [
        SessionAttributeResponse(id=attr["id"], text=attr["attribute_text"])
        for attr in attributes_raw
    ]

    conversations = await store.get_conversation_history(session_id)
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
        current_image_url=current_image_url(session),
        transformation_count=session.transformation_count,
        history=history_items,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        stats=stats_response,
        attributes=attributes,
        conversation_history=conversation_history,
        self_mode=session.self_mode,
        play_memory=build_play_memory_response(session),
    )
