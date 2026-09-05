"""独立アドベンチャーモードのAPI。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ..consts.adventure_bgm import get_bgm_catalog, resolve_bgm_audio_path
from ..schemas.adventure import (
    AdventureCreateRequest,
    AdventureImageRequest,
    AdventurePromptPreviewRequest,
    AdventureRealityRulesUpdateRequest,
    AdventureRewindRequest,
    AdventureSettingsUpdateRequest,
    AdventureSetupGenerateRequest,
    AdventureTalkRequest,
    AdventureTurnRequest,
)
from ..services.adventure_service import (
    AdventureError,
    AdventureImagePromptOutput,
    adventure_service,
)

router = APIRouter(prefix="/adventure", tags=["Adventure"])


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
