"""
ゲームAPIエンドポイント

着せ替えインタラクティブゲームのAPIルーター。
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ..consts.language import normalize_language
from ..models import DIFFICULTY_PRESETS
from ..schemas.characters import CharacterListResponse, GenerateBaseTagsRequest
from ..schemas.common import ErrorResponse
from ..schemas.conversation import SuggestInstructionRequest, SuggestInstructionResponse
from ..schemas.gallery import GalleryEndingItem, GalleryResponse
from ..schemas.novelai import (
    AnlasBalanceResponse,
    AnlasUsageModel,
    MaskListResponse,
    MaskSaveRequest,
)
from ..schemas.parameters import (
    DifficultyListResponse,
    DifficultyResponse,
    SessionStatsResponse,
)
from ..schemas.play import PlayRequest, PlayStreamRequest
from ..schemas.session import (
    BranchSessionRequest,
    BranchSessionResponse,
    CustomStartRequest,
    GameStartRequest,
    GameStartResponse,
    HistorySelectResponse,
    PlayMemoryResponse,
    PlayMemoryUpdateRequest,
    SessionListResponse,
    SessionResetResponse,
    SessionResponse,
    SessionSummary,
)
from ..services import mask_service
from ..services.characters import character_manager
from ..services.conversation_service import (
    ChatContext,
    SessionNotFoundError,
    conversation_service,
)
from ..services.custom_sessions import (
    list_custom_characters as list_custom_character_items,
)
from ..services.endings import ENDINGS
from ..services.mask_service import MaskError
from ..services.session import session_store

router = APIRouter(prefix="/game", tags=["Game"])


async def _build_chat_context(**params: Any) -> ChatContext:
    """会話の前処理。セッションが無ければ 404。"""
    try:
        return await conversation_service.build_chat_context(**params)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        ) from exc


def _game_start_response(
    session_id: str, difficulty: str, stats: Any
) -> GameStartResponse:
    return GameStartResponse(
        session_id=session_id,
        difficulty=difficulty,
        initial_stats=SessionStatsResponse(
            bloom=stats.bloom,
            shame=stats.shame,
            adaptation=stats.adaptation,
            passed_critical_points=stats.passed_critical_points,
            difficulty=stats.difficulty,
            nsfw_mode=stats.nsfw_mode,
        ),
    )


@router.get(
    "/characters",
    response_model=CharacterListResponse,
    summary="キャラクター一覧を取得",
    description="選択可能なキャラクターの一覧を返却",
)
async def list_characters() -> CharacterListResponse:
    """キャラクター一覧を取得"""
    characters = character_manager.get_all_api_models()
    return CharacterListResponse(characters=characters)


@router.get(
    "/session/{session_id}",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="セッション情報を取得",
    description="現在のセッション状態と履歴を返却",
)
async def get_session(session_id: str) -> SessionResponse:
    """セッション情報を取得"""
    session = await session_store.get_full_session_response(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )
    return session


@router.post(
    "/play/stream",
    summary="ストリーミング着せ替え",
    description="着せ替えを実行し、テキストと画像をSSEでストリーミング返却",
)
async def play_game_stream(request: PlayStreamRequest) -> EventSourceResponse:
    """ストリーミング着せ替えを実行

    SSEイベント:
    - text: {"chunk": "テキストチャンク"}
    - image: {"image": "base64...", "history_id": "uuid"}
    - complete: {"session_id": "uuid", "transformation_count": 1}
    - error: {"message": "エラーメッセージ"}
    """
    from ..services.game_service import game_service

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for event in game_service.play_with_stream(
            session_id=request.session_id,
            character_id=request.character_id,
            character_image=request.character_image,
            instruction=request.instruction,
            base_history_id=request.base_history_id,
            costume_image=request.costume_image,
            language_override=request.language,
            transformation_type=request.transformation_type,
            mask_image=request.mask_image,
            mask_id=request.mask_id,
            inpaint_strength=request.inpaint_strength,
            inpaint_noise=request.inpaint_noise,
            negative_prompt=request.negative_prompt,
            prompt_override=request.prompt_override,
            nsfw_mode_override=request.nsfw_mode,
            difficulty_override=request.difficulty,
            character_references=[
                ref.model_dump() for ref in request.character_references
            ]
            if request.character_references
            else None,
            instruction_type=request.instruction_type,
            seed=request.seed,
            enable_surroundings_image=request.enable_surroundings_image,
            surroundings_include_people=request.surroundings_include_people,
            clothing_color_consistency=request.clothing_color_consistency,
            respect_clothing_layers=request.respect_clothing_layers,
            enable_multiple_people=request.enable_multiple_people,
            use_character_panel=request.use_character_panel,
            use_memory=request.use_memory,
            use_play_memory=request.use_play_memory,
            use_history_lookback=request.use_history_lookback,
            image_only_text_to_image=request.image_only_text_to_image,
        ):
            yield {
                "event": event.type,
                "data": json.dumps(event.data, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.get(
    "/session",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="現在のセッション取得",
    description="アクティブなセッション情報と履歴を返却（パラメータ含む）",
)
async def get_current_session() -> SessionResponse:
    """現在のアクティブセッションを取得（パラメータ拡張版）"""
    session = await session_store.get_active_session()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "アクティブなセッションがありません",
            },
        )
    response = await session_store.get_full_session_response(session.id)
    if response is None:
        raise HTTPException(status_code=404, detail="Session data not found")
    return response


@router.get(
    "/session/image/{session_id}",
    summary="セッション初期画像を取得",
    description="セッションの初期画像を返却（履歴がない場合のキャラクター画像）",
)
async def get_session_image(session_id: str) -> FileResponse:
    """セッションの初期画像を取得"""
    from ..settings.config import BASE_DIR, settings

    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    # 画像パスを解決
    # current_image_path は2種類のパターンがある:
    # 1. キャラクター初期画像: images/characters/... (BASE_DIR からの相対パス)
    # 2. 履歴画像: history_images/... (data/ からの相対パス)
    if session.current_image_path:
        # まず履歴画像パスとして試す (data/ からの相対パス)
        image_path = settings.history_images_dir.parent / session.current_image_path
        if image_path.exists():
            return FileResponse(
                image_path,
                media_type="image/png",
                headers={"Cache-Control": "max-age=3600"},
            )

        # 次にBASE_DIRからの相対パスとして試す (キャラクター画像)
        image_path = BASE_DIR / session.current_image_path
        if image_path.exists():
            return FileResponse(
                image_path,
                media_type="image/png",
                headers={"Cache-Control": "max-age=3600"},
            )

    raise HTTPException(
        status_code=404,
        detail={
            "error": "image_not_found",
            "message": "画像が見つかりません",
        },
    )


@router.get(
    "/difficulties",
    response_model=DifficultyListResponse,
    summary="難易度一覧取得",
    description="選択可能な難易度プリセット一覧を取得",
)
async def get_difficulties() -> DifficultyListResponse:
    """難易度一覧を取得"""
    difficulties = [
        DifficultyResponse(
            id=preset.id,
            name=preset.name,
            description=f"羞恥心初期値: {preset.shame_initial}, 開花倍率: {preset.bloom_multiplier}x",
        )
        for preset in DIFFICULTY_PRESETS.values()
    ]
    return DifficultyListResponse(difficulties=difficulties)


@router.post(
    "/start",
    response_model=GameStartResponse,
    responses={400: {"model": ErrorResponse}},
    summary="ゲームセッション開始",
    description="難易度を選択してゲームセッションを開始",
)
async def start_game(request: GameStartRequest) -> GameStartResponse:
    """ゲームセッションを開始（難易度選択付き）"""
    from ..services.game_service import GameServiceError, game_service

    try:
        session, stats, difficulty = await game_service.start_session(
            character_id=request.character_id,
            difficulty=request.difficulty,
            nsfw_mode=request.nsfw_mode,
            self_mode=request.self_mode,
        )
    except GameServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code or "invalid_request", "message": str(exc)},
        ) from exc
    return _game_start_response(session.id, difficulty, stats)


@router.post(
    "/start-custom",
    response_model=GameStartResponse,
    responses={400: {"model": ErrorResponse}},
    summary="カスタム画像でセッション開始",
    description="ユーザーがアップロードした画像でゲームセッションを開始",
)
async def start_game_custom(request: CustomStartRequest) -> GameStartResponse:
    """カスタム画像でセッションを開始"""
    from ..services.game_service import GameServiceError, game_service

    try:
        session, stats, difficulty = await game_service.start_custom_session(
            custom_character_id=request.custom_character_id,
            image=request.image,
            name=request.name,
            description=request.description,
            pronoun=request.pronoun,
            personality=request.personality,
            gender=request.gender,
            base_tags=request.base_tags,
            difficulty=request.difficulty,
            nsfw_mode=request.nsfw_mode,
            self_mode=request.self_mode,
        )
    except GameServiceError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.code or "invalid_request", "message": str(exc)},
        ) from exc
    return _game_start_response(session.id, difficulty, stats)


@router.get(
    "/custom-characters",
    summary="作成済みカスタムキャラクター一覧",
    description="保存済みのカスタム画像とメタデータを返却",
)
async def list_custom_characters() -> dict:
    return {"characters": list_custom_character_items()}


@router.delete(
    "/session",
    response_model=SessionResetResponse,
    responses={404: {"model": ErrorResponse}},
    summary="セッションリセット",
    description="現在のセッションを非アクティブ化し、新しいセッションを開始可能にする",
)
async def reset_session() -> SessionResetResponse:
    """セッションをリセット"""
    result = await session_store.reset_session()
    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "アクティブなセッションがありません",
            },
        )
    return SessionResetResponse(message="セッションをリセットしました")


@router.post(
    "/history/{history_id}/select",
    response_model=HistorySelectResponse,
    responses={404: {"model": ErrorResponse}},
    summary="履歴からベース画像選択",
    description="指定した履歴の画像を次の変身のベース画像として設定",
)
async def select_history_as_base(history_id: str) -> HistorySelectResponse:
    """履歴の画像をベース画像として選択"""
    image_path = await session_store.select_history_as_base(history_id)
    if image_path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "history_not_found",
                "message": "履歴が見つかりません",
            },
        )
    return HistorySelectResponse(
        message="ベース画像を選択しました",
        current_image_path=image_path,
    )


@router.post(
    "/history/{history_id}/branch-session",
    response_model=BranchSessionResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="履歴画像から新規セッション分岐",
    description=(
        "指定履歴の画像状態から新規セッションを開始する。"
        "分岐点までの状況サマリーを LLM で生成し、初期 history に格納する。"
        "inherit_stats で開花度等のパラメータ引き継ぎ、"
        "self_mode で自分自身モードの継続/解除を選択できる。"
    ),
)
async def branch_session_from_history(
    history_id: str,
    request: BranchSessionRequest | None = None,
) -> BranchSessionResponse:
    """既存履歴の状態から新規セッションを分岐開始する"""
    from ..services.session_branch_service import (
        SessionBranchError,
    )
    from ..services.session_branch_service import (
        branch_session_from_history as do_branch,
    )

    body = request or BranchSessionRequest()
    try:
        return await do_branch(
            history_id,
            inherit_stats=body.inherit_stats,
            self_mode=body.self_mode,
        )
    except SessionBranchError as exc:
        status = (
            404
            if exc.code
            in {
                "history_not_found",
                "session_not_found",
                "image_not_found",
            }
            else 400
        )
        raise HTTPException(
            status_code=status,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "branch_failed",
                "message": f"セッション分岐に失敗しました: {exc}",
            },
        ) from exc


# =============================================================================
# セッション一覧・詳細 (001-immersion-enhancement)
# =============================================================================


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="セッション一覧取得",
    description="過去のセッション一覧を取得（ページネーション対応）",
)
async def list_sessions(
    limit: int = Query(20, ge=1, le=100, description="取得件数"),
    offset: int = Query(0, ge=0, description="オフセット"),
) -> SessionListResponse:
    """過去セッション一覧を取得"""
    from ..services.characters import character_manager

    sessions_data, total_count = await session_store.get_all_sessions(
        limit=limit,
        offset=offset,
    )

    sessions = []
    for s in sessions_data:
        # キャラクター名を取得
        character_name = None
        if s["character_id"]:
            character = character_manager.get_by_id(s["character_id"])
            if character:
                character_name = character.name

        sessions.append(
            SessionSummary(
                session_id=s["session_id"],
                character_id=s["character_id"],
                character_name=character_name,
                thumbnail_url=s["thumbnail_url"],
                transformation_count=s["transformation_count"],
                is_active=s["is_active"],
                created_at=s["created_at"],
                updated_at=s["updated_at"],
                last_instruction=s["last_instruction"],
            )
        )

    return SessionListResponse(
        sessions=sessions,
        total_count=total_count,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="セッション詳細取得",
    description="指定セッションの詳細情報（履歴含む）を取得",
)
async def get_session_detail(session_id: str) -> SessionResponse:
    """セッション詳細を取得"""
    response = await session_store.get_full_session_response(session_id)
    if response is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )
    return response


@router.post(
    "/sessions/{session_id}/restore",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="セッション復元",
    description="指定したセッションをアクティブに設定し、復元する",
)
async def restore_session(session_id: str) -> SessionResponse:
    """過去セッションを復元してアクティブにする"""
    # セッション存在確認
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    # セッションをアクティブ化
    success = await session_store.activate_session(session_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "activation_failed",
                "message": "セッションのアクティブ化に失敗しました",
            },
        )

    # 復元したセッション情報を返却
    response = await session_store.get_full_session_response(session_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Session data not found")
    return response


@router.patch("/sessions/{session_id}/play-memory", response_model=PlayMemoryResponse)
async def update_play_memory(
    session_id: str, request: PlayMemoryUpdateRequest
) -> PlayMemoryResponse:
    """プレイメモの個別トグルとユーザーメモを更新する。"""
    updated = await session_store.update_play_memory(
        session_id,
        system_enabled=request.system_enabled,
        user_enabled=request.user_enabled,
        user_text=request.user_text,
        update_user_text="user_text" in request.model_fields_set,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="session not found")
    return updated


@router.post(
    "/sessions/{session_id}/play-memory/regenerate",
    response_model=PlayMemoryResponse,
)
async def regenerate_play_memory(
    session_id: str, language: str | None = Query(None)
) -> PlayMemoryResponse:
    """現在の全履歴から自動メモを再生成する。"""
    from ..services.play_memory_service import play_memory_service

    user_settings = await session_store.get_user_settings()
    try:
        return await play_memory_service.regenerate(
            session_id, normalize_language(language or user_settings.get("language"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/gallery",
    response_model=GalleryResponse,
    summary="ギャラリー取得",
    description="達成済みエンディング一覧と全エンディング数を取得",
)
async def get_gallery() -> GalleryResponse:
    """ギャラリー（エンディング一覧）を取得"""
    # 達成済みエンディングIDを取得
    achieved_ids = await session_store.get_achieved_ending_ids()
    achieved_endings = await session_store.get_achieved_endings()
    achieved_map = {e.ending_id: e.achieved_at for e in achieved_endings}

    # すべてのエンディングをチェック
    items = []
    for ending_id, ending in ENDINGS.items():
        achieved = ending_id in achieved_ids
        items.append(
            GalleryEndingItem(
                ending_id=ending_id,
                title=ending.title if achieved else "???",
                achieved=achieved,
                achieved_at=achieved_map.get(ending_id),
            )
        )

    return GalleryResponse(
        endings=items,
        total_count=len(ENDINGS),
        achieved_count=len(achieved_ids),
    )


@router.get(
    "/endings",
    summary="エンディング一覧",
    description="全エンディングの基本情報を取得（条件テキスト含む）",
)
async def list_endings() -> dict:
    """エンディング一覧を取得（開発・デバッグ用）"""
    achieved_ids = await session_store.get_achieved_ending_ids()
    return {
        "endings": [
            {
                "id": e.id,
                "title": e.title if e.id in achieved_ids else "???",
                "condition_text": e.condition_text if e.id in achieved_ids else "???",
                "achieved": e.id in achieved_ids,
            }
            for e in ENDINGS.values()
        ]
    }


@router.get(
    "/ending/{ending_id}",
    responses={404: {"model": ErrorResponse}},
    summary="エンディング詳細取得",
    description="指定したエンディングの詳細情報を取得",
)
async def get_ending_detail(ending_id: str) -> dict:
    """エンディング詳細を取得"""
    ending = ENDINGS.get(ending_id)
    if ending is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "ending_not_found",
                "message": "エンディングが見つかりません",
            },
        )

    achieved_ids = await session_store.get_achieved_ending_ids()
    is_achieved = ending_id in achieved_ids

    if not is_achieved:
        # 未達成の場合は限定情報のみ
        return {
            "id": ending_id,
            "title": "???",
            "achieved": False,
        }

    return {
        "id": ending_id,
        "title": ending.title,
        "description": ending.description,
        "condition_text": ending.condition_text,
        "final_speech": ending.final_speech,
        "summary": ending.summary,
        "achieved": True,
    }


# =============================================================================
# 会話 (Conversation)
# =============================================================================


@router.post(
    "/chat",
    summary="キャラクターと会話",
    description="キャラクターにメッセージを送信し、応答を取得",
)
async def chat_with_character(
    session_id: str = Query(..., description="セッションID"),
    message: str = Query(..., min_length=1, max_length=500, description="メッセージ"),
    language: str | None = Query(None, description="応答言語 (ja/en)"),
    enable_multiple_people: bool = Query(False, description="複数人表示を有効にする"),
    use_play_memory: bool = Query(False, description="プレイメモを有効にする"),
    use_history_lookback: bool | None = Query(None, description="履歴遡及を利用するか"),
) -> dict:
    """キャラクターとの会話"""
    ctx = await _build_chat_context(
        session_id=session_id,
        message=message,
        language=language,
        enable_multiple_people=enable_multiple_people,
        use_play_memory=use_play_memory,
        use_history_lookback=use_history_lookback,
    )
    return await conversation_service.chat(ctx)


@router.post(
    "/suggest-instruction",
    response_model=SuggestInstructionResponse,
    summary="過去メッセージから指示テキストを生成",
    description="セッションの過去のhistory/conversationと現在の状態を踏まえ、次に送信できる指示テキストをLLMで生成する（送信はしない）",
)
async def suggest_instruction(
    request: SuggestInstructionRequest,
) -> SuggestInstructionResponse:
    """過去の履歴を踏まえた指示テキストの生成"""
    from ..services.instruction_suggestion_service import (
        generate_instruction_suggestion,
    )

    try:
        suggestion = await generate_instruction_suggestion(
            session_id=request.session_id,
            instruction_type=request.instruction_type,
            language=normalize_language(request.language),
            keyword=request.keyword,
            use_memory=request.use_memory,
            use_play_memory=request.use_play_memory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SuggestInstructionResponse(suggestion=suggestion)


@router.get(
    "/chat/stream",
    summary="キャラクターと会話（ストリーミング）",
    description="キャラクターにメッセージを送信し、応答をストリーミング取得",
)
async def chat_with_character_stream(
    session_id: str = Query(..., description="セッションID"),
    message: str = Query(..., min_length=1, max_length=500, description="メッセージ"),
    language: str | None = Query(None, description="応答言語 (ja/en)"),
    enable_multiple_people: bool = Query(False, description="複数人表示を有効にする"),
    use_play_memory: bool = Query(False, description="プレイメモを有効にする"),
    use_history_lookback: bool | None = Query(None, description="履歴遡及を利用するか"),
) -> EventSourceResponse:
    """キャラクターとの会話（ストリーミング）

    `data:` 行だけの SSE。ペイロードは {"type": "text" | "done" | "error", ...}
    """
    ctx = await _build_chat_context(
        session_id=session_id,
        message=message,
        language=language,
        enable_multiple_people=enable_multiple_people,
        use_play_memory=use_play_memory,
        use_history_lookback=use_history_lookback,
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for payload in conversation_service.chat_stream(ctx):
            yield {"data": json.dumps(payload)}

    return EventSourceResponse(event_generator(), sep="\n")


@router.get(
    "/conversation/{session_id}",
    summary="会話履歴取得",
    description="セッションの会話履歴を取得",
)
async def get_conversation_history(
    session_id: str,
    limit: int = Query(20, ge=1, le=100, description="取得件数上限"),
) -> dict:
    """会話履歴を取得"""
    # セッションの存在確認
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    messages = await session_store.get_conversation_history(session_id, limit)
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
            }
            for msg in messages
        ],
    }


# =============================================================================
# 画質改善
# =============================================================================


@router.get(
    "/improve-quality/stream",
    summary="画質改善（ストリーミング）",
    description="劣化した画像を初期画像+現在の状態説明で再生成し、画質をリセット",
)
async def improve_quality_stream(
    session_id: str = Query(..., description="セッションID"),
) -> EventSourceResponse:
    """画質改善をストリーミングで実行

    SSEイベント:
    - status: {"message": "ステータスメッセージ"}
    - image: {"image": "base64...", "history_id": "uuid"}
    - cost: {"cost_usd": 0.05, "provider": "openrouter"}
    - complete: {"session_id": "uuid", "improved": true}
    - error: {"message": "エラーメッセージ"}
    """
    from ..services.game_service import game_service

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for event in game_service.improve_quality_with_stream(
            session_id=session_id,
        ):
            yield {
                "event": event.type,
                "data": json.dumps(event.data, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post(
    "/standing-portrait",
    summary="立ち絵再生成",
    description="現在の姿を、初期立ち絵と同じ構図の全身立ち絵として再生成する（履歴には保存しない）",
    responses={400: {"model": ErrorResponse}},
)
async def generate_standing_portrait(
    session_id: str = Query(..., description="セッションID"),
    nsfw_mode: bool | None = Query(
        None, description="現在選択中のNSFW設定（指定時はこの値を優先）"
    ),
) -> dict:
    """立ち絵を再生成して base64 で返す"""

    from ..services.game_service import GameServiceError, game_service

    try:
        image_bytes, cost_usd = await game_service.generate_standing_portrait(
            session_id=session_id,
            nsfw_mode=nsfw_mode,
        )
    except GameServiceError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "standing_portrait_failed", "message": str(e)},
        ) from e

    return {
        "image": base64.b64encode(image_bytes).decode("utf-8"),
        "cost_usd": cost_usd,
    }


# =============================================================================
# 属性付与 (Attribute Assignment)
# =============================================================================


@router.post(
    "/attributes",
    summary="属性を追加",
    description="セッションにカスタム属性を追加（画像生成プロンプトに反映）",
)
async def add_attribute(
    session_id: str = Query(..., description="セッションID"),
    attribute_text: str = Query(
        ..., min_length=1, max_length=100, description="属性テキスト"
    ),
) -> dict:
    """属性を追加"""
    # セッション存在確認
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    attribute = await session_store.add_session_attribute(session_id, attribute_text)
    return {
        "success": True,
        "attribute": attribute,
    }


@router.delete(
    "/attributes/{attribute_id}",
    summary="属性を削除",
    description="指定した属性を削除",
)
async def delete_attribute(attribute_id: str) -> dict:
    """属性を削除"""
    success = await session_store.remove_session_attribute(attribute_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "attribute_not_found",
                "message": "属性が見つかりません",
            },
        )
    return {"success": True, "deleted_id": attribute_id}


@router.get(
    "/attributes/{session_id}",
    summary="属性一覧取得",
    description="セッションの属性一覧を取得",
)
async def get_attributes(session_id: str) -> dict:
    """属性一覧を取得"""
    # セッション存在確認
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    attributes = await session_store.get_session_attributes(session_id)
    return {
        "session_id": session_id,
        "attributes": attributes,
    }


@router.post("/preview/prompt", response_model=dict, summary="プロンプトプレビュー")
async def preview_prompt(request: PlayRequest) -> dict:
    from ..services.game_service import game_service

    instruction = request.instruction
    if request.use_play_memory:
        from ..services.play_memory_service import play_memory_service

        instruction += await play_memory_service.build_context(
            request.session_id,
            enabled=True,
            language=normalize_language(request.language),
        )

    return await game_service.preview_prompts(
        session_id=request.session_id,
        instruction=instruction,
        transformation_type=request.transformation_type,
        instruction_type=request.instruction_type,
        respect_clothing_layers=request.respect_clothing_layers,
        use_history_lookback=request.use_history_lookback,
    )


# =============================================================================
# マスク管理 (NovelAI向け)
# =============================================================================


@router.get("/masks", response_model=MaskListResponse, summary="マスク一覧取得")
async def list_masks() -> MaskListResponse:
    """システムマスク、履歴マスク、ユーザープリセットを返す"""
    return mask_service.list_masks()


@router.post("/masks", response_model=MaskListResponse, summary="マスクを保存")
async def save_mask(request: MaskSaveRequest) -> MaskListResponse:
    """マスクを保存する。nameが指定されている場合はプリセットとして、それ以外は履歴として保存"""
    try:
        return mask_service.save_mask(request.mask_base64, request.name)
    except MaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/masks/system/{filename}", summary="システムマスク取得")
async def get_system_mask(filename: str):
    path = mask_service.system_mask_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="mask not found")
    return FileResponse(path, media_type="image/png")


@router.get("/masks/history/{mask_id}", summary="履歴マスク取得")
async def get_history_mask(mask_id: str):
    path = mask_service.history_mask_path(mask_id)
    if path is None:
        raise HTTPException(status_code=404, detail="mask not found")
    return FileResponse(path, media_type="image/png")


@router.get("/masks/preset/{mask_id}", summary="プリセットマスク取得")
async def get_preset_mask(mask_id: str):
    """プリセットマスク画像を取得"""
    path = mask_service.preset_mask_path(mask_id)
    if path is None:
        raise HTTPException(status_code=404, detail="preset mask not found")
    return FileResponse(path, media_type="image/png")


@router.delete(
    "/masks/preset/{mask_id}",
    response_model=MaskListResponse,
    summary="プリセットマスク削除",
)
async def delete_preset_mask(mask_id: str) -> MaskListResponse:
    """プリセットマスクを削除し、最新のマスク一覧を返す"""
    try:
        return mask_service.delete_preset_mask(mask_id)
    except MaskError as exc:
        status_code = 404 if exc.code == "not_found" else 500
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


# ---------- Anlas balance ----------


@router.get(
    "/anlas",
    response_model=AnlasBalanceResponse,
    summary="Anlas残高取得",
    description="NovelAIのAnlas残高を取得する。NovelAI APIキー未設定時はnullを返す。",
)
async def get_anlas_balance() -> AnlasBalanceResponse:
    """Get the current Anlas balance from NovelAI."""
    from ..settings.config import settings as app_settings

    # provider設定ではなくAPIキーの有無でゲートする(providerを切り替えても
    # NovelAIキーがあれば残高は参照できるため)
    if not app_settings.novelai_api_key:
        return AnlasBalanceResponse()

    try:
        from ..services.anlas_service import get_anlas_balance as fetch_anlas

        balance = await fetch_anlas()
        if balance is None:
            return AnlasBalanceResponse()
        return AnlasBalanceResponse(
            fixed_anlas=balance.fixed_anlas,
            purchased_anlas=balance.purchased_anlas,
            total_anlas=balance.total_anlas,
            usage=AnlasUsageModel(
                percent=balance.usage.percent,
                is_negative=balance.usage.is_negative,
                time_until_next_percent=balance.usage.time_until_next_percent,
            )
            if balance.usage
            else None,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch Anlas balance: {e}",
        ) from e


# ── Base tags generation endpoint ──


@router.post(
    "/generate-base-tags",
    summary="外見タグを自動生成",
    description="キャラクター情報からDanbooru形式の英語外見タグをLLMで自動生成",
)
async def generate_base_tags(request: GenerateBaseTagsRequest) -> dict:
    """Generate Danbooru-style base tags from character description via LLM."""
    from ..services.llm_service import llm_service
    from ..services.prompts import build_base_tags_generation_prompt

    system_prompt, user_prompt = build_base_tags_generation_prompt(
        name=request.name,
        description=request.description,
        gender=request.gender,
        personality=request.personality,
    )

    # ユーザー設定からNovelAIテキストモデルを取得
    user_settings = await session_store.get_user_settings()
    effective_novelai_text_model = user_settings.get("novelai_text_model")

    try:
        result = await llm_service.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            novelai_model_override=effective_novelai_text_model,
        )
        # Clean up: remove markdown formatting, extra whitespace
        raw = result.content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        # Ensure single-line comma-separated format
        tags = ", ".join(
            tag.strip() for tag in raw.replace("\n", ",").split(",") if tag.strip()
        )
        return {"base_tags": tags}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate base tags: {e}",
        ) from e


# ------------------------------------------------------------------
# Conversation-only deletion (preserves History & images)
# ------------------------------------------------------------------


@router.delete(
    "/conversation/{history_id}",
    summary="会話テキストのみ削除",
    description="指定した履歴IDに紐づく会話テキストのみを削除し、履歴レコードと画像は保持する",
)
async def delete_conversation_by_history(
    history_id: str,
    session_id: str = Query(..., description="セッションID"),
) -> dict:
    """Delete conversation records for a history item without touching History/images."""
    result = await session_store.delete_conversation_by_history_id(
        session_id=session_id,
        history_id=history_id,
    )
    if result == -1:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": "History not found in this session",
            },
        )
    return {
        "success": True,
        "deleted_count": result,
        "message": f"Deleted {result} conversation records for history {history_id}",
    }


@router.delete(
    "/conversation/message/{conversation_id}",
    summary="会話メッセージの個別削除",
    description="指定したconversation IDのメッセージを1件削除する。履歴・画像は削除しない。",
)
async def delete_conversation_message(
    conversation_id: str,
    session_id: str = Query(..., description="セッションID"),
) -> dict:
    """Delete a single conversation message by its ID. History/images are NOT affected."""
    success = await session_store.delete_conversation_message(
        session_id=session_id,
        conversation_id=conversation_id,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": "Conversation message not found in this session",
            },
        )
    return {
        "success": True,
        "message": f"Deleted conversation message {conversation_id}",
    }


# ------------------------------------------------------------------
# Full history entry deletion (History + images + conversations)
# ------------------------------------------------------------------


@router.delete(
    "/history/{history_id}",
    summary="履歴エントリを完全削除",
    description="指定した履歴IDの履歴レコード・画像・会話テキストを全て削除する",
)
async def delete_history_entry(
    history_id: str,
    session_id: str = Query(..., description="セッションID"),
) -> dict:
    """Delete a history entry and all associated data (images, conversations)."""
    result = await session_store.delete_history_entry(
        session_id=session_id,
        history_id=history_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": "History not found in this session",
            },
        )
    # 複数人モード使用中の全キャラ克ターの外見を最新履歴に復帰
    try:
        from ..services.character_service import (
            restore_session_characters_appearance_from_history,
        )

        await restore_session_characters_appearance_from_history(session_id)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "Failed to restore session characters appearance after history "
            "delete (session=%s, history=%s): %s",
            session_id,
            history_id,
            exc,
        )
    return {
        "success": True,
        **result,
    }


# ------------------------------------------------------------------
# Latest history deletion (self-mode only)
# ------------------------------------------------------------------


@router.delete(
    "/session/{session_id}/latest-history",
    summary="最新履歴を削除",
    description="最新の履歴を削除し、1つ前の状態に復元する",
)
async def delete_latest_history(session_id: str) -> dict:
    """Delete the latest history entry and restore previous state."""
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "SESSION_NOT_FOUND", "message": "Session not found"},
        )

    result = await session_store.delete_latest_history(session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_HISTORY",
                "message": "No history to delete",
            },
        )

    # 複数人モード使用中の全キャラ克ターの外見を最新履歴に復帰
    try:
        from ..services.character_service import (
            restore_session_characters_appearance_from_history,
        )

        await restore_session_characters_appearance_from_history(session_id)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "Failed to restore session characters appearance after "
            "latest-history delete (session=%s): %s",
            session_id,
            exc,
        )

    return result
