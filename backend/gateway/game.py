"""
ゲームAPIエンドポイント

変身インタラクティブゲームのAPIルーター。
"""

from __future__ import annotations

import base64
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .characters import character_manager
from .models import (
    CharacterListResponse,
    ErrorResponse,
    HistorySelectResponse,
    PlayRequest,
    PlayResponse,
    SessionResetResponse,
    SessionResponse,
    # 新規追加 (T010, T016, T017)
    SessionStatsResponse,
    DifficultyResponse,
    DifficultyListResponse,
    GameStartRequest,
    GameStartResponse,
    DIFFICULTY_PRESETS,
    # ギャラリー (T052)
    GalleryResponse,
    GalleryEndingItem,
)
from .session import session_store
from .endings import ENDINGS

router = APIRouter(prefix="/game", tags=["Game"])


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
    "/character-image/{session_id}",
    summary="キャラクター画像を取得",
    description="セッションの初期キャラクター画像を返却",
)
async def get_character_image(session_id: str):
    """セッションのキャラクター画像を取得"""
    from fastapi.responses import FileResponse
    from .config import BASE_DIR

    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.current_image_path:
        raise HTTPException(status_code=404, detail="No image available")

    # current_image_path は相対パス (例: "images/characters/char1.png")
    image_path = BASE_DIR / session.current_image_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image file not found: {image_path}")

    # ファイル拡張子に応じたmedia_typeを設定
    suffix = image_path.suffix.lower()
    media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    return FileResponse(image_path, media_type=media_type)


@router.get(
    "/session/{session_id}",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="セッション情報を取得",
    description="現在のセッション状態と履歴を返却",
)
async def get_session(session_id: str) -> SessionResponse:
    """セッション情報を取得"""
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )
    return session.to_api_model()


@router.post(
    "/play",
    response_model=PlayResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="変身を実行",
    description="キャラクターに対して変身を実行し、結果画像と心境テキストを返却",
)
async def play_game(request: PlayRequest) -> PlayResponse:
    """変身を実行

    新規開始時: character_id または character_image を指定
    継続プレイ時: session_id を指定
    """
    # インポートを遅延して循環参照を回避
    from .game_service import game_service

    try:
        result = await game_service.play(request)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_request", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"ゲーム実行エラー: {e}"},
        ) from e


@router.get(
    "/play/stream",
    summary="ストリーミング変身",
    description="変身を実行し、テキストと画像をSSEでストリーミング返却",
)
async def play_game_stream(
    instruction: str = Query(
        ..., min_length=1, max_length=500, description="変身指示"
    ),
    session_id: Optional[str] = Query(None, description="既存セッションID"),
    character_id: Optional[str] = Query(None, description="キャラクターID"),
    character_image: Optional[str] = Query(None, description="Base64エンコード画像"),
    base_history_id: Optional[str] = Query(None, description="履歴からのベース画像ID"),
    use_kanji: bool = Query(False, description="漢字を使用するかどうか"),
) -> EventSourceResponse:
    """ストリーミング変身を実行

    SSEイベント:
    - text: {"chunk": "テキストチャンク"}
    - image: {"image": "base64...", "history_id": "uuid"}
    - complete: {"session_id": "uuid", "transformation_count": 1}
    - error: {"message": "エラーメッセージ"}
    """
    from .game_service import game_service

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for event in game_service.play_with_stream(
            session_id=session_id,
            character_id=character_id,
            character_image=character_image,
            instruction=instruction,
            base_history_id=base_history_id,
            use_kanji=use_kanji,
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
            description=f"なりきり度初期値: {preset.immersion_initial}, ワクワク倍率: {preset.excitement_multiplier}x",
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
    # 既存セッションをリセット
    await session_store.reset_session()

    # キャラクター情報を取得
    character_id = request.character_id
    if character_id:
        character = character_manager.get_by_id(character_id)
        if character is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_character",
                    "message": f"キャラクター '{character_id}' が見つかりません",
                },
            )
        image_path = character.image_path
    else:
        # デフォルトキャラクター
        default_char = (
            character_manager.get_all()[0] if character_manager.get_all() else None
        )
        if default_char is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no_characters",
                    "message": "利用可能なキャラクターがありません",
                },
            )
        character_id = default_char.id
        image_path = default_char.image_path

    # 難易度を検証
    difficulty = request.difficulty
    if difficulty not in DIFFICULTY_PRESETS:
        difficulty = "normal"

    # セッションを作成
    session = await session_store.create_session(
        image_path=image_path,
        character_id=character_id,
    )

    # セッション統計を作成
    stats = await session_store.create_session_stats(session.id, difficulty)

    return GameStartResponse(
        session_id=session.id,
        difficulty=difficulty,
        initial_stats=SessionStatsResponse(
            excitement=stats.excitement,
            immersion=stats.immersion,
            challenge=stats.challenge,
            passed_critical_points=stats.passed_critical_points,
            difficulty=stats.difficulty,
        ),
    )


class CustomImageStartRequest(BaseModel):
    """カスタム画像でのセッション開始リクエスト"""
    image: str  # Base64エンコードされた画像
    difficulty: str = "normal"


@router.post(
    "/start-custom",
    response_model=GameStartResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="カスタム画像でセッション開始",
    description="自分の画像をアップロードしてアニメ風キャラクターに変換し、ゲームセッションを開始",
)
async def start_game_custom(request: CustomImageStartRequest) -> GameStartResponse:
    """カスタム画像でゲームセッションを開始
    
    1. Base64画像をデコード
    2. アニメ風キャラクターに変換
    3. 変換後の画像を保存
    4. セッションを作成
    """
    from .config import BASE_DIR
    from .game_service import game_service
    from .prompts import ANIME_CHILD_CONVERSION_PROMPT
    import uuid
    
    # 既存セッションをリセット
    await session_store.reset_session()

    # Base64画像をデコード
    try:
        image_data = base64.b64decode(request.image)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_image",
                "message": f"画像のデコードに失敗しました: {e}",
            },
        )

    # アニメ風キャラクターに変換
    try:
        converted_image, _ = await game_service._generate_image(
            image_bytes=image_data,
            instruction=ANIME_CHILD_CONVERSION_PROMPT,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "conversion_failed",
                "message": f"アニメ風キャラクターへの変換に失敗しました: {e}",
            },
        )

    # 変換後の画像を保存
    image_id = str(uuid.uuid4())
    custom_images_dir = BASE_DIR / "data" / "custom_images"
    custom_images_dir.mkdir(parents=True, exist_ok=True)
    image_path = custom_images_dir / f"{image_id}.png"
    image_path.write_bytes(converted_image)

    # 難易度を検証
    difficulty = request.difficulty
    if difficulty not in DIFFICULTY_PRESETS:
        difficulty = "normal"

    # セッションを作成（相対パスを保存）
    relative_path = f"data/custom_images/{image_id}.png"
    session = await session_store.create_session(
        image_path=relative_path,
        character_id=None,
    )

    # セッション統計を作成
    stats = await session_store.create_session_stats(session.id, difficulty)

    return GameStartResponse(
        session_id=session.id,
        difficulty=difficulty,
        initial_stats=SessionStatsResponse(
            excitement=stats.excitement,
            immersion=stats.immersion,
            challenge=stats.challenge,
            passed_critical_points=stats.passed_critical_points,
            difficulty=stats.difficulty,
        ),
    )


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


# =============================================================================
# ギャラリー (T052, T053, T054)
# =============================================================================


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
) -> dict:
    """キャラクターとの会話"""
    from .conversation import (
        build_conversation_prompt,
        get_stage_name,
        get_stage_display_name,
        get_fallback_response,
    )
    from .llm_service import llm_service
    from .characters import character_manager

    # セッションを取得
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "session_not_found",
                "message": "セッションが見つかりません",
            },
        )

    # セッション統計を取得
    stats = await session_store.get_session_stats(session_id)
    if stats is None:
        stats = await session_store.create_session_stats(session_id)

    # 会話履歴を取得
    conversation_history = await session_store.get_conversation_history(session_id)

    # キャラクター情報を取得
    character_name = "キャラクター"
    pronoun = "僕"
    if session.character_id:
        character = character_manager.get_by_id(session.character_id)
        if character:
            character_name = character.name
            pronoun = character.pronoun

    # 現在の衣装説明を取得（直近の履歴から）
    current_outfit_desc = ""
    history = await session_store.get_history(session_id)
    if history:
        latest = history[-1]
        current_outfit_desc = latest.after_description or ""

    # ユーザーメッセージを保存
    await session_store.add_conversation(session_id, "user", message)

    # プロンプトを構築
    system_prompt, user_prompt = build_conversation_prompt(
        message=message,
        conversation_history=conversation_history,
        stats=stats,
        current_outfit_desc=current_outfit_desc,
        character_name=character_name,
        pronoun=pronoun,
    )

    # LLMで応答を生成
    try:
        result = await llm_service.generate_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        response_text = result.content
    except Exception as e:
        # フォールバック応答を使用
        response_text = get_fallback_response(stats.excitement, pronoun)

    # キャラクター応答を保存
    await session_store.add_conversation(session_id, "character", response_text)

    # 心理段階名を取得
    stage_name = get_stage_name(stats.excitement)
    stage_display = get_stage_display_name(stage_name)

    return {
        "session_id": session_id,
        "character_response": response_text,
        "psychological_state": stage_display,
    }


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
    from .game_service import game_service

    async def event_generator() -> AsyncGenerator[dict, None]:
        async for event in game_service.improve_quality_with_stream(
            session_id=session_id,
        ):
            yield {
                "event": event.type,
                "data": json.dumps(event.data, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


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
    attribute_text: str = Query(..., min_length=1, max_length=100, description="属性テキスト"),
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
