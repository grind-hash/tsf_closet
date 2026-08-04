"""TSF Bloomer 育成モードの API。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..services.bloomer_service import BloomerError, bloomer_service
from ..services.image_generation import image_service
from ..services.session import DEFAULT_USER_ID

router = APIRouter(prefix="/bloomer", tags=["Bloomer"])


def _http_error(error: BloomerError) -> HTTPException:
    status = (
        404
        if error.code in {"not_found", "image_not_found"}
        else 409
        if error.code in {"run_ended", "once_per_day", "too_many_runs"}
        else 403
        if error.code
        in {"nsfw_locked", "stage_locked", "not_owned", "mood_too_low", "trust_too_low"}
        else 400
    )
    return HTTPException(status_code=status, detail=str(error))


# ---------------------------------------------------------------------------
# リクエスト / レスポンス モデル
# ---------------------------------------------------------------------------


class RunCreateRequest(BaseModel):
    origin: str = Field(default="preset", pattern=r"^(session|preset)$")
    name: str = Field(min_length=1, max_length=40)
    source_session_id: str | None = Field(default=None, max_length=80)
    character_id: str | None = Field(default=None, max_length=80)


class ActionRequest(BaseModel):
    action_key: str = Field(min_length=1, max_length=60)
    language: str = Field(default="ja", max_length=4)
    user_text: str | None = Field(default=None, max_length=500)


class AdvanceDayRequest(BaseModel):
    language: str = Field(default="ja", max_length=4)


class MilestoneRequest(BaseModel):
    choice_key: str = Field(min_length=1, max_length=40)
    language: str = Field(default="ja", max_length=4)


class EquipOutfitRequest(BaseModel):
    outfit_key: str = Field(min_length=1, max_length=60)


class ImageStreamRequest(BaseModel):
    language: str = Field(default="ja", max_length=4)


def _run_to_dict(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "origin": run.origin,
        "source_session_id": run.source_session_id,
        "character_id": run.character_id,
        "name": run.name,
        "day": run.day,
        "max_days": run.max_days,
        "actions_left": run.actions_left,
        "stage": run.stage,
        "nsfw_stage": run.nsfw_stage,
        "mood": run.mood,
        "stamina": run.stamina,
        "trust": run.trust,
        "axes": json.loads(run.axes_json) if run.axes_json else {},
        "growth": json.loads(run.growth_json) if run.growth_json else {},
        "wardrobe": json.loads(run.wardrobe_json) if run.wardrobe_json else [],
        "equipped_outfit": run.equipped_outfit,
        "decisions": json.loads(run.decisions_json) if run.decisions_json else {},
        "status": run.status,
        "ending_key": run.ending_key,
        "initial_image_path": run.initial_image_path,
        "current_image_path": run.current_image_path,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "day": event.day,
        "kind": event.kind,
        "action_key": event.action_key,
        "payload": json.loads(event.payload_json) if event.payload_json else {},
        "narration": event.narration,
        "image_path": event.image_path,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD エンドポイント
# ---------------------------------------------------------------------------


@router.post("/runs")
async def create_run(body: RunCreateRequest) -> dict[str, Any]:
    try:
        run = await bloomer_service.create_run(
            user_id=DEFAULT_USER_ID,
            origin=body.origin,
            name=body.name,
            source_session_id=body.source_session_id,
            character_id=body.character_id,
        )
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return _run_to_dict(run)


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    runs = await bloomer_service.list_runs(user_id=DEFAULT_USER_ID)
    return [_run_to_dict(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    try:
        run = await bloomer_service.get_run(run_id, user_id=DEFAULT_USER_ID)
    except BloomerError as exc:
        raise _http_error(exc) from exc
    data = _run_to_dict(run)
    data["events"] = [_event_to_dict(e) for e in (run.events or [])]
    return data


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    try:
        await bloomer_service.delete_run(run_id, user_id=DEFAULT_USER_ID)
    except BloomerError as exc:
        raise _http_error(exc) from exc


# ---------------------------------------------------------------------------
# アクション
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/actions")
async def perform_action(run_id: str, body: ActionRequest) -> dict[str, Any]:
    try:
        result = await bloomer_service.perform_action(
            run_id=run_id,
            user_id=DEFAULT_USER_ID,
            action_key=body.action_key,
            language=body.language,
            user_text=body.user_text,
        )
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return {
        "refused": result["refused"],
        "narration": result["narration"],
        "event_id": result["event_id"],
        "run": _run_to_dict(result["run"]),
        "stat_before": result.get("stat_before"),
        "stat_after": result.get("stat_after"),
    }


# ---------------------------------------------------------------------------
# 日進め
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/advance-day")
async def advance_day(run_id: str, body: AdvanceDayRequest) -> dict[str, Any]:
    try:
        result = await bloomer_service.advance_day(
            run_id=run_id,
            user_id=DEFAULT_USER_ID,
            language=body.language,
        )
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return {
        "nightly_narration": result["nightly_narration"],
        "stage_up": result["stage_up"],
        "stage_narration": result["stage_narration"],
        "ended": result["ended"],
        "ending_key": result["ending_key"],
        "ending_narration": result["ending_narration"],
        "milestone_pending": result["milestone_pending"],
        "run": _run_to_dict(result["run"]),
    }


# ---------------------------------------------------------------------------
# 節目
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/milestone")
async def resolve_milestone(run_id: str, body: MilestoneRequest) -> dict[str, Any]:
    try:
        result = await bloomer_service.resolve_milestone(
            run_id=run_id,
            user_id=DEFAULT_USER_ID,
            choice_key=body.choice_key,
            language=body.language,
        )
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return {
        "flag": result["flag"],
        "event_id": result["event_id"],
        "run": _run_to_dict(result["run"]),
    }


# ---------------------------------------------------------------------------
# 衣装
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/outfit")
async def equip_outfit(run_id: str, body: EquipOutfitRequest) -> dict[str, Any]:
    try:
        result = await bloomer_service.equip_outfit(
            run_id=run_id,
            user_id=DEFAULT_USER_ID,
            outfit_key=body.outfit_key,
        )
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return {
        "outfit_key": result["outfit_key"],
        "run": _run_to_dict(result["run"]),
    }


# ---------------------------------------------------------------------------
# キャラクタープリセット一覧
# ---------------------------------------------------------------------------


@router.get("/characters")
async def list_characters() -> list[dict[str, Any]]:
    """images/characters/characters.json からキャラクター一覧を返す。"""
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "images"
        / "characters"
        / "characters.json"
    )
    if not path.is_file():
        return []
    import json

    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# カタログ
# ---------------------------------------------------------------------------


@router.get("/catalog")
async def get_catalog() -> dict[str, Any]:
    from ..consts.bloomer_consts import ALL_ACTIONS, MILESTONE_CATALOG, OUTFIT_CATALOG

    return {
        "actions": ALL_ACTIONS,
        "outfits": OUTFIT_CATALOG,
        "milestones": {str(k): v for k, v in MILESTONE_CATALOG.items()},
    }


# ---------------------------------------------------------------------------
# 画像 SSE ストリーム
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/image/stream")
async def image_stream(run_id: str, body: ImageStreamRequest) -> EventSourceResponse:
    try:
        run = await bloomer_service.get_run(run_id, user_id=DEFAULT_USER_ID)
    except BloomerError as exc:
        raise _http_error(exc) from exc

    async def _generate() -> AsyncGenerator[dict[str, str], None]:
        try:
            yield {
                "event": "status",
                "data": json.dumps({"message": "画像タグを生成中..."}),
            }

            tags = await bloomer_service.get_image_tags(run, language=body.language)

            yield {
                "event": "status",
                "data": json.dumps({"message": "画像を生成中..."}),
            }

            current_bytes: bytes | None = None
            current_path = bloomer_service.resolve_stored_image_path(
                run.current_image_path
            )
            if current_path is not None:
                current_bytes = current_path.read_bytes()

            initial_bytes: bytes | None = None
            initial_path = bloomer_service.resolve_stored_image_path(
                run.initial_image_path
            )
            if initial_path is not None:
                initial_bytes = initial_path.read_bytes()

            result = await image_service.generate_image(
                tags,
                image_bytes=current_bytes,
                reference_image_bytes=initial_bytes,
                mask_bytes=None,
                provider_override=None,
                negative_prompt=None,
                i2i_strength_override=None,
                i2i_noise_override=None,
                nsfw_mode=run.nsfw_stage >= 2,
                character_references=[initial_bytes] if initial_bytes else [],
                seed=None,
                characters=None,
                size_override=None,
                novelai_model_override=None,
            )

            image_bytes = result.images[0]
            image_path = bloomer_service.save_image(run_id, image_bytes)
            await bloomer_service.update_current_image(
                run_id, DEFAULT_USER_ID, image_path
            )

            import base64

            b64 = base64.b64encode(image_bytes).decode()
            yield {
                "event": "image",
                "data": json.dumps({"image_base64": b64, "image_path": image_path}),
            }
            yield {"event": "complete", "data": json.dumps({"image_path": image_path})}

        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(_generate())


# ---------------------------------------------------------------------------
# 画像ファイル配信
# ---------------------------------------------------------------------------


@router.get("/images/{run_id}/{filename}")
async def get_image(run_id: str, filename: str) -> FileResponse:
    try:
        path = bloomer_service.image_file(run_id, filename)
    except BloomerError as exc:
        raise _http_error(exc) from exc
    return FileResponse(path, media_type="image/png")


@router.get("/character-images/{filename}")
async def get_character_image(filename: str) -> FileResponse:
    """images/characters 配下のプリセット画像を配信する。"""
    try:
        path = bloomer_service.character_image_file(filename)
    except BloomerError as exc:
        raise _http_error(exc) from exc
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)
