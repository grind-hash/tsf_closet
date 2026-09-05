"""独立アドベンチャーモードのAPI。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from ..consts.adventure_bgm import get_bgm_catalog, resolve_bgm_audio_path
from ..consts.adventure_narration import (
    NARRATION_PRONOUN_DEFAULT,
    NARRATION_PRONOUN_MAX_LENGTH,
    NARRATION_VOICE_DEFAULT,
    NarrationVoice,
)
from ..consts.adventure_romance import (
    ROMANCE_DAYS_MAX,
    ROMANCE_PLAYER_NAME_MAX_LENGTH,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_TALK_INPUT_MAX,
)
from ..consts.adventure_setup import SCENARIO_CONSTRAINTS_MAX_ITEMS
from ..consts.adventure_speech import (
    PARTNER_SPEECH_STYLE_MAX_LENGTH,
    SPEECH_CUSTOM_MAX_LENGTH,
    SPEECH_STYLE_DEFAULT,
    SpeechStyle,
)
from ..consts.adventure_turns import (
    ADVENTURE_TURNS_DEFAULT,
    ADVENTURE_TURNS_MAX,
    ADVENTURE_TURNS_MIN,
)
from ..services.adventure_service import (
    AdventureError,
    AdventureImagePromptOutput,
    adventure_service,
)

# scenario_max_turns の受理上限。romance は日数×2 を手数として送るため、
# 通常プリセットの上限(ADVENTURE_TURNS_MAX)より広く取る。
# 非 romance の超過分はサービス側の clamp_generated_max_turns が丸める
SCENARIO_MAX_TURNS_REQUEST_MAX = max(
    ADVENTURE_TURNS_MAX, ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY
)

router = APIRouter(prefix="/adventure", tags=["Adventure"])

# run 単位で上書きできる NovelAI 画像モデル（consts/novelai_models.py と同期）
AdventureImageModel = Literal[
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
]


class AdventureSetupGenerateRequest(BaseModel):
    # 開始素材はゲームセッション（＋履歴時点）か Prompt Expander エントリのどちらか。
    # 両方あれば Prompt Expander エントリを優先する
    source_session_id: str | None = Field(default=None, min_length=1)
    source_history_id: str | None = None
    source_prompt_expander_entry_id: str | None = Field(default=None, max_length=80)
    preset: Literal["infiltration", "escape", "negotiation", "disguise", "romance"]

    @model_validator(mode="after")
    def _require_source(self) -> AdventureSetupGenerateRequest:
        if not self.source_session_id and not self.source_prompt_expander_entry_id:
            raise ValueError(
                "source_session_id か source_prompt_expander_entry_id のいずれかが必要です"
            )
        return self

    # 自動生成のゴール文面は「N手以内に〜」という尺で書かれるため、
    # 案の生成時点でもターン予算を渡す
    scenario_max_turns: int = Field(
        default=ADVENTURE_TURNS_DEFAULT,
        ge=ADVENTURE_TURNS_MIN,
        le=SCENARIO_MAX_TURNS_REQUEST_MAX,
    )
    # ユーザーが入力済みの舞台・ゴール・制約。空でなければ生成の下書きとして
    # LLM に渡し、意味を保ったまま仕上げ・補完させる（AdventureCreateRequest と同じ上限）
    scenario_setting: str = Field(default="", max_length=600)
    scenario_objective: str = Field(default="", max_length=600)
    scenario_constraints: list[str] = Field(
        default_factory=list, max_length=SCENARIO_CONSTRAINTS_MAX_ITEMS
    )
    # 対面会話モード(romance 専用)。ゴール文面を日数でなくターン数で書かせる
    companion_mode: bool = False


class AdventureCreateRequest(BaseModel):
    source_session_id: str | None = Field(default=None, min_length=1)
    source_history_id: str | None = None
    source_prompt_expander_entry_id: str | None = Field(default=None, max_length=80)
    preset: Literal["infiltration", "escape", "negotiation", "disguise", "romance"]
    custom_setup: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _require_source(self) -> AdventureCreateRequest:
        # リプレイ（replay_run_id）は元 run から素材を引き継ぐため素材未指定を許す
        if (
            not self.source_session_id
            and not self.source_prompt_expander_entry_id
            and not self.replay_run_id
        ):
            raise ValueError(
                "source_session_id か source_prompt_expander_entry_id のいずれかが必要です"
            )
        return self

    scenario_setting: str = Field(default="", max_length=600)
    scenario_objective: str = Field(default="", max_length=600)
    scenario_constraints: list[str] = Field(
        default_factory=list, max_length=SCENARIO_CONSTRAINTS_MAX_ITEMS
    )
    scenario_template_id: str | None = Field(default=None, max_length=80)
    replay_run_id: str | None = Field(default=None, max_length=80)
    # 自動生成タイプのみで使用。作品シナリオはテンプレJSON、
    # リプレイは元 run の max_turns を引き継ぐ
    scenario_max_turns: int = Field(
        default=ADVENTURE_TURNS_DEFAULT,
        ge=ADVENTURE_TURNS_MIN,
        le=SCENARIO_MAX_TURNS_REQUEST_MAX,
    )
    # 語りの人称。既定は従来どおりの二人称
    narration_voice: NarrationVoice = NARRATION_VOICE_DEFAULT
    # first_person のときだけ使う一人称語
    narration_pronoun: str = Field(
        default=NARRATION_PRONOUN_DEFAULT,
        min_length=1,
        max_length=NARRATION_PRONOUN_MAX_LENGTH,
    )
    # 主人公のセリフの口調。既定は丁寧語
    player_speech_style: SpeechStyle = SPEECH_STYLE_DEFAULT
    # custom のときだけ使う自由入力
    player_speech_custom: str = Field(default="", max_length=SPEECH_CUSTOM_MAX_LENGTH)
    # 既定OFF: ユーザーが明示ONしない限り精密参照でAnlasを消費しない
    use_precise_reference: bool = False
    # 既定OFF: OFF時は中央の立ち絵のみ更新し、背景合成シーンは初回のみ生成
    enable_composite_scene: bool = False
    # 衣装レイヤー考慮。ONなら外衣に覆われた下着を画像タグから除外する
    respect_clothing_layers: bool = False
    # romance の主人公テンプレートキャラクター。未指定なら既定(char1)
    romance_player_character_id: str | None = Field(default=None, max_length=40)
    # romance の主人公を特定セッション時点の変身状態にする場合に指定。
    # session_id があればテンプレートキャラクターより優先される
    romance_player_session_id: str | None = Field(default=None, max_length=80)
    romance_player_history_id: str | None = Field(default=None, max_length=80)
    # romance の主人公の呼び名(攻略対象がセリフで呼ぶ名前)。空なら
    # テンプレートキャラクター名またはセッションの主人公名を使う
    romance_player_name: str = Field(
        default="", max_length=ROMANCE_PLAYER_NAME_MAX_LENGTH
    )
    # romance の攻略対象の口調。空なら人物像からLLMが自動で決める
    romance_partner_speech_style: str = Field(
        default="", max_length=PARTNER_SPEECH_STYLE_MAX_LENGTH
    )
    # この run 専用の NovelAI 画像モデル。未指定ならグローバル設定に従う
    image_model: AdventureImageModel | None = None
    # 対面会話モード(romance 専用。他プリセットでは無視される)。
    # ONなら手番の画像は背景(現在地変化時のみ)と攻略対象の立ち絵だけになる
    companion_mode: bool = False
    # 対面会話モードで攻略対象の立ち絵の代わりに描く 3D アバター(VRM)の登録 ID
    companion_avatar_id: str | None = Field(default=None, max_length=80)
    # 持ち物システム(既定 OFF、全プリセット)。作品シナリオでは無視される
    inventory_enabled: bool = False


class AdventureSettingsUpdateRequest(BaseModel):
    use_precise_reference: bool
    enable_composite_scene: bool
    # 未指定なら既存の run 設定を維持する
    respect_clothing_layers: bool | None = None
    player_speech_style: SpeechStyle | None = None
    player_speech_custom: str | None = Field(
        default=None, max_length=SPEECH_CUSTOM_MAX_LENGTH
    )
    # romance 以外の run では無視される
    partner_speech_style: str | None = Field(
        default=None, max_length=PARTNER_SPEECH_STYLE_MAX_LENGTH
    )
    # "default" で run 単位の上書きを解除。未指定(None)なら既存値を維持する
    image_model: Literal["default"] | AdventureImageModel | None = None
    # 対面会話モード。未指定なら既存値を維持する(romance 以外では無視)
    companion_mode: bool | None = None
    # 3D アバター。"none" で解除、登録 ID で設定。未指定(None)なら既存値を維持する
    companion_avatar_id: str | None = Field(default=None, max_length=80)
    # 持ち物システム。未指定なら既存値を維持する(作品シナリオでは無視)
    inventory_enabled: bool | None = None


class AdventureTalkRequest(BaseModel):
    # トークモード(手番を消費しない会話)の1メッセージ。romance 専用
    user_input: str = Field(min_length=1, max_length=ROMANCE_TALK_INPUT_MAX)


class AdventureRealityRulesUpdateRequest(BaseModel):
    # 一覧を丸ごと置き換える。件数・表記の正規化はサービス側で行うため、
    # ここの上限は明らかに異常な量を弾くためだけのもの
    rules: list[str] = Field(default_factory=list, max_length=64)


class AdventureItemActionRequest(BaseModel):
    # 持ち物パネルの行動。item_id は所持品の ID、target は渡す相手(NPC 名)
    item_id: str = Field(min_length=1, max_length=40)
    action: Literal["give", "use", "wear", "unwear", "discard"]
    target: str | None = Field(default=None, max_length=60)


class AdventurePromptPreviewRequest(BaseModel):
    # 「この入力で送信したら何が送られるか」を組み立てるための仮の入力
    user_input: str = Field(default="", max_length=2000)
    input_kind: Literal[
        "choice",
        "free_text",
        "reality_alter",
        "gift",
        "work",
        "confess",
        "item_action",
    ] = "free_text"
    gift_id: str | None = Field(default=None, max_length=40)
    item_action: AdventureItemActionRequest | None = None


class AdventureRewindRequest(BaseModel):
    # この手番の完了時点まで巻き戻す(それ以降のターンを削除する)
    turn_number: int = Field(ge=0)


class AdventureTurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=80)
    user_input: str = Field(min_length=1, max_length=1000)
    # reality_alter はサーバ側で「現実改変：〜」を検出したときにも設定される。
    # gift / work / confess は romance プリセット専用の行動
    input_kind: Literal[
        "choice",
        "free_text",
        "reality_alter",
        "gift",
        "work",
        "confess",
        "item_action",
    ] = "free_text"
    # romance のプレゼント購入で贈る品を機械可読 ID で指定する
    gift_id: str | None = Field(default=None, max_length=40)
    # 持ち物パネルの行動(input_kind=item_action のとき必須)
    item_action: AdventureItemActionRequest | None = None
    # false のとき主人公の立ち絵の毎ターン生成を省略する。
    # 精密参照OFFかつ非合成モードの run でのみ有効
    generate_portrait: bool = True
    # false のとき攻略対象(romance)の立ち絵の毎ターン生成を省略する。条件は同上
    generate_partner_portrait: bool = True
    # false のとき、この手番では新しい手掛かりを抽出しない。判定処理自体は
    # 走るため時間短縮はわずか。作品シナリオの決定論的な手掛かりには影響しない
    generate_clues: bool = True


class AdventureImageRequest(BaseModel):
    scene_tags: str = Field(default="", max_length=1800)
    player_tags: str = Field(default="", max_length=1200)
    npc_tags: list[str] = Field(default_factory=list, max_length=3)
    redraw_from_reference: bool = True
    # portrait は立ち絵だけを作り直す。生成失敗ターンからの復旧に使う。
    # partner は romance の攻略対象の立ち絵だけを作り直す(対面会話モードの↻)
    target: Literal["scene", "portrait", "partner"] = "scene"


def _http_error(error: AdventureError) -> HTTPException:
    status = (
        404
        if error.code
        in {"run_not_found", "source_not_found", "image_not_found", "avatar_not_found"}
        else 400
    )
    return HTTPException(
        status_code=status, detail={"code": error.code, "message": str(error)}
    )


@router.get("/templates")
async def list_templates() -> dict:
    return {"templates": await adventure_service.list_templates()}


@router.post("/setup/generate")
async def generate_setup(request: AdventureSetupGenerateRequest) -> dict:
    try:
        return await adventure_service.generate_setup(
            source_session_id=request.source_session_id,
            source_history_id=request.source_history_id,
            source_prompt_expander_entry_id=request.source_prompt_expander_entry_id,
            preset=request.preset,
            max_turns=request.scenario_max_turns,
            draft_setting=request.scenario_setting,
            draft_objective=request.scenario_objective,
            draft_constraints=request.scenario_constraints,
            companion_mode=request.companion_mode,
        )
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs", status_code=201)
async def create_run(request: AdventureCreateRequest) -> dict:
    try:
        return await adventure_service.create_run(
            source_session_id=request.source_session_id,
            source_history_id=request.source_history_id,
            source_prompt_expander_entry_id=request.source_prompt_expander_entry_id,
            preset=request.preset,
            custom_setup=request.custom_setup,
            scenario_setting=request.scenario_setting,
            scenario_objective=request.scenario_objective,
            scenario_constraints=request.scenario_constraints,
            scenario_template_id=request.scenario_template_id,
            replay_run_id=request.replay_run_id,
            scenario_max_turns=request.scenario_max_turns,
            narration_voice=request.narration_voice,
            narration_pronoun=request.narration_pronoun,
            player_speech_style=request.player_speech_style,
            player_speech_custom=request.player_speech_custom,
            use_precise_reference=request.use_precise_reference,
            enable_composite_scene=request.enable_composite_scene,
            respect_clothing_layers=request.respect_clothing_layers,
            romance_player_character_id=request.romance_player_character_id,
            romance_player_session_id=request.romance_player_session_id,
            romance_player_history_id=request.romance_player_history_id,
            romance_player_name=request.romance_player_name,
            romance_partner_speech_style=request.romance_partner_speech_style,
            image_model=request.image_model,
            companion_mode=request.companion_mode,
            companion_avatar_id=request.companion_avatar_id,
            inventory_enabled=request.inventory_enabled,
        )
    except AdventureError as error:
        raise _http_error(error) from error


@router.get("/runs")
async def list_runs() -> dict:
    return {"runs": await adventure_service.list_runs()}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    try:
        return await adventure_service.get_run(run_id)
    except AdventureError as error:
        raise _http_error(error) from error


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    try:
        await adventure_service.delete_run(run_id)
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs/{run_id}/choices/regenerate")
async def regenerate_choices(run_id: str) -> dict:
    try:
        return await adventure_service.regenerate_choices(run_id)
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs/{run_id}/rewind")
async def rewind_run(run_id: str, request: AdventureRewindRequest) -> dict:
    try:
        return await adventure_service.rewind_to_turn(run_id, request.turn_number)
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs/{run_id}/epilogue")
async def start_epilogue(run_id: str) -> dict:
    try:
        return await adventure_service.start_epilogue(run_id)
    except AdventureError as error:
        raise _http_error(error) from error


@router.patch("/runs/{run_id}/settings")
async def update_run_settings(
    run_id: str, request: AdventureSettingsUpdateRequest
) -> dict:
    try:
        return await adventure_service.update_run_settings(
            run_id,
            use_precise_reference=request.use_precise_reference,
            enable_composite_scene=request.enable_composite_scene,
            respect_clothing_layers=request.respect_clothing_layers,
            player_speech_style=request.player_speech_style,
            player_speech_custom=request.player_speech_custom,
            partner_speech_style=request.partner_speech_style,
            image_model=request.image_model,
            companion_mode=request.companion_mode,
            companion_avatar_id=request.companion_avatar_id,
            inventory_enabled=request.inventory_enabled,
        )
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs/{run_id}/preview-prompt")
async def preview_turn_prompts(
    run_id: str, request: AdventurePromptPreviewRequest
) -> dict:
    try:
        return await adventure_service.preview_turn_prompts(
            run_id,
            user_input=request.user_input,
            input_kind=request.input_kind,
            gift_id=request.gift_id,
            item_action=request.item_action.model_dump()
            if request.item_action
            else None,
        )
    except AdventureError as error:
        raise _http_error(error) from error


@router.patch("/runs/{run_id}/reality-rules")
async def update_reality_rules(
    run_id: str, request: AdventureRealityRulesUpdateRequest
) -> dict:
    try:
        return await adventure_service.update_reality_rules(run_id, request.rules)
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs/{run_id}/turns/stream")
async def play_turn(run_id: str, request: AdventureTurnRequest) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in adventure_service.stream_turn(
                run_id=run_id,
                client_turn_id=request.client_turn_id,
                user_input=request.user_input,
                input_kind=request.input_kind,
                gift_id=request.gift_id,
                generate_portrait=request.generate_portrait,
                generate_partner_portrait=request.generate_partner_portrait,
                generate_clues=request.generate_clues,
                item_action=request.item_action.model_dump()
                if request.item_action
                else None,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except AdventureError as error:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": error.code,
                        "message": str(error),
                        "phase": "narrative",
                        "retryable": error.code == "invalid_model_output",
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/talk/stream")
async def talk_stream(
    run_id: str, request: AdventureTalkRequest
) -> EventSourceResponse:
    """トークモード: 手番を消費せずに攻略対象と会話する(romance 専用)。"""

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in adventure_service.stream_talk(
                run_id=run_id, user_input=request.user_input
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except AdventureError as error:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": error.code,
                        "message": str(error),
                        "phase": "talk",
                        "retryable": error.code == "invalid_model_output",
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/image/stream")
async def regenerate_image(
    run_id: str, request: AdventureImageRequest | None = None
) -> EventSourceResponse:
    options = request or AdventureImageRequest()
    prompt_override = (
        AdventureImagePromptOutput(
            scene_tags=options.scene_tags,
            player_tags=options.player_tags,
            npc_tags=[tag for tag in options.npc_tags if tag.strip()],
        )
        if options.scene_tags.strip() and options.player_tags.strip()
        else None
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            yield {
                "event": "status",
                "data": json.dumps({"phase": "image_generation"}, ensure_ascii=False),
            }
            if options.target == "portrait":
                portrait = await adventure_service.generate_portrait(
                    run_id,
                    redraw_from_reference=options.redraw_from_reference,
                    prompt_override=prompt_override,
                )
                cost_usd = portrait.pop("cost_usd", None)
                yield {
                    "event": "portrait_image",
                    "data": json.dumps(portrait, ensure_ascii=False),
                }
            elif options.target == "partner":
                partner = await adventure_service.generate_partner_portrait(run_id)
                cost_usd = partner.pop("cost_usd", None)
                yield {
                    "event": "partner_image",
                    "data": json.dumps(partner, ensure_ascii=False),
                }
            else:
                image = await adventure_service.generate_image(
                    run_id,
                    redraw_from_reference=options.redraw_from_reference,
                    prompt_override=prompt_override,
                )
                cost_usd = image.pop("cost_usd", None)
                yield {"event": "image", "data": json.dumps(image, ensure_ascii=False)}
            if cost_usd:
                yield {
                    "event": "cost",
                    "data": json.dumps({"cost_usd": cost_usd}, ensure_ascii=False),
                }
            yield {
                "event": "complete",
                "data": json.dumps({"status": "complete"}, ensure_ascii=False),
            }
        except AdventureError as error:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "code": error.code,
                        "message": str(error),
                        "phase": "image_generation",
                        "retryable": True,
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.get("/images/{run_id}/{filename}")
async def get_image(run_id: str, filename: str) -> FileResponse:
    try:
        await adventure_service.get_run_orm(run_id)
        return FileResponse(adventure_service.image_file(run_id, filename))
    except AdventureError as error:
        raise _http_error(error) from error


@router.get("/bgm")
async def get_bgm_tracks() -> dict:
    """BGMカタログを返す。ファイル名・説明・出所表記はBGMテスト画面の表示に使う。
    LLM とのやり取りには semantic key しか使わず、この endpoint は経由しない。"""
    catalog = get_bgm_catalog()
    return {
        "default_key": catalog.resolved_default_key(),
        "tracks": [
            {
                "key": track.key,
                "file": track.file,
                "description": track.description,
                "credit": track.credit,
                "url": f"/adventure/bgm/audio/{track.file}",
            }
            for track in catalog.tracks
        ],
    }


@router.get("/bgm/audio/{filename}")
async def get_bgm_audio(filename: str) -> FileResponse:
    path = resolve_bgm_audio_path(filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "bgm_not_found", "message": f"unknown bgm: {filename}"},
        )
    return FileResponse(path, media_type="audio/ogg")
