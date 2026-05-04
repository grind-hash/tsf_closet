"""Multi-character persistence API router (spec 005).

Endpoints (all under /api/game prefix when registered in app.py):

- GET    /game/session/{sid}/characters
- POST   /game/session/{sid}/characters
- PUT    /game/session/{sid}/characters/{cid}
- DELETE /game/session/{sid}/characters/{cid}
- POST   /game/session/{sid}/characters/from-preset/{preset_id}
- POST   /game/characters/generate-tags
- GET    /game/character-presets
- POST   /game/character-presets
- PUT    /game/character-presets/{preset_id}
- DELETE /game/character-presets/{preset_id}
"""

from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..databases.base import async_session_factory
from ..databases.models import Session as SessionORM
from ..models import (
    CharacterPresetListResponse,
    CharacterPresetRead,
    CharacterPresetUpdate,
    GenerateTagsRequest,
    GenerateTagsResponse,
    GenerateTagsResultItem,
    PresetCreateFromCharacter,
    PresetCreateRaw,
    SessionCharacterCreate,
    SessionCharacterListResponse,
    SessionCharacterRead,
    SessionCharacterUpdate,
)
from ..services.character_service import (
    CharacterLimitExceededError,
    CharacterPresetService,
    SessionCharacterService,
)
from ..services.llm_service import LLMServiceError, llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", tags=["MultiCharacter"])


async def _ensure_session_exists(session_id: str) -> None:
    async with async_session_factory() as db:
        stmt = select(SessionORM.id).where(SessionORM.id == session_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "session_not_found", "code": "session_not_found"},
            )


def _serialize_character(record) -> SessionCharacterRead:
    return SessionCharacterRead(
        id=record.id,
        session_id=record.session_id,
        slot_index=record.slot_index,
        name=record.name,
        appearance_natural=record.appearance_natural,
        appearance_tags=record.appearance_tags,
        position=record.position,  # type: ignore[arg-type]
        source_preset_id=record.source_preset_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _serialize_preset(record) -> CharacterPresetRead:
    return CharacterPresetRead(
        id=record.id,
        name=record.name,
        appearance_natural=record.appearance_natural,
        appearance_tags=record.appearance_tags,
        default_position=record.default_position,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---------------------------------------------------------------------------
# Session-scoped character endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/session/{session_id}/characters",
    response_model=SessionCharacterListResponse,
    summary="List characters in a session",
)
async def list_session_characters(
    session_id: str,
) -> SessionCharacterListResponse:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        records = await SessionCharacterService.list_for_session(db, session_id)
    return SessionCharacterListResponse(
        characters=[_serialize_character(r) for r in records],
    )


@router.post(
    "/session/{session_id}/characters",
    response_model=SessionCharacterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a character in a session",
)
async def create_session_character(
    session_id: str,
    payload: SessionCharacterCreate,
) -> SessionCharacterRead:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        try:
            record = await SessionCharacterService.create_in_session(
                db,
                session_id,
                name=payload.name,
                appearance_natural=payload.appearance_natural,
                appearance_tags=payload.appearance_tags,
                position=payload.position,
                slot_index=payload.slot_index,
                source_preset_id=payload.source_preset_id,
            )
        except CharacterLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "detail": "character_limit_exceeded",
                    "code": "character_limit_exceeded",
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"detail": str(exc), "code": "validation_error"},
            ) from exc
        await db.commit()
        await db.refresh(record)
        return _serialize_character(record)


@router.put(
    "/session/{session_id}/characters/{character_id}",
    response_model=SessionCharacterRead,
    summary="Update a character",
)
async def update_session_character_endpoint(
    session_id: str,
    character_id: str,
    payload: SessionCharacterUpdate,
) -> SessionCharacterRead:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        patch = payload.model_dump(exclude_none=True)
        try:
            record = await SessionCharacterService.update(db, character_id, **patch)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"detail": str(exc), "code": "validation_error"},
            ) from exc
        if record is None or record.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "character_not_found", "code": "character_not_found"},
            )
        await db.commit()
        await db.refresh(record)
        return _serialize_character(record)


@router.delete(
    "/session/{session_id}/characters/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a character",
)
async def delete_session_character_endpoint(
    session_id: str,
    character_id: str,
) -> None:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        ok = await SessionCharacterService.delete(db, character_id)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "character_not_found", "code": "character_not_found"},
            )
        await db.commit()


@router.post(
    "/session/{session_id}/characters/from-preset/{preset_id}",
    response_model=SessionCharacterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a character from a preset",
)
async def add_character_from_preset(
    session_id: str,
    preset_id: str,
) -> SessionCharacterRead:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        try:
            record = await SessionCharacterService.apply_preset_to_session(
                db, session_id, preset_id
            )
        except LookupError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "preset_not_found", "code": "preset_not_found"},
            )
        except CharacterLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "detail": "character_limit_exceeded",
                    "code": "character_limit_exceeded",
                },
            ) from exc
        await db.commit()
        await db.refresh(record)
        return _serialize_character(record)


# ---------------------------------------------------------------------------
# Tag-generation tool
# ---------------------------------------------------------------------------


@router.post(
    "/characters/generate-tags",
    response_model=GenerateTagsResponse,
    summary="Batch generate NovelAI-style tags for N characters in one LLM call",
)
async def generate_character_tags(
    payload: GenerateTagsRequest,
) -> GenerateTagsResponse:
    items = [
        {"id": item.id, "name": item.name, "natural": item.natural}
        for item in payload.items
    ]
    try:
        results = await llm_service.generate_character_tags_batch(items)
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": str(exc), "code": "llm_failure"},
        ) from exc
    return GenerateTagsResponse(
        results=[GenerateTagsResultItem(id=r["id"], tags=r["tags"]) for r in results],
    )


# ---------------------------------------------------------------------------
# Preset CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/character-presets",
    response_model=CharacterPresetListResponse,
    summary="List character presets",
)
async def list_character_presets() -> CharacterPresetListResponse:
    async with async_session_factory() as db:
        records = await CharacterPresetService.list_presets(db)
    return CharacterPresetListResponse(
        presets=[_serialize_preset(r) for r in records],
    )


@router.post(
    "/character-presets",
    response_model=CharacterPresetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a preset",
)
async def create_character_preset(
    payload: Union[PresetCreateFromCharacter, PresetCreateRaw],
) -> CharacterPresetRead:
    async with async_session_factory() as db:
        try:
            if isinstance(payload, PresetCreateFromCharacter):
                record = await CharacterPresetService.create_preset_from_character(
                    db,
                    from_character_id=payload.from_character_id,
                    name=payload.name,
                )
            else:
                record = await CharacterPresetService.create_preset_raw(
                    db,
                    name=payload.name,
                    appearance_natural=payload.appearance_natural,
                    appearance_tags=payload.appearance_tags,
                    default_position=payload.default_position,
                )
        except LookupError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": "session_character_not_found",
                    "code": "session_character_not_found",
                },
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"detail": str(exc), "code": "validation_error"},
            ) from exc
        await db.commit()
        await db.refresh(record)
        return _serialize_preset(record)


@router.put(
    "/character-presets/{preset_id}",
    response_model=CharacterPresetRead,
    summary="Update a preset (partial)",
)
async def update_character_preset_endpoint(
    preset_id: str,
    payload: CharacterPresetUpdate,
) -> CharacterPresetRead:
    async with async_session_factory() as db:
        patch = payload.model_dump(exclude_none=True)
        try:
            record = await CharacterPresetService.update_preset(db, preset_id, **patch)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"detail": str(exc), "code": "validation_error"},
            ) from exc
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "preset_not_found", "code": "preset_not_found"},
            )
        await db.commit()
        await db.refresh(record)
        return _serialize_preset(record)


@router.delete(
    "/character-presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a preset",
)
async def delete_character_preset_endpoint(preset_id: str) -> None:
    async with async_session_factory() as db:
        ok = await CharacterPresetService.delete_preset(db, preset_id)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "preset_not_found", "code": "preset_not_found"},
            )
        await db.commit()
