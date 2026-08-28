"""3D アバター(VRM)の登録・一覧・改名・削除・配信 API。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..databases.base import async_session_factory
from ..services import avatar_service
from ..services.avatar_service import AVATAR_NAME_MAX_LEN, AvatarError
from ..settings.config import settings

router = APIRouter(prefix="/avatars", tags=["avatars"])


class AvatarRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=AVATAR_NAME_MAX_LEN)


def _http_error(error: AvatarError) -> HTTPException:
    if error.code in {"avatar_not_found", "file_missing"}:
        code = status.HTTP_404_NOT_FOUND
    elif error.code == "file_too_large":
        code = status.HTTP_413_CONTENT_TOO_LARGE
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=code, detail={"code": error.code, "message": str(error)}
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(default=None, max_length=AVATAR_NAME_MAX_LEN),
) -> dict:
    # 本体を読む前に Content-Length で明らかな超過を弾く(粗いゲート)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.avatar_upload_max_bytes:
        raise _http_error(
            AvatarError(
                "file_too_large",
                "ファイルが大きすぎます"
                f"(上限 {settings.avatar_upload_max_bytes // (1024 * 1024)} MiB)",
            )
        )
    try:
        async with async_session_factory() as db:
            model = await avatar_service.save_upload(db, file, name=name)
    except AvatarError as error:
        raise _http_error(error) from error
    finally:
        await file.close()
    return avatar_service.serialize_avatar(model)


@router.get("")
async def list_avatars() -> dict:
    async with async_session_factory() as db:
        models = await avatar_service.list_avatars(db)
    return {"items": [avatar_service.serialize_avatar(model) for model in models]}


@router.patch("/{avatar_id}")
async def rename_avatar(avatar_id: str, request: AvatarRenameRequest) -> dict:
    try:
        async with async_session_factory() as db:
            model = await avatar_service.rename_avatar(db, avatar_id, request.name)
    except AvatarError as error:
        raise _http_error(error) from error
    return avatar_service.serialize_avatar(model)


@router.delete("/{avatar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(avatar_id: str) -> None:
    try:
        async with async_session_factory() as db:
            await avatar_service.delete_avatar(db, avatar_id)
    except AvatarError as error:
        raise _http_error(error) from error
    return None


@router.get("/{avatar_id}/file")
async def get_avatar_file(avatar_id: str):
    try:
        async with async_session_factory() as db:
            model = await avatar_service.get_avatar(db, avatar_id)
    except AvatarError as error:
        raise _http_error(error) from error
    path = avatar_service.resolve_avatar_file(model)
    if path is None:
        raise _http_error(AvatarError("file_missing", "3Dモデルのファイルがありません"))
    return FileResponse(
        path,
        media_type="model/gltf-binary",
        filename=f"{model.name}.vrm",
        content_disposition_type="inline",
    )
