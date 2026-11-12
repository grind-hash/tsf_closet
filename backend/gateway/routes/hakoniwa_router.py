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
    HakoniwaChatHistoryResponse,
    HakoniwaChatRequest,
    HakoniwaChatResponse,
    HakoniwaContinueEventRequest,
    HakoniwaCreateRequest,
    HakoniwaCustomRuleRequest,
    HakoniwaDayResponse,
    HakoniwaDirectedEventRequest,
    HakoniwaFavoriteRequest,
    HakoniwaFurnitureRequest,
    HakoniwaGreetingResponse,
    HakoniwaImageResponse,
    HakoniwaInterventionRequest,
    HakoniwaLanguageRequest,
    HakoniwaLookRequest,
    HakoniwaLookResponse,
    HakoniwaRandomResidentsRequest,
    HakoniwaRandomResidentsResponse,
    HakoniwaReapplyRequest,
    HakoniwaResidentChangeResponse,
    HakoniwaResidentRequest,
    HakoniwaResidentTagsRequest,
    HakoniwaRuleLookTagsRequest,
    HakoniwaRuleToggleRequest,
    HakoniwaSettingsRequest,
    HakoniwaTagsResponse,
    HakoniwaTouchRequest,
    HakoniwaTouchResponse,
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
    "area_not_found",
    "furniture_not_found",
}
_UPSTREAM_CODES = {
    "image_generation_failed",
    "tag_conversion_failed",
    "tags_failed",
    "event_generation_failed",
}
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
            dissonance_enabled=request.dissonance_enabled,
            custom_residents=[item.model_dump() for item in request.custom_residents],
            experiment_theme=(
                request.experiment_theme.model_dump()
                if request.experiment_theme
                else None
            ),
        )
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/random-residents",
    response_model=HakoniwaRandomResidentsResponse,
    summary="おまかせの住民を組む",
    description=(
        "世界を作る前の住民構成をランダムに組む(状態は変えない)。テキストモデルで作り、"
        "作れなければ語彙の組み合わせで組み立てる。1人の入れ替えは count=1 と、"
        "ほかの住民の名前を exclude_names で渡す"
    ),
    responses=_ERROR_RESPONSES,
)
async def random_residents(
    request: HakoniwaRandomResidentsRequest,
) -> HakoniwaRandomResidentsResponse:
    result = await _call(
        hakoniwa_service.random_residents(
            request.count, request.exclude_names, request.language
        )
    )
    return HakoniwaRandomResidentsResponse(**result)


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
    summary="世界の設定(アバター生成の画像モデル・世界の違和感)",
    responses=_ERROR_RESPONSES,
)
async def update_settings(
    world_id: str, request: HakoniwaSettingsRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.update_settings(
            world_id,
            image_model=request.image_model,
            dissonance_enabled=request.dissonance_enabled,
            world_memo=request.world_memo,
            experiment_theme=(
                request.experiment_theme.model_dump()
                if request.experiment_theme is not None
                else None
            ),
            language=request.language,
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
    response_model=HakoniwaDayResponse,
    summary="掟の有効化・解除",
    description=(
        "掟を切り替える。世界の違和感が到達点に達したら、住民が書き手へ呼びかける"
        "出来事(対面)を new_events で返す"
    ),
    responses=_ERROR_RESPONSES,
)
async def toggle_rule(
    world_id: str, card_id: str, request: HakoniwaRuleToggleRequest
) -> HakoniwaDayResponse:
    result = await _call(
        hakoniwa_service.set_rule(
            world_id,
            card_id,
            request.active,
            request.language,
            area_id=request.area_id,
        )
    )
    return HakoniwaDayResponse(**result)


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
            world_id,
            request.name,
            request.text,
            request.appearance_text,
            request.language,
            appearance_tags=request.appearance_tags,
            body_gender=request.body_gender,
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
            world_id,
            rule_id,
            request.name,
            request.text,
            request.appearance_text,
            request.language,
            appearance_tags=request.appearance_tags,
            body_gender=request.body_gender,
        )
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/custom-rules/{rule_id}/look",
    response_model=HakoniwaLookResponse,
    summary="自作の掟の姿を生成",
    description=(
        "住民の人数分の姿を1人ずつ生成する。見た目のタグが無ければ掟の本文から考える。"
        "regenerate=false なら、今の見た目でまだ生成していない住民だけ"
    ),
    responses=_ERROR_RESPONSES,
)
async def generate_rule_look(
    world_id: str, rule_id: str, request: HakoniwaLookRequest
) -> HakoniwaLookResponse:
    result = await _call(
        hakoniwa_service.generate_rule_look(
            world_id,
            rule_id,
            regenerate=request.regenerate,
            language=request.language,
        )
    )
    return HakoniwaLookResponse(**result)


@router.post(
    "/worlds/{world_id}/combo-look",
    response_model=HakoniwaLookResponse,
    summary="複合の姿を生成",
    description=(
        "いま重なっている見た目の掟(自作の掟とドレスの掟)を合わせた姿を、住民の人数分"
        "1人ずつ生成する"
    ),
    responses=_ERROR_RESPONSES,
)
async def generate_combo_look(
    world_id: str, request: HakoniwaLookRequest
) -> HakoniwaLookResponse:
    result = await _call(
        hakoniwa_service.generate_combo_look(
            world_id, regenerate=request.regenerate, language=request.language
        )
    )
    return HakoniwaLookResponse(**result)


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
    "/tags/rule-look",
    response_model=HakoniwaTagsResponse,
    summary="掟の見た目のタグを作る",
    description=(
        "掟の名前・本文・見た目の説明から見た目のタグを作って返す(保存はしない)。"
        "見た目の説明が英語のタグならそのまま整える"
    ),
    responses=_ERROR_RESPONSES,
)
async def make_rule_look_tags(
    request: HakoniwaRuleLookTagsRequest,
) -> HakoniwaTagsResponse:
    result = await _call(
        hakoniwa_service.make_rule_look_tags(
            request.name, request.text, request.appearance_text, request.language
        )
    )
    return HakoniwaTagsResponse(**result)


@router.post(
    "/tags/resident",
    response_model=HakoniwaTagsResponse,
    summary="住民の姿のタグを作る",
    description=(
        "住民の外見(dress ならドレス姿)の説明から画像タグを作って返す(保存はしない)。"
        "性別のタグは住民の性別にそろえる"
    ),
    responses=_ERROR_RESPONSES,
)
async def make_resident_tags(
    request: HakoniwaResidentTagsRequest,
) -> HakoniwaTagsResponse:
    result = await _call(
        hakoniwa_service.make_resident_tags(
            request.appearance_text,
            request.gender,
            dress=request.dress,
            language=request.language,
        )
    )
    return HakoniwaTagsResponse(**result)


@router.post(
    "/worlds/{world_id}/residents",
    response_model=HakoniwaResidentChangeResponse,
    summary="自作の住民を迎える",
    description="画像のタグは送られたものを整えて使う(いつもの姿のタグは必須)",
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


@router.put(
    "/worlds/{world_id}/intervention",
    response_model=HakoniwaWorldResponse,
    summary="明日の介入を選ぶ",
    description="次の「1日進める」で効かせる介入を選ぶ。進めるまでは選び直せる",
    responses=_ERROR_RESPONSES,
)
async def set_intervention(
    world_id: str, request: HakoniwaInterventionRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.set_intervention(world_id, request.choice, request.language)
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/touch",
    response_model=HakoniwaTouchResponse,
    summary="住民の立ち絵に触れる",
    description="触れた部位への住民の一言(年代記には残さない)と、気分の小さな変化",
    responses=_ERROR_RESPONSES,
)
async def touch_resident(
    world_id: str, resident_id: str, request: HakoniwaTouchRequest
) -> HakoniwaTouchResponse:
    result = await _call(
        hakoniwa_service.touch(world_id, resident_id, request.part, request.language)
    )
    return HakoniwaTouchResponse(**result)


@router.get(
    "/worlds/{world_id}/residents/{resident_id}/chat",
    response_model=HakoniwaChatHistoryResponse,
    summary="住民との会話の履歴",
    responses=_ERROR_RESPONSES,
)
async def get_chat_history(
    world_id: str, resident_id: str
) -> HakoniwaChatHistoryResponse:
    result = await _call(hakoniwa_service.chat_history(world_id, resident_id))
    return HakoniwaChatHistoryResponse(**result)


@router.post(
    "/worlds/{world_id}/residents/{resident_id}/chat",
    response_model=HakoniwaChatResponse,
    summary="住民と会話する",
    description=(
        "住民本人として返事をする。変身・元に戻す指示なら実行して、結果を会話に残す"
        "(変身の出来事は年代記にも積む)"
    ),
    responses=_ERROR_RESPONSES,
)
async def chat_with_resident(
    world_id: str, resident_id: str, request: HakoniwaChatRequest
) -> HakoniwaChatResponse:
    result = await _call(
        hakoniwa_service.chat(
            world_id,
            resident_id,
            request.message,
            allow_image=request.allow_image,
            confirmed_instruction=request.confirmed_instruction,
            language=request.language,
        )
    )
    return HakoniwaChatResponse(**result)


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
    "/worlds/{world_id}/residents/{resident_id}/event",
    response_model=HakoniwaDayResponse,
    summary="指示した出来事を起こす",
    description=(
        "書き手の指示で、住民のいまの姿のまま出来事を1件生成して年代記に積む。"
        "scope は solo(本人だけ) / selected(partner_ids の住民と) / room(同じ部屋の住民と)"
    ),
    responses=_ERROR_RESPONSES,
)
async def direct_event(
    world_id: str, resident_id: str, request: HakoniwaDirectedEventRequest
) -> HakoniwaDayResponse:
    result = await _call(
        hakoniwa_service.directed_event(
            world_id,
            resident_id,
            request.instruction,
            request.scope,
            request.partner_ids,
            request.language,
            request.location,
        )
    )
    return HakoniwaDayResponse(**result)


@router.post(
    "/worlds/{world_id}/events/{event_id}/continue",
    response_model=HakoniwaDayResponse,
    summary="今日の出来事の続きを指示して起こす",
    responses=_ERROR_RESPONSES,
)
async def continue_event(
    world_id: str, event_id: str, request: HakoniwaContinueEventRequest
) -> HakoniwaDayResponse:
    result = await _call(
        hakoniwa_service.continue_event(
            world_id, event_id, request.instruction, request.language
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


@router.put(
    "/worlds/{world_id}/furniture",
    response_model=HakoniwaWorldResponse,
    summary="家具を置く・片付ける",
    description="家具は1点物なので、別の場所に置いてあれば移す",
    responses=_ERROR_RESPONSES,
)
async def place_furniture(
    world_id: str, request: HakoniwaFurnitureRequest
) -> HakoniwaWorldResponse:
    world = await _call(
        hakoniwa_service.place_furniture(
            world_id,
            request.area_id,
            request.slot,
            request.furniture_id,
            request.language,
        )
    )
    return HakoniwaWorldResponse(**world)


@router.post(
    "/worlds/{world_id}/events/{event_id}/scene-image",
    response_model=HakoniwaImageResponse,
    summary="出来事の場面絵を生成",
    description="参加者のいまの姿で、出来事の山場を横長の1枚に描く",
    responses=_ERROR_RESPONSES,
)
async def generate_scene_image(
    world_id: str, event_id: str, request: HakoniwaLanguageRequest
) -> HakoniwaImageResponse:
    result = await _call(
        hakoniwa_service.generate_scene_image(world_id, event_id, request.language)
    )
    return HakoniwaImageResponse(**result)


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
