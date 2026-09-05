"""
ゲームAPIエンドポイント

着せ替えインタラクティブゲームのAPIルーター。
"""

from __future__ import annotations

import base64
import contextlib
import json
import math
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..consts.language import normalize_language
from ..models import DIFFICULTY_PRESETS
from ..schemas.characters import CharacterListResponse
from ..schemas.common import ErrorResponse
from ..schemas.conversation import SuggestInstructionRequest, SuggestInstructionResponse
from ..schemas.gallery import GalleryEndingItem, GalleryResponse
from ..schemas.novelai import MaskListResponse, MaskSaveRequest
from ..schemas.parameters import (
    DifficultyListResponse,
    DifficultyResponse,
    SessionStatsResponse,
)
from ..schemas.play import PlayRequest
from ..schemas.session import (
    BranchSessionRequest,
    BranchSessionResponse,
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
from ..services.characters import character_manager
from ..services.endings import ENDINGS
from ..services.game_service import GameService
from ..services.session import session_store
from ..services.settings_service import settings_service

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
    session_id: str | None = Field(None, description="既存セッションID")
    character_id: str | None = Field(None, description="キャラクターID")
    character_image: str | None = Field(None, description="Base64エンコード画像")
    base_history_id: str | None = Field(None, description="履歴からのベース画像ID")
    costume_image: str | None = Field(None, description="衣装参照画像（Base64）")
    # 変身タイプ
    transformation_type: str = Field(
        "costume", description="変身タイプ (costume=衣装変更, reality=現実改変)"
    )
    # 007-chat-interactive-ux: 指示タイプ（チャット表示用）
    instruction_type: str | None = Field(
        None,
        description=(
            "指示タイプ (dress_up=着せ替え, reality_alter=現実改変, "
            "conversation=会話, action=行動, image_only=画像のみ)"
        ),
    )
    # NovelAI専用フィールド
    mask_image: str | None = Field(
        None, description="Base64エンコードされたインペイントマスク"
    )
    mask_id: str | None = Field(
        None, description="保存済みマスクID（/game/masks で取得）"
    )
    inpaint_strength: float | None = Field(
        None, description="inpaintImg2ImgStrength (0.05-0.99)"
    )
    inpaint_noise: float | None = Field(None, description="img2img noise (0-0.5)")
    negative_prompt: str | None = Field(None, description="NovelAIネガティブプロンプト")
    prompt_override: str | None = Field(
        None, description="LLM生成をスキップしこのプロンプトを使う"
    )
    # ユーザー設定（リクエストごとにオーバーライド可能）
    nsfw_mode: bool | None = Field(
        None, description="NSFWモード（未指定時はセッション設定を使用）"
    )
    difficulty: str | None = Field(
        None, description="難易度（未指定時はセッション設定を使用）"
    )
    language: str | None = Field(
        None, description="応答言語（ja/en、未指定時はユーザー設定を使用）"
    )
    # NovelAI精密参照画像
    character_references: list[CharacterReferenceParam] | None = Field(
        None,
        description="精密参照画像パラメータの配列（NovelAIプロバイダー使用時のみ有効）",
    )
    # Seed for image generation
    seed: int | None = Field(
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
    # Clothing color consistency toggle
    clothing_color_consistency: bool = Field(
        False,
        description="服の色の一貫性を保つ実験的機能",
    )
    respect_clothing_layers: bool = Field(
        False,
        description="外衣による下着・身体属性の被覆を画像と心境で考慮する",
    )
    # Multiple people in image generation toggle
    enable_multiple_people: bool = Field(
        False,
        description="複数人表示を有効にする実験的機能",
    )
    # CharacterPanel (session_characters) injection toggle.
    # False の場合、複数人表示の GLM-4.6 ルール緩和はそのまま保ちつつ、
    # session_characters パネルからのプロンプト注入をバイパスする（v0.5.0 以前の旧仕様）。
    use_character_panel: bool = Field(
        True,
        description="登場人物パネルの情報を画像生成プロンプトに注入するか",
    )
    use_memory: bool = Field(
        False,
        description="保存済みメモリテキスト（ユーザーの嗜好傾向）を生成に反映するか",
    )
    use_play_memory: bool = Field(
        False, description="セッション単位のプレイメモを生成に反映するか"
    )
    use_history_lookback: bool | None = Field(
        None,
        description="履歴遡及を利用するか（未指定時は操作種別の既定値を使用）",
    )
    image_only_text_to_image: bool = Field(
        False,
        description=(
            "画像のみモードで前画像を使わず text-to-image で生成する"
            "（image_only 以外の指示タイプでは無視）"
        ),
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
            if event.type == "complete" and request.use_play_memory:
                from ..services.play_memory_service import play_memory_service

                result_text = "\n".join(
                    part
                    for part in (
                        str(event.data.get("after_desc", "")),
                        str(event.data.get("feeling_text", "")),
                    )
                    if part
                )
                updated = await play_memory_service.update_rolling(
                    event.data.get("session_id") or request.session_id or "",
                    interaction_type=request.instruction_type or "dress_up",
                    user_input=request.instruction,
                    result_text=result_text,
                    language=normalize_language(request.language),
                )
                event.data["play_memory_update"] = "updated" if updated else "failed"
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
    base_tags: str = Field("", description="Danbooru形式の外見タグ (英語)")
    self_mode: bool = Field(False, description="自分自身モード")


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
                "base_tags": request.base_tags,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # セッションを作成
    session = await session_store.create_session(
        image_path=relative_path,
        character_id=None,  # カスタム画像なのでキャラクターIDなし
        self_mode=request.self_mode,
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
                "base_tags": request.base_tags,
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
        base_tags=request.base_tags,
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
                "base_tags": metadata.get("base_tags", ""),
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
    from ..services.characters import character_manager
    from ..services.conversation import (
        build_conversation_prompt,
        get_fallback_response,
        get_stage_display_name,
        get_stage_name,
    )
    from ..services.conversation_service import conversation_service
    from ..services.history_context import resolve_history_lookback_enabled
    from ..services.llm_service import llm_service

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

    lookback_enabled = resolve_history_lookback_enabled(
        use_history_lookback, instruction_type="conversation"
    )
    lookback_count = settings_service.get_history_lookback_count(session_id)
    conversation_limit = (
        math.ceil(lookback_count * 1.2)
        if getattr(session, "self_mode", False)
        else lookback_count
    )
    conversation_history = (
        await session_store.get_conversation_history(session_id, conversation_limit)
        if lookback_enabled
        else []
    )

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

    # 属性を取得
    attributes = await session_store.get_session_attribute_texts(session_id)
    user_settings = await session_store.get_user_settings()
    language = normalize_language(language or user_settings.get("language"))
    effective_novelai_text_model = user_settings.get("novelai_text_model")

    timeline_limit = math.ceil(lookback_count * 1.6)
    session_timeline = (
        await session_store.get_recent_instructions(session_id, limit=timeline_limit)
        if lookback_enabled
        else []
    )

    # 現在の発言を過去履歴へ含めないよう、タイムライン取得後に保存する
    user_conv = await session_store.add_conversation(
        session_id, "user", message, instruction_type="conversation"
    )
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
            language=language,
            session_timeline=session_timeline,
            lookback_count=lookback_count,
        )
    if use_play_memory:
        from ..services.play_memory_service import play_memory_service

        system_prompt += await play_memory_service.build_context(
            session_id, enabled=True, language=language
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
                novelai_model_override=effective_novelai_text_model,
            )
            or ""
        )
    except Exception:
        response_text = ""

    if not response_text:
        response_text = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)

    # キャラクター応答を保存
    char_conv = await session_store.add_conversation(
        session_id, "character", response_text
    )
    play_memory_update = "skipped"
    if use_play_memory:
        from ..services.play_memory_service import play_memory_service

        play_memory_update = (
            "updated"
            if await play_memory_service.update_rolling(
                session_id,
                interaction_type="conversation",
                user_input=message,
                result_text=response_text,
                language=language,
            )
            else "failed"
        )

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
        "user_conversation_id": getattr(user_conv, "id", None),
        "character_conversation_id": getattr(char_conv, "id", None),
        "play_memory_update": play_memory_update,
    }


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
) -> StreamingResponse:
    """キャラクターとの会話（ストリーミング）"""
    import logging

    from ..services.characters import character_manager
    from ..services.conversation import (
        build_conversation_prompt,
        get_fallback_response,
        is_response_language_valid,
    )
    from ..services.conversation_service import conversation_service
    from ..services.history_context import resolve_history_lookback_enabled
    from ..services.llm_service import llm_service

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

    lookback_enabled = resolve_history_lookback_enabled(
        use_history_lookback, instruction_type="conversation"
    )
    lookback_count = settings_service.get_history_lookback_count(session_id)
    conversation_limit = (
        math.ceil(lookback_count * 1.2)
        if getattr(session, "self_mode", False)
        else lookback_count
    )
    conversation_history = (
        await session_store.get_conversation_history(session_id, conversation_limit)
        if lookback_enabled
        else []
    )

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

    # 属性を取得
    attributes = await session_store.get_session_attribute_texts(session_id)
    user_settings = await session_store.get_user_settings()
    language = normalize_language(language or user_settings.get("language"))
    effective_novelai_text_model = user_settings.get("novelai_text_model")

    timeline_limit = math.ceil(lookback_count * 1.6)
    session_timeline = (
        await session_store.get_recent_instructions(session_id, limit=timeline_limit)
        if lookback_enabled
        else []
    )

    # 現在の発言を過去履歴へ含めないよう、タイムライン取得後に保存する
    user_conv = await session_store.add_conversation(
        session_id, "user", message, instruction_type="conversation"
    )
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
            language=language,
            session_timeline=session_timeline,
            lookback_count=lookback_count,
        )
    if use_play_memory:
        from ..services.play_memory_service import play_memory_service

        system_prompt += await play_memory_service.build_context(
            session_id, enabled=True, language=language
        )

    async def update_conversation_memory(response_text: str) -> str:
        """保存済み会話を自動メモへ反映する。"""
        if not use_play_memory:
            return "skipped"
        from ..services.play_memory_service import play_memory_service

        updated = await play_memory_service.update_rolling(
            session_id,
            interaction_type="conversation",
            user_input=message,
            result_text=response_text,
            language=language,
        )
        return "updated" if updated else "failed"

    async def generate_stream():
        """ストリーミング応答を生成"""
        full_response = ""
        try:
            async for chunk in llm_service.generate_feeling_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                novelai_model_override=effective_novelai_text_model,
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
                            novelai_model_override=effective_novelai_text_model,
                        )
                    )
                    if retry_text and is_response_language_valid(retry_text, language):
                        char_conv = await session_store.add_conversation(
                            session_id, "character", retry_text
                        )
                        memory_status = await update_conversation_memory(retry_text)
                        yield f"data: {json.dumps({'type': 'error', 'fallback': retry_text, 'language': language, 'user_conversation_id': user_conv.id, 'character_conversation_id': char_conv.id, 'play_memory_update': memory_status})}\n\n"
                        return
                except Exception:
                    pass

                fallback = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)
                char_conv = await session_store.add_conversation(
                    session_id, "character", fallback
                )
                memory_status = await update_conversation_memory(fallback)
                yield f"data: {json.dumps({'type': 'error', 'fallback': fallback, 'language': language, 'user_conversation_id': user_conv.id, 'character_conversation_id': char_conv.id, 'play_memory_update': memory_status})}\n\n"
                return

            # キャラクター応答を保存
            char_conv = await session_store.add_conversation(
                session_id, "character", full_response
            )
            memory_status = await update_conversation_memory(full_response)

            # 完了イベント
            yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'language': language, 'user_conversation_id': user_conv.id, 'character_conversation_id': char_conv.id, 'play_memory_update': memory_status})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            # フォールバック応答を使用
            fallback = get_fallback_response(stats.bloom, pronoun, stats.nsfw_mode)
            char_conv = await session_store.add_conversation(
                session_id, "character", fallback
            )
            yield f"data: {json.dumps({'type': 'error', 'fallback': fallback, 'language': language, 'user_conversation_id': user_conv.id, 'character_conversation_id': char_conv.id})}\n\n"

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
    import base64

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
    from ..settings.config import BASE_DIR, settings

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
    except Exception as exc:
        raise HTTPException(status_code=400, detail="mask_base64 が不正です") from exc

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
            with contextlib.suppress(OSError):
                old.unlink()

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
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Failed to delete preset mask"
        ) from exc

    # メタデータファイル削除（存在する場合）
    if meta_path.exists():
        with contextlib.suppress(OSError):  # メタデータ削除失敗は無視
            meta_path.unlink()

    return await list_masks()


# ---------- Anlas balance ----------


class AnlasUsageModel(BaseModel):
    """NovelAI V5 usage limit model."""

    percent: int
    is_negative: bool = False
    time_until_next_percent: int = 0


class AnlasBalanceResponse(BaseModel):
    """Anlas balance response model."""

    fixed_anlas: int | None = None
    purchased_anlas: int | None = None
    total_anlas: int | None = None
    usage: AnlasUsageModel | None = None


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


class GenerateBaseTagsRequest(BaseModel):
    """外見タグ自動生成リクエスト"""

    name: str = Field("", description="キャラクター名")
    description: str = Field("", description="外見の説明")
    gender: str = Field("other", description="性別 (man/woman/other)")
    personality: str = Field("", description="パーソナリティ")


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
