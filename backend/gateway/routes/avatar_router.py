"""3D アバター(VRM)の登録・一覧・更新(改名/キャラクター分類)・削除・配信 API。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from ..databases.base import async_session_factory
from ..services import avatar_service
from ..services.adventure_service import adventure_service
from ..services.avatar_service import AVATAR_NAME_MAX_LEN, AvatarError
from ..settings.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/avatars", tags=["avatars"])


class AvatarUpdateRequest(BaseModel):
    """None の項目は据え置き。character_name / variant_label は空文字で解除。"""

    name: str | None = Field(default=None, min_length=1, max_length=AVATAR_NAME_MAX_LEN)
    character_name: str | None = Field(default=None, max_length=AVATAR_NAME_MAX_LEN)
    variant_label: str | None = Field(default=None, max_length=AVATAR_NAME_MAX_LEN)

    @model_validator(mode="after")
    def require_any_field(self) -> AvatarUpdateRequest:
        if (
            self.name is None
            and self.character_name is None
            and self.variant_label is None
        ):
            raise ValueError("no fields to update")
        return self


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
    # 未指定ならファイル名 ``名前_衣装_….vrm`` から自動分類する。FastAPI は空の
    # フォーム欄を未指定(None)に落とすため、「未分類で登録」は auto_classify=false
    character_name: str | None = Form(default=None, max_length=AVATAR_NAME_MAX_LEN),
    variant_label: str | None = Form(default=None, max_length=AVATAR_NAME_MAX_LEN),
    auto_classify: bool = Form(default=True),
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
            model = await avatar_service.save_upload(
                db,
                file,
                name=name,
                character_name=(
                    character_name
                    if character_name is not None or auto_classify
                    else ""
                ),
                variant_label=variant_label,
            )
    except AvatarError as error:
        raise _http_error(error) from error
    finally:
        await file.close()
    return avatar_service.serialize_avatar(model)


@router.post("/auto-classify")
async def auto_classify_avatars() -> dict:
    """未設定の項目だけをモデル名の規則(``名前_衣装_…``)で埋める。設定済みは変えない。"""
    async with async_session_factory() as db:
        updated = await avatar_service.auto_classify_avatars(db)
        models = await avatar_service.list_avatars(db)
    return {
        "updated": len(updated),
        "updated_ids": [model.id for model in updated],
        "items": [avatar_service.serialize_avatar(model) for model in models],
    }


@router.get("")
async def list_avatars() -> dict:
    async with async_session_factory() as db:
        models = await avatar_service.list_avatars(db)
    return {"items": [avatar_service.serialize_avatar(model) for model in models]}


@router.patch("/{avatar_id}")
async def update_avatar(avatar_id: str, request: AvatarUpdateRequest) -> dict:
    try:
        async with async_session_factory() as db:
            model = await avatar_service.update_avatar(
                db,
                avatar_id,
                name=request.name,
                character_name=request.character_name,
                variant_label=request.variant_label,
            )
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
    # このモデルを表示中の Adventure run から割り当てを外す。残すと run を
    # 開くたびに削除済み ID のファイル配信が 404 になり、3D 表示が失敗する。
    # 削除自体は完了しているため、解除に失敗しても応答は成功のまま記録に残す
    try:
        await adventure_service.detach_companion_avatar(avatar_id)
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "Failed to detach deleted avatar %s from adventure runs: %s",
            avatar_id,
            error,
        )
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
