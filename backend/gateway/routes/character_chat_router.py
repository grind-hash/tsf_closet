"""キャラチャット(TSF シナリオを経由しないキャラクターとの会話)の API。

ハンドラーは入力の受け取りと HTTP / SSE への変換だけを行い、スレッドの永続化・
判定 LLM・返答生成・立ち絵生成は services/character_chat_service に置く。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ..consts.character_chat import THREAD_MESSAGE_LIMIT
from ..schemas.character_chat import (
    CharacterChatAdventureAppearanceRequest,
    CharacterChatAppearanceRequest,
    CharacterChatAvatarRequest,
    CharacterChatCreateRequest,
    CharacterChatMessageRequest,
    CharacterChatPortraitRequest,
)
from ..services.character_chat_service import (
    CharacterChatError,
    character_chat_service,
)
from ..settings.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/character-chat", tags=["CharacterChat"])

_NOT_FOUND_CODES = {
    "thread_not_found",
    "source_not_found",
    "image_not_found",
    "run_not_found",
    "reference_not_found",
    "avatar_not_found",
}


def _http_error(error: CharacterChatError) -> HTTPException:
    status = 404 if error.code in _NOT_FOUND_CODES else 400
    return HTTPException(
        status_code=status, detail={"code": error.code, "message": str(error)}
    )


def _sse_error(error: Exception, phase: str) -> dict:
    code = getattr(error, "code", "internal_error")
    message = str(error) or type(error).__name__
    return {
        "event": "error",
        "data": json.dumps(
            {
                "code": code,
                "message": message,
                "phase": phase,
                "retryable": code == "invalid_model_output",
            },
            ensure_ascii=False,
        ),
    }


@router.get("/threads")
async def list_threads() -> dict:
    return {
        "threads": await character_chat_service.list_threads(),
        # 環境変数由来のグローバル設定。通常ゲームは session stats 経由で受け取るが
        # キャラチャットはそこを見ないため、一覧のペイロードへ載せる
        "enable_prompt_preview": bool(settings.enable_prompt_preview),
    }


@router.post("/threads/base")
async def open_base_thread() -> dict:
    """案内役キャラ(セレナ)のスレッドを返す。無ければ作る(冪等)。"""
    try:
        return await character_chat_service.get_or_create_base_thread()
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads/adventure/{run_id}")
async def open_adventure_thread(run_id: str) -> dict:
    """TSF シナリオ(恋愛シミュレーション)の攻略対象と話すスレッドを返す。無ければ作る(冪等)。"""
    try:
        return await character_chat_service.get_or_create_adventure_thread(run_id)
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
    """発言を送り、判定 → (調べ物) → 返答ストリーム → 保存 → (着替え) → (要約) を SSE で返す。"""

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in character_chat_service.stream_message(
                thread_id=thread_id,
                content=request.content,
                use_web_search=request.use_web_search,
                use_weather=request.use_weather,
                request_play_proposal=request.request_play_proposal,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except CharacterChatError as error:
            yield _sse_error(error, "chat")
        except Exception as error:  # noqa: BLE001 - SSE には他に伝える経路が無い
            logger.exception("character chat stream failed")
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


@router.post("/threads/{thread_id}/appearance/adventure")
async def set_adventure_appearance(
    thread_id: str, request: CharacterChatAdventureAppearanceRequest
) -> dict:
    """adventure 種の姿を run の画像に切り替える(既定 / 攻略対象の立ち絵 / 場面の画像)。"""
    try:
        return await character_chat_service.set_adventure_appearance(
            thread_id, mode=request.mode
        )
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.put("/threads/{thread_id}/avatar")
async def set_avatar(thread_id: str, request: CharacterChatAvatarRequest) -> dict:
    """3D モデル(VRM)の表示を切り替える(自動 / 2D 立ち絵 / 登録済みモデル)。"""
    try:
        return await character_chat_service.set_avatar(
            thread_id, mode=request.mode, avatar_id=request.avatar_id
        )
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.get("/avatar/base")
async def get_base_avatar() -> FileResponse:
    """案内役キャラの同梱 3D モデル(backend/images/character_chat/serena.vrm)。"""
    try:
        path = character_chat_service.base_avatar_path()
    except CharacterChatError as error:
        raise _http_error(error) from error
    return FileResponse(path, media_type="model/gltf-binary", filename=path.name)


@router.post("/threads/{thread_id}/appearance/reset")
async def reset_appearance(thread_id: str) -> dict:
    """姿を最初の状態(同梱の立ち絵 / 選んだ時点の画像とタグ)へ戻す。画像生成はしない。"""
    try:
        return await character_chat_service.reset_appearance(thread_id)
    except CharacterChatError as error:
        raise _http_error(error) from error


@router.post("/threads/{thread_id}/portrait/stream")
async def portrait_stream(
    thread_id: str,
    request: CharacterChatPortraitRequest | None = Body(default=None),
) -> EventSourceResponse:
    """現在の外見タグから立ち絵を描き直す(参照画像と精密参照の指定は任意)。"""
    options = request or CharacterChatPortraitRequest()

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in character_chat_service.stream_portrait_regeneration(
                thread_id,
                reference=options.reference,
                use_precise_reference=options.use_precise_reference,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except CharacterChatError as error:
            yield _sse_error(error, "portrait")
        except Exception as error:  # noqa: BLE001 - SSE には他に伝える経路が無い
            logger.exception("character chat portrait stream failed")
            yield _sse_error(error, "portrait")

    return EventSourceResponse(event_generator())


@router.get("/images/{thread_id}/{filename}")
async def get_image(thread_id: str, filename: str) -> FileResponse:
    try:
        path = character_chat_service.image_file(thread_id, filename)
    except CharacterChatError as error:
        raise _http_error(error) from error
    return FileResponse(path, media_type="image/png")
