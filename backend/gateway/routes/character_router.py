"""Multi-character persistence API router (spec 005).

Endpoints (all under /api/game prefix when registered in app.py):

- GET    /game/session/{sid}/characters
- POST   /game/session/{sid}/characters
- PUT    /game/session/{sid}/characters/{cid}
- DELETE /game/session/{sid}/characters/{cid}
- POST   /game/session/{sid}/characters/from-preset/{preset_id}
- POST   /game/session/{sid}/characters/from-group/{group_id}
- POST   /game/characters/generate-tags
- POST   /game/characters/generate-profile
- POST   /game/characters/resolve-source
- GET    /game/character-presets
- POST   /game/character-presets
- GET    /game/character-presets/{preset_id}
- PUT    /game/character-presets/{preset_id}
- DELETE /game/character-presets/{preset_id}
- GET    /game/character-presets/{preset_id}/images/{filename}
- POST   /game/character-presets/{preset_id}/portrait/from-source
- POST   /game/character-presets/{preset_id}/portrait/stream (SSE)
- GET    /game/character-group-presets
- POST   /game/character-group-presets
- PUT    /game/character-group-presets/{group_id}
- DELETE /game/character-group-presets/{group_id}
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from ..databases.base import async_session_factory
from ..databases.character_repo import fetch_character_preset
from ..databases.models import Session as SessionORM
from ..schemas.characters import (
    CharacterGroupMember,
    CharacterGroupPresetCreate,
    CharacterGroupPresetListResponse,
    CharacterGroupPresetRead,
    CharacterGroupPresetUpdate,
    CharacterPresetListResponse,
    CharacterPresetPortraitImportResponse,
    CharacterPresetPortraitRequest,
    CharacterPresetRead,
    CharacterPresetUpdate,
    CharacterProfile,
    CharacterProfileGenerateRequest,
    CharacterSourceResolveRequest,
    CharacterSourceResolveResponse,
    CharacterVoice,
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
from ..services.character_preset_portrait import (
    CharacterPresetPortraitError,
    import_preset_portrait,
    preset_image_file,
    preset_portrait_url,
    remove_preset_images,
    stream_preset_portrait,
)
from ..services.character_profile import (
    CharacterProfileGenerationError,
    CharacterSourceNotFoundError,
    generate_character_profile,
    normalize_character_profile,
    resolve_character_source,
)
from ..services.character_service import (
    CharacterGroupPresetService,
    CharacterLimitExceededError,
    CharacterLook,
    CharacterPresetService,
    SessionCharacterService,
    group_members,
    load_character_looks,
    record_profile,
    record_voice,
    resolve_character_look,
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


def _limit_exceeded() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "detail": "character_limit_exceeded",
            "code": "character_limit_exceeded",
        },
    )


def _serialize_profile(record) -> CharacterProfile | None:
    profile = record_profile(record)
    if profile is None:
        return None
    return CharacterProfile.model_validate(normalize_character_profile(profile))


def _serialize_character(
    record, looks: dict[str, CharacterLook] | None = None
) -> SessionCharacterRead:
    _look_tags, look_source, current_tags = resolve_character_look(record, looks)
    look = (looks or {}).get(record.id)
    return SessionCharacterRead(
        id=record.id,
        session_id=record.session_id,
        slot_index=record.slot_index,
        name=record.name,
        appearance_natural=record.appearance_natural,
        appearance_tags=record.appearance_tags,
        position=record.position,  # type: ignore[arg-type]
        is_protagonist=record.is_protagonist,
        appearance_lock=getattr(record, "appearance_lock", False),
        exclude_from_effects=getattr(record, "exclude_from_effects", False),
        source_preset_id=record.source_preset_id,
        negative_tags=record.negative_tags or "",
        profile=_serialize_profile(record),
        on_stage=bool(record.on_stage),
        thumbnail_url=record.thumbnail_url,
        look_source=look_source,  # type: ignore[arg-type]
        current_tags=current_tags,
        stats=look.stats if look is not None else None,
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
        negative_tags=record.negative_tags or "",
        profile=_serialize_profile(record),
        thumbnail_url=record.thumbnail_url,
        avatar_model_id=record.avatar_model_id,
        voice=(
            CharacterVoice.model_validate(voice)
            if (voice := record_voice(record))
            else None
        ),
        portrait_url=preset_portrait_url(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


_PORTRAIT_NOT_FOUND_CODES = {"preset_not_found", "source_not_found", "image_not_found"}


def _portrait_http_error(error: CharacterPresetPortraitError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND
        if error.code in _PORTRAIT_NOT_FOUND_CODES
        else status.HTTP_400_BAD_REQUEST,
        detail={"detail": str(error), "code": error.code},
    )


def _serialize_group(record) -> CharacterGroupPresetRead:
    members: list[CharacterGroupMember] = []
    for member in group_members(record):
        if member["profile"] is not None:
            member = {
                **member,
                "profile": normalize_character_profile(member["profile"]),
            }
        members.append(CharacterGroupMember.model_validate(member))
    return CharacterGroupPresetRead(
        id=record.id,
        name=record.name,
        members=members,
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
        looks = await load_character_looks(db, session_id)
    return SessionCharacterListResponse(
        characters=[_serialize_character(r, looks) for r in records],
    )


@router.post(
    "/session/{session_id}/characters/ensure-protagonist",
    response_model=SessionCharacterListResponse,
    summary="Ensure protagonist session_character exists (FR-010)",
    description=(
        "Idempotently create the protagonist record for the current session "
        "when multi-person mode is active. Resolves identity from the "
        "template character / self-profile / custom metadata (in that order) "
        "and falls back to base_tags when no history JSON exists yet. "
        "Returns the up-to-date character roster."
    ),
)
async def ensure_protagonist_session_character(
    session_id: str,
) -> SessionCharacterListResponse:
    from ..services.character_service import (
        load_session_characters_for_prompt,
        resolve_protagonist_image_identity,
        upsert_protagonist_session_character,
    )
    from ..services.characters import character_manager
    from ..services.game_service import game_service
    from ..services.session import session_store

    await _ensure_session_exists(session_id)

    session = await session_store.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "session_not_found", "code": "session_not_found"},
        )

    character = None
    if session.character_id:
        character = character_manager.get_by_id(session.character_id)

    self_profile: dict | None = None
    if getattr(session, "self_mode", False):
        self_profile = await session_store.get_self_profile()

    custom_metadata = game_service._load_custom_session_metadata(session_id)
    last_history = await session_store.get_latest_history(session_id)
    last_after_description = last_history.after_description if last_history else None

    name, tags = resolve_protagonist_image_identity(
        last_after_description=last_after_description,
        character=character,
        self_profile=self_profile,
        custom_metadata=custom_metadata,
    )

    async with async_session_factory() as db:
        records = await load_session_characters_for_prompt(db, session_id)
        has_protagonist = any(r.is_protagonist for r in records)
        if not has_protagonist and name and tags:
            await upsert_protagonist_session_character(
                db,
                session_id,
                name=name,
                appearance_tags=tags,
            )
            await db.commit()
            records = await load_session_characters_for_prompt(db, session_id)
        looks = await load_character_looks(db, session_id)

    return SessionCharacterListResponse(
        characters=[_serialize_character(r, looks) for r in records],
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
                appearance_lock=payload.appearance_lock,
                exclude_from_effects=payload.exclude_from_effects,
                negative_tags=payload.negative_tags,
                profile=payload.profile.model_dump() if payload.profile else None,
                on_stage=payload.on_stage,
                thumbnail_url=payload.thumbnail_url,
            )
        except CharacterLimitExceededError as exc:
            raise _limit_exceeded() from exc
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
        looks = await load_character_looks(db, session_id)
        return _serialize_character(record, looks)


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
        from ..databases.character_repo import fetch_session_character

        record = await fetch_session_character(db, character_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "character_not_found", "code": "character_not_found"},
            )
        if record.is_protagonist:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "detail": "cannot_delete_protagonist",
                    "code": "cannot_delete_protagonist",
                },
            )
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
    on_stage: bool = Query(True),
) -> SessionCharacterRead:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        try:
            record = await SessionCharacterService.apply_preset_to_session(
                db, session_id, preset_id, on_stage=on_stage
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "preset_not_found", "code": "preset_not_found"},
            ) from exc
        except CharacterLimitExceededError as exc:
            raise _limit_exceeded() from exc
        await db.commit()
        await db.refresh(record)
        return _serialize_character(record)


@router.post(
    "/session/{session_id}/characters/from-group/{group_id}",
    response_model=SessionCharacterListResponse,
    summary="Replace non-protagonist characters with a group preset",
)
async def apply_group_preset_to_session(
    session_id: str,
    group_id: str,
) -> SessionCharacterListResponse:
    await _ensure_session_exists(session_id)
    async with async_session_factory() as db:
        try:
            records = await CharacterGroupPresetService.apply_to_session(
                db, session_id, group_id
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": "group_preset_not_found",
                    "code": "group_preset_not_found",
                },
            ) from exc
        except CharacterLimitExceededError as exc:
            raise _limit_exceeded() from exc
        await db.commit()
        characters = [_serialize_character(r) for r in records]
    return SessionCharacterListResponse(characters=characters)


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
    from ..services.session import session_store

    items = [
        {"id": item.id, "name": item.name, "natural": item.natural}
        for item in payload.items
    ]
    # 本文生成と同じプロバイダ（FEELING_PROVIDER）とユーザーのテキストモデルを使う
    user_settings = await session_store.get_user_settings()
    try:
        results = await llm_service.generate_character_tags_batch(
            items, novelai_model_override=user_settings.get("novelai_text_model")
        )
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": str(exc), "code": "llm_failure"},
        ) from exc
    return GenerateTagsResponse(
        results=[GenerateTagsResultItem(id=r["id"], tags=r["tags"]) for r in results],
    )


@router.post(
    "/characters/generate-profile",
    response_model=CharacterProfile,
    summary="Generate a personality profile for one character",
)
async def generate_character_profile_endpoint(
    payload: CharacterProfileGenerateRequest,
) -> CharacterProfile:
    try:
        profile = await generate_character_profile(
            name=payload.name,
            appearance_natural=payload.appearance_natural,
            appearance_tags=payload.appearance_tags,
            memo=payload.memo,
            include_speech=payload.include_speech,
        )
    except CharacterProfileGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"detail": str(exc), "code": "llm_failure"},
        ) from exc
    return CharacterProfile.model_validate(profile)


@router.post(
    "/characters/resolve-source",
    response_model=CharacterSourceResolveResponse,
    summary="Resolve name and appearance from a session / favorite / Prompt Expander",
)
async def resolve_character_source_endpoint(
    payload: CharacterSourceResolveRequest,
) -> CharacterSourceResolveResponse:
    try:
        resolved = await resolve_character_source(
            session_id=payload.session_id,
            history_id=payload.history_id,
            prompt_expander_entry_id=payload.prompt_expander_entry_id,
        )
    except CharacterSourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": str(exc), "code": "source_not_found"},
        ) from exc
    return CharacterSourceResolveResponse.model_validate(resolved)


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


@router.get(
    "/character-presets/{preset_id}",
    response_model=CharacterPresetRead,
    summary="Get one character preset",
)
async def get_character_preset(preset_id: str) -> CharacterPresetRead:
    async with async_session_factory() as db:
        record = await fetch_character_preset(db, preset_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "preset_not_found", "code": "preset_not_found"},
        )
    return _serialize_preset(record)


@router.post(
    "/character-presets",
    response_model=CharacterPresetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a preset",
)
async def create_character_preset(
    payload: PresetCreateFromCharacter | PresetCreateRaw,
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
                    negative_tags=payload.negative_tags,
                    profile=payload.profile.model_dump() if payload.profile else None,
                    thumbnail_url=payload.thumbnail_url,
                    avatar_model_id=payload.avatar_model_id,
                    voice=payload.voice.model_dump() if payload.voice else None,
                )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": "session_character_not_found",
                    "code": "session_character_not_found",
                },
            ) from exc
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
    remove_preset_images(preset_id)


@router.get(
    "/character-presets/{preset_id}/images/{filename}",
    summary="Serve a character's portrait image",
)
async def get_character_preset_image(preset_id: str, filename: str) -> FileResponse:
    try:
        path = preset_image_file(preset_id, filename)
    except CharacterPresetPortraitError as error:
        raise _portrait_http_error(error) from error
    return FileResponse(path)


@router.post(
    "/character-presets/{preset_id}/portrait/from-source",
    response_model=CharacterPresetPortraitImportResponse,
    summary="Use an image from a session / favorite / Prompt Expander as the portrait",
)
async def import_character_preset_portrait(
    preset_id: str, payload: CharacterSourceResolveRequest
) -> CharacterPresetPortraitImportResponse:
    try:
        record, resolved = await import_preset_portrait(
            preset_id,
            session_id=payload.session_id,
            history_id=payload.history_id,
            prompt_expander_entry_id=payload.prompt_expander_entry_id,
        )
    except CharacterPresetPortraitError as error:
        raise _portrait_http_error(error) from error
    return CharacterPresetPortraitImportResponse(
        preset=_serialize_preset(record),
        source=CharacterSourceResolveResponse.model_validate(resolved),
    )


@router.post(
    "/character-presets/{preset_id}/portrait/stream",
    summary="Draw the character's portrait from its appearance tags (SSE)",
)
async def stream_character_preset_portrait(
    preset_id: str,
    request: CharacterPresetPortraitRequest | None = Body(default=None),
) -> EventSourceResponse:
    options = request or CharacterPresetPortraitRequest()

    def _error_event(error: Exception) -> dict:
        return {
            "event": "error",
            "data": json.dumps(
                {
                    "code": getattr(error, "code", "internal_error"),
                    "message": str(error) or type(error).__name__,
                },
                ensure_ascii=False,
            ),
        }

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in stream_preset_portrait(
                preset_id, use_precise_reference=options.use_precise_reference
            ):
                data = event["data"]
                if event["event"] == "portrait_image":
                    data = {
                        "preset": _serialize_preset(data["preset"]).model_dump(
                            mode="json"
                        )
                    }
                yield {
                    "event": event["event"],
                    "data": json.dumps(data, ensure_ascii=False),
                }
        except CharacterPresetPortraitError as error:
            yield _error_event(error)
        except Exception as error:  # noqa: BLE001 - SSE には他に伝える経路が無い
            logger.exception("character preset portrait stream failed")
            yield _error_event(error)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Group preset CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/character-group-presets",
    response_model=CharacterGroupPresetListResponse,
    summary="List cast combinations (group presets)",
)
async def list_character_group_presets() -> CharacterGroupPresetListResponse:
    async with async_session_factory() as db:
        records = await CharacterGroupPresetService.list_groups(db)
        groups = [_serialize_group(r) for r in records]
    return CharacterGroupPresetListResponse(groups=groups)


@router.post(
    "/character-group-presets",
    response_model=CharacterGroupPresetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save the session's non-protagonist cast as a group preset",
)
async def create_character_group_preset(
    payload: CharacterGroupPresetCreate,
) -> CharacterGroupPresetRead:
    await _ensure_session_exists(payload.from_session_id)
    async with async_session_factory() as db:
        record = await CharacterGroupPresetService.create_from_session(
            db, name=payload.name, session_id=payload.from_session_id
        )
        await db.commit()
        await db.refresh(record)
        return _serialize_group(record)


@router.put(
    "/character-group-presets/{group_id}",
    response_model=CharacterGroupPresetRead,
    summary="Rename a group preset or overwrite it with a session's cast",
)
async def update_character_group_preset_endpoint(
    group_id: str,
    payload: CharacterGroupPresetUpdate,
) -> CharacterGroupPresetRead:
    if payload.from_session_id:
        await _ensure_session_exists(payload.from_session_id)
    async with async_session_factory() as db:
        record = await CharacterGroupPresetService.update_group(
            db,
            group_id,
            name=payload.name,
            from_session_id=payload.from_session_id,
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": "group_preset_not_found",
                    "code": "group_preset_not_found",
                },
            )
        await db.commit()
        await db.refresh(record)
        return _serialize_group(record)


@router.delete(
    "/character-group-presets/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a group preset",
)
async def delete_character_group_preset_endpoint(group_id: str) -> None:
    async with async_session_factory() as db:
        ok = await CharacterGroupPresetService.delete_group(db, group_id)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "detail": "group_preset_not_found",
                    "code": "group_preset_not_found",
                },
            )
        await db.commit()
