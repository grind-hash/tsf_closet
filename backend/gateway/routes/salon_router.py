"""サロン経営モードの API。

接客そのものは通常の手番(/game/play/stream)と依頼の API で進め、ここでは
開店・予約・接客の開始・会計・週の締めを扱う。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..consts.language import normalize_language
from ..schemas.common import ErrorResponse
from ..schemas.salon import (
    SalonCheckoutResponse,
    SalonCloseWeekResponse,
    SalonCreateRequest,
    SalonLanguageRequest,
    SalonRunListResponse,
    SalonRunResponse,
    SalonSettingsRequest,
    SalonVisitStartResponse,
)
from ..services.salon_service import SalonError, salon_service
from ..services.session import session_store

router = APIRouter(prefix="/salon", tags=["salon"])

_NOT_FOUND_CODES = {"salon_not_found", "visit_not_found"}
_ERROR_RESPONSES = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def _http_error(error: SalonError) -> HTTPException:
    return HTTPException(
        status_code=404 if error.code in _NOT_FOUND_CODES else 400,
        detail={"error": error.code, "message": str(error)},
    )


async def _language(request: SalonLanguageRequest) -> str:
    user_settings = await session_store.get_user_settings()
    return normalize_language(request.language or user_settings.get("language"))


@router.get("/runs", response_model=SalonRunListResponse, summary="サロン一覧")
async def list_salon_runs() -> SalonRunListResponse:
    runs = await salon_service.list_runs()
    return SalonRunListResponse(runs=[SalonRunResponse(**run) for run in runs])


@router.post(
    "/runs",
    response_model=SalonRunResponse,
    summary="開店",
    description="サロンを開き、1週目の予約を入れる。開業資金は経営の難易度で決まる",
    responses=_ERROR_RESPONSES,
)
async def create_salon_run(request: SalonCreateRequest) -> SalonRunResponse:
    try:
        run = await salon_service.create_run(request.name, request.difficulty)
    except SalonError as error:
        raise _http_error(error) from error
    return SalonRunResponse(**run)


@router.get(
    "/runs/{run_id}",
    response_model=SalonRunResponse,
    summary="サロン取得",
    responses=_ERROR_RESPONSES,
)
async def get_salon_run(run_id: str) -> SalonRunResponse:
    try:
        run = await salon_service.get_run(run_id)
    except SalonError as error:
        raise _http_error(error) from error
    return SalonRunResponse(**run)


@router.patch(
    "/runs/{run_id}/settings",
    response_model=SalonRunResponse,
    summary="オーナー室の設定を変える(過激施術など)",
    responses=_ERROR_RESPONSES,
)
async def update_salon_settings(
    run_id: str, request: SalonSettingsRequest
) -> SalonRunResponse:
    try:
        run = await salon_service.update_settings(run_id, sensitive=request.sensitive)
    except SalonError as error:
        raise _http_error(error) from error
    return SalonRunResponse(**run)


@router.delete(
    "/runs/{run_id}", status_code=204, summary="サロン削除", responses=_ERROR_RESPONSES
)
async def delete_salon_run(run_id: str) -> None:
    try:
        await salon_service.delete_run(run_id)
    except SalonError as error:
        raise _http_error(error) from error


@router.post(
    "/runs/{run_id}/visits/{visit_id}/start",
    response_model=SalonVisitStartResponse,
    summary="接客の開始",
    description=(
        "予約のお客様でセッションを作り、施術3手・質問2回の依頼を付ける。"
        "接客中なら同じセッションに戻る"
    ),
    responses=_ERROR_RESPONSES,
)
async def start_salon_visit(
    run_id: str, visit_id: str, request: SalonLanguageRequest
) -> SalonVisitStartResponse:
    try:
        result = await salon_service.start_visit(
            run_id, visit_id, language=await _language(request)
        )
    except SalonError as error:
        raise _http_error(error) from error
    return SalonVisitStartResponse(**result)


@router.post(
    "/runs/{run_id}/visits/{visit_id}/checkout",
    response_model=SalonCheckoutResponse,
    summary="会計",
    description="依頼の満足度から支払と評判を決め、お客様の口コミを生成する",
    responses=_ERROR_RESPONSES,
)
async def checkout_salon_visit(
    run_id: str, visit_id: str, request: SalonLanguageRequest
) -> SalonCheckoutResponse:
    try:
        result = await salon_service.checkout_visit(
            run_id, visit_id, language=await _language(request)
        )
    except SalonError as error:
        raise _http_error(error) from error
    return SalonCheckoutResponse(**result)


@router.post(
    "/runs/{run_id}/visits/{visit_id}/decline",
    response_model=SalonRunResponse,
    summary="予約を断る",
    responses=_ERROR_RESPONSES,
)
async def decline_salon_visit(run_id: str, visit_id: str) -> SalonRunResponse:
    try:
        run = await salon_service.decline_visit(run_id, visit_id)
    except SalonError as error:
        raise _http_error(error) from error
    return SalonRunResponse(**run)


@router.post(
    "/runs/{run_id}/close-week",
    response_model=SalonCloseWeekResponse,
    summary="週を締める",
    description=(
        "固定費と本業の収入を反映し、翌週の予約を入れる。"
        "最終週なら決算し、解除したサロン経営の実績を返す"
    ),
    responses=_ERROR_RESPONSES,
)
async def close_salon_week(run_id: str) -> SalonCloseWeekResponse:
    try:
        result = await salon_service.close_week(run_id)
    except SalonError as error:
        raise _http_error(error) from error
    return SalonCloseWeekResponse(**result)
