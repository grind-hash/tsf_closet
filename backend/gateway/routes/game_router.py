"""
ゲームAPIエンドポイント

着せ替えインタラクティブゲームのAPIルーター。
"""

from __future__ import annotations

import json
import base64
import uuid
from datetime import datetime
from typing import AsyncGenerator, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..services.characters import character_manager
from ..models import (
    CharacterListResponse,
    ErrorResponse,
    HistorySelectResponse,
    PlayRequest,
    PlayResponse,
    SessionResetResponse,
    SessionResponse,
    SessionStatsResponse,
    DifficultyResponse,
    DifficultyListResponse,
    GameStartRequest,
    GameStartResponse,
    DIFFICULTY_PRESETS,
    # ギャラリー (T052)
    GalleryResponse,
    GalleryEndingItem,
    # セッション一覧 (001-immersion-enhancement)
    SessionSummary,
    SessionListResponse,
    MaskListResponse,
    MaskSaveRequest,
)
from ..services.session import session_store
from ..services.endings import ENDINGS
from ..services.game_service import GameService
from ..consts.language import normalize_language

router = APIRouter(prefix="/game", tags=["Game"])

SYSTEM_MASK_LABELS = {
    "system_mask_upper_body.png": "上半身マスク（頭部以外）",
    "system_mask_upper_body_and_head.png": "上半身マスク（頭部含む）",
    "system_mask_bottom_body.png": "下半身マスク",
    "system_entire_body_excluding_face.png": "全身マスク（頭部以外）",
    "system_entire_body.png": "全身マスク",
}


def normalize_gender(value: str | None) -> str:
    """性別値を man/woman/other に正規化"""
    if not value:
        return "other"
    normalized = value.strip().lower()
    if normalized in {"man", "male", "男性", "男"}:
        return "man"
    if normalized in {"woman", "female", "女性", "女"}:
        return "woman"
    return "other"


def load_custom_session_metadata(session_id: str) -> dict:
    """カスタムセッションメタデータを読み込む"""
    from ..settings.config import settings

    metadata_path = (
        settings.history_images_dir / "custom" / f"session_{session_id}.json"
    )
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


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
    "/play",
    response_model=PlayResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="着せ替えを実行",
    description="キャラクターに対して着せ替えを実行し、結果画像と心境テキストを返却",
)
async def play_game(request: PlayRequest) -> PlayResponse:
    """着せ替えを実行

    新規開始時: character_id または character_image を指定
    継続プレイ時: session_id を指定
    """
    # インポートを遅延して循環参照を回避
    from ..services.game_service import game_service

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


class CharacterReferenceParam(BaseModel):
    """NovelAI Character Reference parameter."""

    image: str = Field(..., min_length=1, description="Base64 encoded image data")
    type: Literal["character", "style", "character&style"] = Field(
        "character&style", description="Reference type"
    )
    strength: float = Field(1.0, ge=0.0, le=1.0, description="Reference strength")
    fidelity: float = Field(1.0, ge=0.0, le=1.0, description="Reference fidelity")


class PlayStreamRequest(BaseModel):
    """ストリーミング着せ替えリクエスト"""

    instruction: str = Field(
        ..., min_length=1, max_length=500, description="着せ替え指示"
    )
    session_id: Optional[str] = Field(None, description="既存セッションID")
    character_id: Optional[str] = Field(None, description="キャラクターID")
    character_image: Optional[str] = Field(None, description="Base64エンコード画像")
    base_history_id: Optional[str] = Field(None, description="履歴からのベース画像ID")
    costume_image: Optional[str] = Field(None, description="衣装参照画像（Base64）")
    # 変更範囲コントロール
    preserve_elements: Optional[list[str]] = Field(
        None,
        description="保持する要素のリスト (background, hairstyle, pose, expression, accessories)",
    )
    change_scope: str = Field(
        "full", description="変更対象 (full, upper, lower, accessories, shoes)"
    )
    custom_preserve_text: str = Field("", description="カスタム保持指示（自由記述）")
    # 変身タイプ
    transformation_type: str = Field(
        "costume", description="変身タイプ (costume=衣装変更, reality=現実改変)"
    )
    # 007-chat-interactive-ux: 指示タイプ（チャット表示用）
    instruction_type: Optional[str] = Field(
        None,
        description="指示タイプ (dress_up=着せ替え, reality_alter=現実改変, conversation=会話)",
    )
    # NovelAI専用フィールド
    mask_image: Optional[str] = Field(
        None, description="Base64エンコードされたインペイントマスク"
    )
    mask_id: Optional[str] = Field(
        None, description="保存済みマスクID（/game/masks で取得）"
    )
    inpaint_strength: Optional[float] = Field(
        None, description="inpaintImg2ImgStrength (0.05-0.99)"
    )
    inpaint_noise: Optional[float] = Field(None, description="img2img noise (0-0.5)")
    negative_prompt: Optional[str] = Field(
        None, description="NovelAIネガティブプロンプト"
    )
    prompt_override: Optional[str] = Field(
        None, description="LLM生成をスキップしこのプロンプトを使う"
    )
    # ユーザー設定（リクエストごとにオーバーライド可能）
    nsfw_mode: Optional[bool] = Field(
        None, description="NSFWモード（未指定時はセッション設定を使用）"
    )
    difficulty: Optional[str] = Field(
        None, description="難易度（未指定時はセッション設定を使用）"
    )
    language: Optional[str] = Field(
        None, description="応答言語（ja/en、未指定時はユーザー設定を使用）"
    )
    # NovelAI精密参照画像
    character_references: Optional[list[CharacterReferenceParam]] = Field(
        None,
        description="精密参照画像パラメータの配列（NovelAIプロバイダー使用時のみ有効）",
    )
    # Seed for image generation
    seed: Optional[int] = Field(
        None,
        description="画像生成seed値（0〜999999999、未指定時はランダム）",
        ge=0,
        le=999999999,
    )
    # Surroundings image generation toggle
    enable_surroundings_image: bool = Field(
        False,
        description="行動後の周囲状況画像生成を有効にする",
    )
    # Surroundings image: include reactive bystanders
    surroundings_include_people: bool = Field(
        False,
        description="周囲状況画像にリアクションする通行人を含める",
    )


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
            preserve_elements=request.preserve_elements,
            change_scope=request.change_scope,
            custom_preserve_text=request.custom_preserve_text,
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
    from ..settings.config import settings, BASE_DIR

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
    # 既存セッションをリセット
    await session_store.reset_session()

    # キャラクター情報を取得
    character_id = request.character_id
    character = None
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
        all_characters = character_manager.get_all()
        default_char = all_characters[0] if all_characters else None
        if default_char is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no_characters",
                    "message": "利用可能なキャラクターがありません",
                },
            )
        character_id = default_char.id
        character = default_char
        image_path = default_char.image_path

    # 難易度を検証
    difficulty = request.difficulty
    if difficulty not in DIFFICULTY_PRESETS:
        difficulty = "normal"

    # セッションを作成
    session = await session_store.create_session(
        image_path=image_path,
        character_id=character_id,
        self_mode=request.self_mode,
    )

    # セッション統計を作成
    stats = await session_store.create_session_stats(
        session.id, difficulty, request.nsfw_mode
    )

    if character is not None:
        initial_desc = GameService._build_initial_prompt(
            gender=character.gender,
            character=character,
        )
        await session_store.add_history(
            session_id=session.id,
            instruction="初期状態",
            image_data=character_manager.get_image_bytes(character),
            feeling_text="(初期状態)",
            before_description=initial_desc,
            after_description=initial_desc,
        )

    return GameStartResponse(
        session_id=session.id,
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


class CustomStartRequest(BaseModel):
    """カスタム画像でのセッション開始リクエスト"""

    image: str | None = Field(None, description="Base64エンコードされた画像")
    custom_character_id: str | None = Field(
        None, description="再利用するカスタムキャラID"
    )
    difficulty: str = Field("normal", description="難易度")
    nsfw_mode: bool = Field(False, description="NSFWモード")
    name: str = Field("カスタムキャラクター", description="キャラクター名")
    description: str = Field("", description="説明")
    pronoun: str = Field("僕", description="一人称")
    personality: str = Field("", description="パーソナリティ")
    gender: str = Field("other", description="性別 (man/woman/other)")


@router.post(
    "/start-custom",
    response_model=GameStartResponse,
    responses={400: {"model": ErrorResponse}},
    summary="カスタム画像でセッション開始",
    description="ユーザーがアップロードした画像でゲームセッションを開始",
)
async def start_game_custom(request: CustomStartRequest) -> GameStartResponse:
    """カスタム画像でセッションを開始"""
    import base64
    from ..settings.config import settings

    # 既存セッションをリセット
    await session_store.reset_session()

    custom_images_dir = settings.history_images_dir / "custom"
    custom_images_dir.mkdir(parents=True, exist_ok=True)
    custom_image_id = request.custom_character_id or str(uuid.uuid4())
    custom_image_path = custom_images_dir / f"{custom_image_id}.png"

    if request.custom_character_id and custom_image_path.exists():
        image_bytes = custom_image_path.read_bytes()
    else:
        try:
            if not request.image:
                raise ValueError("画像が指定されていません")
            image_data = request.image
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            image_bytes = base64.b64decode(image_data)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_image",
                    "message": f"画像のデコードに失敗しました: {e}",
                },
            ) from e
        custom_image_path.write_bytes(image_bytes)

    # 相対パスを計算（BASE_DIRからの相対パス）
    relative_path = f"data/history_images/custom/{custom_image_id}.png"

    normalized_gender = normalize_gender(request.gender)

    metadata_path = custom_images_dir / f"{custom_image_id}.json"
    metadata_path.write_text(
        json.dumps(
            {
                "id": custom_image_id,
                "name": request.name,
                "description": request.description,
                "pronoun": request.pronoun,
                "personality": request.personality,
                "gender": normalized_gender,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # セッションを作成
    session = await session_store.create_session(
        image_path=relative_path,
        character_id=None,  # カスタム画像なのでキャラクターIDなし
    )

    session_metadata_path = custom_images_dir / f"session_{session.id}.json"
    session_metadata_path.write_text(
        json.dumps(
            {
                "custom_character_id": custom_image_id,
                "name": request.name,
                "description": request.description,
                "pronoun": request.pronoun,
                "personality": request.personality,
                "gender": normalized_gender,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 難易度を検証
    difficulty = request.difficulty
    if difficulty not in DIFFICULTY_PRESETS:
        difficulty = "normal"

    # セッション統計を作成
    stats = await session_store.create_session_stats(
        session.id, difficulty, request.nsfw_mode
    )

    initial_desc = GameService._build_initial_prompt(
        gender=normalized_gender,
    )
    await session_store.add_history(
        session_id=session.id,
        instruction="初期状態",
        image_data=image_bytes,
        feeling_text="(初期状態)",
        before_description=initial_desc,
        after_description=initial_desc,
    )

    return GameStartResponse(
        session_id=session.id,
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
    "/custom-characters",
    summary="作成済みカスタムキャラクター一覧",
    description="保存済みのカスタム画像とメタデータを返却",
)
async def list_custom_characters() -> dict:
    from ..settings.config import settings

    custom_images_dir = settings.history_images_dir / "custom"
    custom_images_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for image_file in sorted(
        custom_images_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        metadata_file = image_file.with_suffix(".json")
        metadata = {}
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        items.append(
            {
                "id": image_file.stem,
                "thumbnail": base64.b64encode(image_file.read_bytes()).decode("utf-8"),
                "name": metadata.get("name", "カスタムキャラクター"),
                "description": metadata.get("description", ""),
                "pronoun": metadata.get("pronoun", "僕"),
                "personality": metadata.get("personality", ""),
                "gender": normalize_gender(metadata.get("gender", "other")),
            }
        )
    return {"characters": items}


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
) -> dict:
    """キャラクターとの会話"""
    from ..services.conversation import (
        build_conversation_prompt,
        get_stage_name,
        get_stage_display_name,
        get_fallback_response,
    )
    from ..services.llm_service import llm_service
    from ..services.conversation_service import conversation_service
    from ..services.characters import character_manager

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
    self_profile = None

    # self_mode: self_profile からプロフィールを上書き
    if getattr(session, "self_mode", False):
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

    # 現在の衣装説明を取得（直近の履歴から）
    current_outfit_desc = ""
    history = await session_store.get_history(session_id)
    if history:
        latest = history[-1]
        current_outfit_desc = latest.after_description or ""

    # ユーザーメッセージを保存
    await session_store.add_conversation(
        session_id, "user", message, instruction_type="conversation"
    )

    # 属性を取得
    attributes = await session_store.get_session_attribute_texts(session_id)
    user_settings = await session_store.get_user_settings()
    language = normalize_language(language or user_settings.get("language"))

    # セッション経緯を取得（着替・改変・行動・会話を時系列マージ）
    session_timeline = await session_store.get_session_timeline(session_id, limit=30)
    # 新しい順 → 時系列順に反転
    session_timeline = list(reversed(session_timeline))

    # プロンプトを構築（self_mode はプロフィールベース、通常はステージベース）
    if getattr(session, "self_mode", False) and self_profile:
        from ..services.self_mode_prompts import build_self_mode_conversation_prompt

        system_prompt, user_prompt = build_self_mode_conversation_prompt(
            message=message,
            conversation_history=conversation_history,
            current_outfit_desc=current_outfit_desc,
            self_profile=self_profile,
            nsfw_mode=stats.nsfw_mode,
            language=language,
            session_timeline=session_timeline,
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
            language=language,
            session_timeline=session_timeline,
        )

    # LLMで応答を生成
    response_text = ""
    try:
        response_text = (
            await conversation_service.generate_with_language_retry(
                llm_service=llm_service,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                language=language,
            )
            or ""
        )
    except Exception:
        response_text = ""

    if not response_text:
        response_text = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)

    # キャラクター応答を保存
    await session_store.add_conversation(session_id, "character", response_text)

    # 心理段階名を取得
    if session.transformation_count == 0:
        stage_display = "未変身"
    else:
        stage_name = get_stage_name(stats.bloom)
        stage_display = get_stage_display_name(stage_name)

    return {
        "session_id": session_id,
        "character_response": response_text,
        "psychological_state": stage_display,
        "language": language,
    }


@router.get(
    "/chat/stream",
    summary="キャラクターと会話（ストリーミング）",
    description="キャラクターにメッセージを送信し、応答をストリーミング取得",
)
async def chat_with_character_stream(
    session_id: str = Query(..., description="セッションID"),
    message: str = Query(..., min_length=1, max_length=500, description="メッセージ"),
    language: str | None = Query(None, description="応答言語 (ja/en)"),
) -> StreamingResponse:
    """キャラクターとの会話（ストリーミング）"""
    import logging
    from ..services.conversation import (
        build_conversation_prompt,
        get_fallback_response,
        is_response_language_valid,
    )
    from ..services.llm_service import llm_service
    from ..services.conversation_service import conversation_service
    from ..services.characters import character_manager

    logger = logging.getLogger(__name__)

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
    self_profile = None

    # self_mode: self_profile からプロフィールを上書き
    if getattr(session, "self_mode", False):
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

    # 現在の衣装説明を取得（直近の履歴から）
    current_outfit_desc = ""
    history = await session_store.get_history(session_id)
    if history:
        latest = history[-1]
        current_outfit_desc = latest.after_description or ""

    # ユーザーメッセージを保存
    await session_store.add_conversation(
        session_id, "user", message, instruction_type="conversation"
    )

    # 属性を取得
    attributes = await session_store.get_session_attribute_texts(session_id)
    user_settings = await session_store.get_user_settings()
    language = normalize_language(language or user_settings.get("language"))

    # セッション経緯を取得（着替・改変・行動・会話を時系列マージ）
    session_timeline = await session_store.get_session_timeline(session_id, limit=30)
    # 新しい順 → 時系列順に反転
    session_timeline = list(reversed(session_timeline))

    # プロンプトを構築（self_mode はプロフィールベース、通常はステージベース）
    if getattr(session, "self_mode", False) and self_profile:
        from ..services.self_mode_prompts import build_self_mode_conversation_prompt

        system_prompt, user_prompt = build_self_mode_conversation_prompt(
            message=message,
            conversation_history=conversation_history,
            current_outfit_desc=current_outfit_desc,
            self_profile=self_profile,
            nsfw_mode=stats.nsfw_mode,
            language=language,
            session_timeline=session_timeline,
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
            language=language,
            session_timeline=session_timeline,
        )

    async def generate_stream():
        """ストリーミング応答を生成"""
        full_response = ""
        try:
            async for chunk in llm_service.generate_feeling_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"

            if not is_response_language_valid(full_response, language):
                retry_prompt = f"{user_prompt}\n\nIMPORTANT: Respond in {'English only' if language == 'en' else 'Japanese only'}."
                try:
                    retry_text = (
                        await conversation_service.generate_with_language_retry(
                            llm_service=llm_service,
                            system_prompt=system_prompt,
                            user_prompt=retry_prompt,
                            language=language,
                        )
                    )
                    if retry_text and is_response_language_valid(retry_text, language):
                        await session_store.add_conversation(
                            session_id, "character", retry_text
                        )
                        yield f"data: {json.dumps({'type': 'error', 'fallback': retry_text, 'language': language})}\n\n"
                        return
                except Exception:
                    pass

                fallback = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)
                await session_store.add_conversation(session_id, "character", fallback)
                yield f"data: {json.dumps({'type': 'error', 'fallback': fallback, 'language': language})}\n\n"
                return

            # キャラクター応答を保存
            await session_store.add_conversation(session_id, "character", full_response)

            # 完了イベント
            yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'language': language})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            # フォールバック応答を使用
            fallback = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)
            await session_store.add_conversation(session_id, "character", fallback)
            yield f"data: {json.dumps({'type': 'error', 'fallback': fallback, 'language': language})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

    return await game_service.preview_prompts(
        session_id=request.session_id,
        instruction=request.instruction,
        transformation_type=request.transformation_type,
        preserve_elements=request.preserve_elements,
        change_scope=request.change_scope,
        custom_preserve_text=request.custom_preserve_text,
    )


# =============================================================================
# マスク管理 (NovelAI向け)
# =============================================================================


@router.get("/masks", response_model=MaskListResponse, summary="マスク一覧取得")
async def list_masks() -> MaskListResponse:
    """システムマスク、履歴マスク、ユーザープリセットを返す"""
    from ..settings.config import settings, BASE_DIR

    system_dir = BASE_DIR / "images" / "masks"
    history_dir = settings.history_masks_dir
    preset_dir = settings.preset_masks_dir
    history_dir.mkdir(parents=True, exist_ok=True)
    preset_dir.mkdir(parents=True, exist_ok=True)

    system_masks = []
    for filename, label in SYSTEM_MASK_LABELS.items():
        path = system_dir / filename
        if path.exists():
            system_masks.append(
                {
                    "id": f"system:{path.name}",
                    "name": label,
                    "type": "system",
                    "url": f"/api/game/masks/system/{path.name}",
                }
            )

    history_masks = []
    files = sorted(
        history_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for f in files[:20]:
        history_masks.append(
            {
                "id": f"history:{f.stem}",
                "name": f.stem,
                "type": "history",
                "url": f"/api/game/masks/history/{f.stem}",
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
        )

    # プリセットマスク一覧取得
    preset_masks = []
    preset_files = sorted(
        preset_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for f in preset_files:
        # メタデータファイルから名前を読み込み
        meta_path = preset_dir / f"{f.stem}.json"
        if meta_path.exists():
            import json

            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta.get("name", f.stem)
            except Exception:
                name = f.stem
        else:
            name = f.stem
        preset_masks.append(
            {
                "id": f"preset:{f.stem}",
                "name": name,
                "type": "preset",
                "url": f"/api/game/masks/preset/{f.stem}",
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
        )

    return MaskListResponse(
        system=system_masks, history=history_masks, presets=preset_masks
    )


@router.post("/masks", response_model=MaskListResponse, summary="マスクを保存")
async def save_mask(request: MaskSaveRequest) -> MaskListResponse:
    """マスクを保存する。nameが指定されている場合はプリセットとして、それ以外は履歴として保存"""
    import json as json_module
    from ..settings.config import settings

    history_dir = settings.history_masks_dir
    preset_dir = settings.preset_masks_dir
    history_dir.mkdir(parents=True, exist_ok=True)
    preset_dir.mkdir(parents=True, exist_ok=True)

    # Base64デコード
    data = request.mask_base64
    if data.startswith("data:"):
        _, data = data.split(",", 1)
    try:
        mask_bytes = base64.b64decode(data)
    except Exception:
        raise HTTPException(status_code=400, detail="mask_base64 が不正です")

    mask_id = uuid.uuid4().hex

    # プリセット名が指定されている場合はプリセットとして保存
    if request.name:
        fname = preset_dir / f"{mask_id}.png"
        fname.write_bytes(mask_bytes)
        # メタデータ保存
        meta_path = preset_dir / f"{mask_id}.json"
        meta_path.write_text(
            json_module.dumps({"name": request.name}, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        # 履歴として保存
        fname = history_dir / f"{mask_id}.png"
        fname.write_bytes(mask_bytes)

        # 上限20件を維持
        files = sorted(
            history_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for old in files[20:]:
            try:
                old.unlink()
            except OSError:
                pass

    # 最新一覧を返す
    return await list_masks()


@router.get("/masks/system/{filename}", summary="システムマスク取得")
async def get_system_mask(filename: str):
    from ..settings.config import BASE_DIR

    if filename not in SYSTEM_MASK_LABELS:
        raise HTTPException(status_code=404, detail="mask not found")
    path = BASE_DIR / "images" / "masks" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="mask not found")
    return FileResponse(path, media_type="image/png")


@router.get("/masks/history/{mask_id}", summary="履歴マスク取得")
async def get_history_mask(mask_id: str):
    from ..settings.config import settings

    safe_id = mask_id.replace("/", "").replace("\\", "")
    path = settings.history_masks_dir / f"{safe_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="mask not found")
    return FileResponse(path, media_type="image/png")


@router.get("/masks/preset/{mask_id}", summary="プリセットマスク取得")
async def get_preset_mask(mask_id: str):
    """プリセットマスク画像を取得"""
    from ..settings.config import settings

    safe_id = mask_id.replace("/", "").replace("\\", "")
    path = settings.preset_masks_dir / f"{safe_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="preset mask not found")
    return FileResponse(path, media_type="image/png")


@router.delete(
    "/masks/preset/{mask_id}",
    response_model=MaskListResponse,
    summary="プリセットマスク削除",
)
async def delete_preset_mask(mask_id: str) -> MaskListResponse:
    """プリセットマスクを削除し、最新のマスク一覧を返す"""
    from ..settings.config import settings

    safe_id = mask_id.replace("/", "").replace("\\", "")
    png_path = settings.preset_masks_dir / f"{safe_id}.png"
    meta_path = settings.preset_masks_dir / f"{safe_id}.json"

    if not png_path.exists():
        raise HTTPException(status_code=404, detail="preset mask not found")

    # 画像ファイル削除
    try:
        png_path.unlink()
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to delete preset mask")

    # メタデータファイル削除（存在する場合）
    if meta_path.exists():
        try:
            meta_path.unlink()
        except OSError:
            pass  # メタデータ削除失敗は無視

    return await list_masks()


# ---------- Anlas balance ----------


class AnlasBalanceResponse(BaseModel):
    """Anlas balance response model."""

    fixed_anlas: int | None = None
    purchased_anlas: int | None = None
    total_anlas: int | None = None


@router.get(
    "/anlas",
    response_model=AnlasBalanceResponse,
    summary="Anlas残高取得",
    description="NovelAIのAnlas残高を取得する。NovelAI以外のプロバイダー使用時はnullを返す。",
)
async def get_anlas_balance() -> AnlasBalanceResponse:
    """Get the current Anlas balance from NovelAI."""
    from ..settings.config import settings as app_settings

    if app_settings.image_provider.lower() != "novelai":
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
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch Anlas balance: {e}",
        )
