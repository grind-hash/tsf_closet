"""AI箱庭モードの API。

世界(住民・掟・年代記)の作成と、1日進める・掟の切り替え・住民の一言・その場で変身・
アバターの生成を扱う。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..schemas.common import ErrorResponse
from ..schemas.hakoniwa import (
    HakoniwaAvatarRequest,
    HakoniwaCatalogResponse,
    HakoniwaCharacterResidentRequest,
    HakoniwaCreateRequest,
    HakoniwaCustomRuleRequest,
    HakoniwaDayResponse,
    HakoniwaFavoriteRequest,
    HakoniwaGreetingResponse,
    HakoniwaImageResponse,
    HakoniwaLanguageRequest,
    HakoniwaReapplyRequest,
    HakoniwaResidentChangeResponse,
    HakoniwaResidentRequest,
    HakoniwaRuleToggleRequest,
    HakoniwaSettingsRequest,
    HakoniwaTransformRequest,
    HakoniwaWorldListResponse,
    HakoniwaWorldResponse,
)
from ..services.hakoniwa_service import HakoniwaError, hakoniwa_service

router = APIRouter(prefix="/hakoniwa", tags=["hakoniwa"])

_NOT_FOUND_CODES = {
    "world_not_found",
    "resident_not_found",
    "rule_not_found",
    "event_not_found",
    "image_not_found",
    "transformation_not_found",
    "preset_not_found",
    "character_preset_not_found",
}
_UPSTREAM_CODES = {"image_generation_failed", "tag_conversion_failed"}
_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
}

T = TypeVar("T")


def _http_error(error: HakoniwaError) -> HTTPException:
    if error.code in _NOT_FOUND_CODES:
        status = 404
    elif error.code in _UPSTREAM_CODES:
        status = 502
    else:
        status = 400
    return HTTPException(
        status_code=status,
        detail={"error": error.code, "code": error.code, "message": str(error)},
    )


async def _call(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except HakoniwaError as error:
        raise _http_error(error) from error


@router.get(
    "/catalog", response_model=HakoniwaCatalogResponse, summary="プリセットの住民と掟"
)
async def get_catalog(language: str | None = Query(None)) -> HakoniwaCatalogResponse:
    return HakoniwaCatalogResponse(**await hakoniwa_service.catalog(language))


@router.get("/worlds", response_model=HakoniwaWorldListResponse, summary="世界の一覧")
async def list_worlds(language: str | None = Query(None)) -> HakoniwaWorldListResponse:
    return HakoniwaWorldListResponse(
        worlds=await hakoniwa_service.list_worlds(language)
    )


@router.post(
    "/worlds",
    response_model=HakoniwaWorldResponse,
    summary="世界を作る",
    description="プリセットの住民と登録キャラクター(立ち絵を写して住民にする)で世界を作る",
    responses=_ERROR_RESPONSES,
)
async def create_world(request: HakoniwaCreateRequest) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.create_world(
            request.name,
            request.preset_ids,
            [item.model_dump() for item in request.characters],
            request.language,
        )
    )
    return HakoniwaWorldResponse(**world)


@router.get(
    "/worlds/{world_id}",
    response_model=HakoniwaWorldResponse,
    summary="世界を取得",
    responses=_ERROR_RESPONSES,
)
async def get_world(
    world_id: str, language: str | None = Query(None)
) -> HakoniwaWorldResponse:
    return HakoniwaWorldResponse(
        **await _call(hakoniwa_service.get_world(world_id, language))
    )


@router.delete(
    "/worlds/{world_id}",
    status_code=204,
    summary="世界を削除",
    responses=_ERROR_RESPONSES,
)
async def delete_world(world_id: str) -> None:
    await _call(hakoniwa_service.delete_world(world_id))


@router.patch(
    "/worlds/{world_id}/settings",
    response_model=HakoniwaWorldResponse,
    summary="世界の設定(アバター生成の画像モデル)",
    responses=_ERROR_RESPONSES,
)
async def update_settings(
    world_id: str, request: HakoniwaSettingsRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.update_settings(
            world_id, image_model=request.image_model, language=request.language
        )
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/day",
    response_model=HakoniwaDayResponse,
    summary="1日進める",
    description="その日の出来事を3件生成して適用し、日を1つ進める",
    responses=_ERROR_RESPONSES,
)
async def advance_day(
    world_id: str, request: HakoniwaLanguageRequest
) -> HakoniwaDayResponse:
    result = await _call(hakoniwa_service.advance_day(world_id, request.language))
    return HakoniwaDayResponse(**result)


@router.put(
    "/worlds/{world_id}/rules/{card_id}",
    response_model=HakoniwaWorldResponse,
    summary="掟の有効化・解除",
    responses=_ERROR_RESPONSES,
)
async def toggle_rule(
    world_id: str, card_id: str, request: HakoniwaRuleToggleRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.set_rule(world_id, card_id, request.active, request.language)
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/custom-rules",
    response_model=HakoniwaWorldResponse,
    summary="自作の掟を追加",
    responses=_ERROR_RESPONSES,
)
async def add_custom_rule(
    world_id: str, request: HakoniwaCustomRuleRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.add_custom_rule(
            world_id, request.name, request.text, request.language
        )
    )
    return HakoniwaWorldResponse(**world)


@router.patch(
    "/worlds/{world_id}/custom-rules/{rule_id}",
    response_model=HakoniwaWorldResponse,
    summary="自作の掟を編集",
    responses=_ERROR_RESPONSES,
)
async def update_custom_rule(
    world_id: str, rule_id: str, request: HakoniwaCustomRuleRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.update_custom_rule(
            world_id, rule_id, request.name, request.text, request.language
        )
    )
    return HakoniwaWorldResponse(**world)


@router.delete(
    "/worlds/{world_id}/custom-rules/{rule_id}",
    response_model=HakoniwaWorldResponse,
    summary="自作の掟を削除",
    responses=_ERROR_RESPONSES,
)
async def delete_custom_rule(
    world_id: str, rule_id: str, language: str | None = Query(None)
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.delete_custom_rule(world_id, rule_id, language)
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/residents",
    response_model=HakoniwaResidentChangeResponse,
    summary="自作の住民を迎える",
    description="外見の説明が日本語の文章なら、画像タグへ変換して別に持つ",
    responses=_ERROR_RESPONSES,
)
async def add_resident(
    world_id: str, request: HakoniwaResidentRequest
) -> HakoniwaResidentChangeResponse:
    result = await _call(
        hakoniwa_service.add_custom_resident(
            world_id,
            request.model_dump(exclude={"language"}),
            request.language,
        )
    )
    return HakoniwaResidentChangeResponse(**result)


@router.post(
    "/worlds/{world_id}/residents/from-character",
    response_model=HakoniwaResidentChangeResponse,
    summary="登録キャラクターを住民に迎える",
    responses=_ERROR_RESPONSES,
)
async def add_character_resident(
    world_id: str, request: HakoniwaCharacterResidentRequest
) -> HakoniwaResidentChangeResponse:
    result = await _call(
        hakoniwa_service.add_character_resident(
            world_id, request.character_preset_id, request.gender, request.language
        )
    )
    return HakoniwaResidentChangeResponse(**result)


@router.patch(
    "/worlds/{world_id}/residents/{resident_id}",
    response_model=HakoniwaResidentChangeResponse,
    summary="住民を編集",
    responses=_ERROR_RESPONSES,
)
async def update_resident(
    world_id: str, resident_id: str, request: HakoniwaResidentRequest
) -> HakoniwaResidentChangeResponse:
    result = await _call(
        hakoniwa_service.update_resident(
            world_id,
            resident_id,
            request.model_dump(exclude={"language"}),
            request.language,
        )
    )
    return HakoniwaResidentChangeResponse(**result)


@router.delete(
    "/worlds/{world_id}/residents/{resident_id}",
    response_model=HakoniwaWorldResponse,
    summary="住民を外す",
    responses=_ERROR_RESPONSES,
)
async def remove_resident(
    world_id: str, resident_id: str, language: str | None = Query(None)
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.remove_resident(world_id, resident_id, language)
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/greet",
    response_model=HakoniwaGreetingResponse,
    summary="住民の一言",
    responses=_ERROR_RESPONSES,
)
async def greet_resident(
    world_id: str, resident_id: str, request: HakoniwaLanguageRequest
) -> HakoniwaGreetingResponse:
    result = await _call(
        hakoniwa_service.greet(world_id, resident_id, request.language)
    )
    return HakoniwaGreetingResponse(**result)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/avatar",
    response_model=HakoniwaImageResponse,
    summary="住民の姿(通常・ドレス)を生成",
    responses=_ERROR_RESPONSES,
)
async def generate_avatar(
    world_id: str, resident_id: str, request: HakoniwaAvatarRequest
) -> HakoniwaImageResponse:
    result = await _call(
        hakoniwa_service.generate_avatar(
            world_id, resident_id, request.variant, request.language
        )
    )
    return HakoniwaImageResponse(**result)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/transform",
    response_model=HakoniwaDayResponse,
    summary="その場で変身",
    description="指定文を画像タグに変えて新しい姿を生成し、変身と周りの反応を年代記に積む",
    responses=_ERROR_RESPONSES,
)
async def transform_resident(
    world_id: str, resident_id: str, request: HakoniwaTransformRequest
) -> HakoniwaDayResponse:
    result = await _call(
        hakoniwa_service.transform(
            world_id, resident_id, request.instruction, request.language
        )
    )
    return HakoniwaDayResponse(**result)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/transform/clear",
    response_model=HakoniwaWorldResponse,
    summary="変身を解く",
    responses=_ERROR_RESPONSES,
)
async def clear_transform(
    world_id: str, resident_id: str, request: HakoniwaLanguageRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.clear_transform(world_id, resident_id, request.language)
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/transform/reapply",
    response_model=HakoniwaWorldResponse,
    summary="履歴の変身をもう一度使う",
    responses=_ERROR_RESPONSES,
)
async def reapply_transform(
    world_id: str, resident_id: str, request: HakoniwaReapplyRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.reapply_transform(
            world_id, resident_id, request.image, request.language
        )
    )
    return HakoniwaWorldResponse(**world)


@router.put(
    "/worlds/{world_id}/events/{event_id}/favorite",
    response_model=HakoniwaWorldResponse,
    summary="出来事のお気に入り",
    responses=_ERROR_RESPONSES,
)
async def set_favorite(
    world_id: str, event_id: str, request: HakoniwaFavoriteRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.set_favorite(
            world_id, event_id, request.favorite, request.language
        )
    )
    return HakoniwaWorldResponse(**world)


@router.get(
    "/worlds/{world_id}/images/{filename}",
    summary="住民の画像",
    responses={404: {"model": ErrorResponse}},
)
async def get_image(world_id: str, filename: str) -> FileResponse:
    try:
        path = hakoniwa_service.image_file(world_id, filename)
    except HakoniwaError as error:
        raise _http_error(error) from error
    return FileResponse(path, media_type="image/png")
