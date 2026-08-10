"""独立アドベンチャーモードのAPI。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..services.adventure_service import (
    AdventureError,
    AdventureImagePromptOutput,
    adventure_service,
)

router = APIRouter(prefix="/adventure", tags=["Adventure"])


class AdventureSetupGenerateRequest(BaseModel):
    source_session_id: str = Field(min_length=1)
    source_history_id: str | None = None
    preset: Literal["infiltration", "escape", "negotiation", "disguise"]


class AdventureCreateRequest(BaseModel):
    source_session_id: str = Field(min_length=1)
    source_history_id: str | None = None
    preset: Literal["infiltration", "escape", "negotiation", "disguise"]
    custom_setup: str = Field(default="", max_length=1000)
    scenario_setting: str = Field(default="", max_length=600)
    scenario_objective: str = Field(default="", max_length=600)
    scenario_constraints: list[str] = Field(default_factory=list, max_length=4)
    scenario_template_id: str | None = Field(default=None, max_length=80)
    replay_run_id: str | None = Field(default=None, max_length=80)
    # 既定OFF: ユーザーが明示ONしない限り精密参照でAnlasを消費しない
    use_precise_reference: bool = False
    # 既定OFF: OFF時は左上ポートレートのみ更新し、背景合成シーンは初回のみ生成
    enable_composite_scene: bool = False


class AdventureSettingsUpdateRequest(BaseModel):
    use_precise_reference: bool
    enable_composite_scene: bool


class AdventureTurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=80)
    user_input: str = Field(min_length=1, max_length=1000)
    input_kind: Literal["choice", "free_text"] = "free_text"


class AdventureImageRequest(BaseModel):
    scene_tags: str = Field(default="", max_length=1800)
    player_tags: str = Field(default="", max_length=1200)
    npc_tags: list[str] = Field(default_factory=list, max_length=3)
    redraw_from_reference: bool = True


def _http_error(error: AdventureError) -> HTTPException:
    status = (
        404
        if error.code in {"run_not_found", "source_not_found", "image_not_found"}
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
            preset=request.preset,
        )
    except AdventureError as error:
        raise _http_error(error) from error


@router.post("/runs", status_code=201)
async def create_run(request: AdventureCreateRequest) -> dict:
    try:
        return await adventure_service.create_run(
            source_session_id=request.source_session_id,
            source_history_id=request.source_history_id,
            preset=request.preset,
            custom_setup=request.custom_setup,
            scenario_setting=request.scenario_setting,
            scenario_objective=request.scenario_objective,
            scenario_constraints=request.scenario_constraints,
            scenario_template_id=request.scenario_template_id,
            replay_run_id=request.replay_run_id,
            use_precise_reference=request.use_precise_reference,
            enable_composite_scene=request.enable_composite_scene,
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


@router.patch("/runs/{run_id}/settings")
async def update_run_settings(
    run_id: str, request: AdventureSettingsUpdateRequest
) -> dict:
    try:
        return await adventure_service.update_run_settings(
            run_id,
            use_precise_reference=request.use_precise_reference,
            enable_composite_scene=request.enable_composite_scene,
        )
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
            image = await adventure_service.generate_image(
                run_id,
                redraw_from_reference=options.redraw_from_reference,
                prompt_override=prompt_override,
            )
            yield {"event": "image", "data": json.dumps(image, ensure_ascii=False)}
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
