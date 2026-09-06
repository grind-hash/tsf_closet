"""キャラチャット(TSF シナリオを経由しないキャラクターとの会話)の API。

ハンドラーは入力の受け取りと HTTP / SSE への変換だけを行い、スレッドの永続化・
判定 LLM・返答生成・立ち絵生成は services/character_chat_service に置く。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ..consts.character_chat import THREAD_MESSAGE_LIMIT
from ..schemas.character_chat import (
    CharacterChatAppearanceRequest,
    CharacterChatCreateRequest,
    CharacterChatMessageRequest,
)
from ..services.character_chat_service import (
    CharacterChatError,
    character_chat_service,
)

router = APIRouter(prefix="/character-chat", tags=["CharacterChat"])

_NOT_FOUND_CODES = {"thread_not_found", "source_not_found", "image_not_found"}


def _http_error(error: CharacterChatError) -> HTTPException:
    status = 404 if error.code in _NOT_FOUND_CODES else 400
    return HTTPException(
        status_code=status, detail={"code": error.code, "message": str(error)}
    )


def _sse_error(error: CharacterChatError, phase: str) -> dict:
    return {
        "event": "error",
        "data": json.dumps(
            {
                "code": error.code,
                "message": str(error),
                "phase": phase,
                "retryable": error.code == "invalid_model_output",
            },
            ensure_ascii=False,
        ),
    }


@router.get("/threads")
async def list_threads() -> dict:
    return {"threads": await character_chat_service.list_threads()}


@router.post("/threads/base")
async def open_base_thread() -> dict:
    """拠点キャラ(セレナ)のスレッドを返す。無ければ作る(冪等)。"""
    try:
        return await character_chat_service.get_or_create_base_thread()
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads", status_code=201)
async def create_thread(request: CharacterChatCreateRequest) -> dict:
    """過去セッション(または Prompt Expander エントリ)の人物からスレッドを作る。"""
    try:
        return await character_chat_service.create_session_thread(
            source_session_id=request.source_session_id,
            source_history_id=request.source_history_id,
            source_prompt_expander_entry_id=request.source_prompt_expander_entry_id,
        )
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    limit: int = Query(THREAD_MESSAGE_LIMIT, ge=1, le=THREAD_MESSAGE_LIMIT),
) -> dict:
    try:
        return await character_chat_service.get_thread(
            thread_id, with_messages=True, limit=limit
        )
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str) -> None:
    try:
        await character_chat_service.delete_thread(thread_id)
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads/{thread_id}/messages/stream")
async def message_stream(
    thread_id: str, request: CharacterChatMessageRequest
) -> EventSourceResponse:
    """発言を送り、判定 → 返答ストリーム → 保存 → (着替え) → (要約) を SSE で返す。"""

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in character_chat_service.stream_message(
                thread_id=thread_id, content=request.content
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except CharacterChatError as error:
            yield _sse_error(error, "chat")

    return EventSourceResponse(event_generator())


@router.put("/threads/{thread_id}/appearance")
async def set_appearance(
    thread_id: str, request: CharacterChatAppearanceRequest
) -> dict:
    """姿を過去セッション / 履歴 / Prompt Expander エントリの画像に差し替える。"""
    try:
        return await character_chat_service.set_appearance_from_source(
            thread_id,
            source_session_id=request.source_session_id,
            source_history_id=request.source_history_id,
            source_prompt_expander_entry_id=request.source_prompt_expander_entry_id,
        )
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads/{thread_id}/appearance/reset")
async def reset_appearance(thread_id: str) -> dict:
    """姿を最初の状態(同梱の立ち絵 / 選んだ時点の画像とタグ)へ戻す。画像生成はしない。"""
    try:
        return await character_chat_service.reset_appearance(thread_id)
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads/{thread_id}/portrait/stream")
async def portrait_stream(thread_id: str) -> EventSourceResponse:
    """現在の外見タグから立ち絵を描き直す。"""

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in character_chat_service.stream_portrait_regeneration(
                thread_id
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except CharacterChatError as error:
            yield _sse_error(error, "portrait")

    return EventSourceResponse(event_generator())


@router.get("/images/{thread_id}/{filename}")
async def get_image(thread_id: str, filename: str) -> FileResponse:
    try:
        path = character_chat_service.image_file(thread_id, filename)
    except CharacterChatError as error:
        raise _http_error(error) from error
    return FileResponse(path, media_type="image/png")
