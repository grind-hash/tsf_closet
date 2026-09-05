"""3D アバター(VRM)の登録・検証・保存・配信。

VRM は glTF 2.0 の GLB コンテナで、先頭の JSON チャンクの ``extensions`` に
``VRM``(0.x) または ``VRMC_vrm``(1.0) を持つ。ここではヘッダと JSON チャンク
だけを読んで形式を検証し、meta を正規化して保存する(追加依存なし)。

ファイル本体は settings.avatar_models_dir に ``{id}.vrm`` として置き、
クライアントのファイル名は保存名に使わない(パストラバーサル防止)。

同じキャラクターの衣装差分は ``character_name`` でまとめる。登録時はファイル名
``名前_衣装_….vrm`` から自動で分類し(``classify_avatar_filename``)、以後は
ユーザーが付け替える。run は個々のモデル ID を参照するため、分類を変えても
既存の割り当ては壊れない。
"""

from __future__ import annotations

import json
import logging
import os
import re
import struct
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.models import AvatarModel
from ..settings.config import settings

logger = logging.getLogger(__name__)

AVATAR_NAME_MAX_LEN = 80
AVATAR_FILE_URL_TEMPLATE = "/avatars/{avatar_id}/file"

# ファイル名 ``名前_衣装_髪型Ver.vrm`` の自動分類。先頭の ``_`` までをキャラクター名、
# 残りを差分の説明にする(``_`` は空白へ)。区切りが無い・どちらかが空なら未分類
_FILENAME_CLASSIFY_RE = re.compile(r"^(?P<name>[^_]+)_(?P<variant>.+)$")

_GLB_MAGIC = b"glTF"
_GLB_VERSION = 2
_GLB_JSON_CHUNK_TYPE = 0x4E4F534A  # "JSON"
_JSON_CHUNK_MAX_BYTES = 16 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024


class AvatarError(Exception):
    """アバター操作のエラー。code はルーターが HTTP ステータスへ写す。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class VrmInfo:
    spec_version: str  # "0" | "1"
    meta: dict[str, Any]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _read_glb_json(path: Path) -> dict[str, Any]:
    """GLB ヘッダと JSON チャンクだけを読んで dict を返す。"""
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12:
            raise AvatarError("invalid_vrm", "VRM ファイルではありません")
        magic, version, _length = struct.unpack("<4sII", header)
        if magic != _GLB_MAGIC or version != _GLB_VERSION:
            raise AvatarError("invalid_vrm", "VRM ファイルではありません")
        chunk_header = handle.read(8)
        if len(chunk_header) < 8:
            raise AvatarError("invalid_vrm", "VRM ファイルではありません")
        chunk_length, chunk_type = struct.unpack("<II", chunk_header)
        if (
            chunk_type != _GLB_JSON_CHUNK_TYPE
            or chunk_length <= 0
            or chunk_length > _JSON_CHUNK_MAX_BYTES
        ):
            raise AvatarError("invalid_vrm", "VRM ファイルではありません")
        raw = handle.read(chunk_length)
    if len(raw) < chunk_length:
        raise AvatarError("invalid_vrm", "VRM ファイルが壊れています")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise AvatarError("invalid_vrm", "VRM ファイルが壊れています") from error
    if not isinstance(data, dict):
        raise AvatarError("invalid_vrm", "VRM ファイルが壊れています")
    return data


def _normalize_meta_v0(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _text(meta.get("title")),
        "author": _text(meta.get("author")),
        "license": _text(meta.get("licenseName")),
        "license_url": _text(meta.get("otherLicenseUrl"))
        or _text(meta.get("otherPermissionUrl")),
        "allowed_user": _text(meta.get("allowedUserName")),
        "commercial": _text(meta.get("commercialUssageName")),
    }


def _normalize_meta_v1(meta: dict[str, Any]) -> dict[str, Any]:
    authors = meta.get("authors")
    if isinstance(authors, list):
        author = ", ".join(item for item in (_text(a) or "" for a in authors) if item)
    else:
        author = _text(authors) or ""
    license_url = _text(meta.get("licenseUrl"))
    license_name = None
    if license_url and "vrm.dev/licenses/1.0" in license_url:
        license_name = "VRM Public License 1.0"
    return {
        "title": _text(meta.get("name")),
        "author": author or None,
        "license": license_name,
        "license_url": license_url,
        "allowed_user": _text(meta.get("avatarPermission")),
        "commercial": _text(meta.get("commercialUsage")),
    }


def parse_vrm_meta(path: Path) -> VrmInfo:
    """VRM 0.x / 1.0 を判定し、meta を正規化して返す。VRM でなければ invalid_vrm。"""
    data = _read_glb_json(path)
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        raise AvatarError("invalid_vrm", "VRM ファイルではありません")
    vrm1 = extensions.get("VRMC_vrm")
    if isinstance(vrm1, dict):
        meta = vrm1.get("meta")
        return VrmInfo("1", _normalize_meta_v1(meta if isinstance(meta, dict) else {}))
    vrm0 = extensions.get("VRM")
    if isinstance(vrm0, dict):
        meta = vrm0.get("meta")
        return VrmInfo("0", _normalize_meta_v0(meta if isinstance(meta, dict) else {}))
    raise AvatarError("invalid_vrm", "VRM ファイルではありません")


def sanitize_avatar_name(raw: Any, fallback: str = "VRM") -> str:
    text = _text(raw) or _text(fallback) or "VRM"
    return text[:AVATAR_NAME_MAX_LEN]


def sanitize_optional_label(raw: Any) -> str | None:
    """キャラクター名・差分ラベル用。空白だけなら None(未設定)。"""
    text = _text(raw)
    return text[:AVATAR_NAME_MAX_LEN] if text else None


def classify_avatar_filename(stem: str) -> tuple[str | None, str | None]:
    """``名前_衣装_髪型Ver`` 形式のファイル名から (キャラクター名, 差分ラベル) を返す。

    アプリのルール: ``_`` 区切りの先頭がキャラクター名、残りが差分の説明。
    形式に合わなければ (None, None) で未分類のまま登録する。最終的な分類は
    ユーザーが設定画面で付け替える前提の初期値に過ぎない。
    """
    match = _FILENAME_CLASSIFY_RE.match(str(stem or "").strip())
    if match is None:
        return None, None
    name = sanitize_optional_label(match.group("name"))
    variant = sanitize_optional_label(match.group("variant").replace("_", " "))
    if name is None or variant is None:
        return None, None
    return name, variant


def avatar_variant_label(model: AvatarModel) -> str:
    """グループ内で差分を区別する表示名。差分ラベルが無ければモデル名。"""
    return _text(model.variant_label) or _text(model.name) or "VRM"


def avatar_display_name(model: AvatarModel) -> str:
    """一覧・選択肢向けの表示名。分類済みなら ``キャラクター / 差分``。"""
    character = _text(model.character_name)
    if not character:
        return _text(model.name) or "VRM"
    return f"{character} / {avatar_variant_label(model)}"


def _filename_stem(upload: UploadFile) -> str:
    name = Path(str(upload.filename or "")).name
    stem = Path(name).stem if name else ""
    return stem or "VRM"


def avatar_models_dir() -> Path:
    return settings.avatar_models_dir


def resolve_avatar_file(model: AvatarModel) -> Path | None:
    """登録済みモデルの実ファイルを返す(bare filename のみ許可)。"""
    name = Path(str(model.file_path or "")).name
    if not name or name != model.file_path:
        return None
    path = avatar_models_dir() / name
    return path if path.is_file() else None


def avatar_file_url(avatar_id: str) -> str:
    return AVATAR_FILE_URL_TEMPLATE.format(avatar_id=avatar_id)


def serialize_avatar(model: AvatarModel) -> dict[str, Any]:
    try:
        meta = json.loads(model.meta_json or "{}")
    except ValueError:
        meta = {}
    return {
        "id": model.id,
        "name": model.name,
        "character_name": _text(model.character_name),
        "variant_label": _text(model.variant_label),
        "file_size": int(model.file_size or 0),
        "vrm_spec_version": model.vrm_spec_version or "0",
        "meta": meta if isinstance(meta, dict) else {},
        "file_url": avatar_file_url(model.id),
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


async def save_upload(
    db: AsyncSession,
    upload: UploadFile,
    *,
    name: str | None = None,
    character_name: str | None = None,
    variant_label: str | None = None,
) -> AvatarModel:
    """アップロードをストリームで保存し、VRM 検証後に登録する。

    character_name / variant_label が None(未指定)ならファイル名から自動分類する。
    空文字を明示すると未分類で登録する。
    """
    directory = avatar_models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    limit = int(settings.avatar_upload_max_bytes)
    avatar_id = uuid.uuid4().hex
    final_path = directory / f"{avatar_id}.vrm"
    # 失敗時の後始末で temp_path を使うため、with は書き込み時に別途開く
    temp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        dir=directory, suffix=".part", delete=False
    )
    temp_path = Path(temp.name)
    total = 0
    try:
        with temp:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise AvatarError(
                        "file_too_large",
                        f"ファイルが大きすぎます(上限 {limit // (1024 * 1024)} MiB)",
                    )
                temp.write(chunk)
        if total == 0:
            raise AvatarError("invalid_vrm", "ファイルが空です")
        info = parse_vrm_meta(temp_path)
        os.replace(temp_path, final_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    stem = _filename_stem(upload)
    auto_character, auto_variant = classify_avatar_filename(stem)
    resolved_character = (
        auto_character
        if character_name is None
        else sanitize_optional_label(character_name)
    )
    if variant_label is None:
        # 自動分類のときだけ差分ラベルも自動。キャラクター名を手で指定した
        # 場合も、ファイル名が形式に合っていれば差分は流用する
        resolved_variant = auto_variant if resolved_character else None
    else:
        resolved_variant = sanitize_optional_label(variant_label)
    model = AvatarModel(
        id=avatar_id,
        name=sanitize_avatar_name(name, fallback=info.meta.get("title") or stem),
        character_name=resolved_character,
        variant_label=resolved_variant,
        file_path=final_path.name,
        file_size=total,
        vrm_spec_version=info.spec_version,
        meta_json=json.dumps(info.meta, ensure_ascii=False),
    )
    try:
        db.add(model)
        await db.commit()
        await db.refresh(model)
    except BaseException:
        final_path.unlink(missing_ok=True)
        raise
    return model


async def list_avatars(db: AsyncSession) -> list[AvatarModel]:
    result = await db.execute(
        select(AvatarModel).order_by(AvatarModel.created_at.desc(), AvatarModel.id)
    )
    return list(result.scalars().all())


async def get_avatar(db: AsyncSession, avatar_id: str) -> AvatarModel:
    model = await db.get(AvatarModel, avatar_id)
    if model is None:
        raise AvatarError("avatar_not_found", "3Dモデルが見つかりません")
    return model


async def avatar_exists(db: AsyncSession, avatar_id: str) -> bool:
    return await db.get(AvatarModel, avatar_id) is not None


async def update_avatar(
    db: AsyncSession,
    avatar_id: str,
    *,
    name: str | None = None,
    character_name: str | None = None,
    variant_label: str | None = None,
) -> AvatarModel:
    """名前・キャラクター名・差分ラベルを更新する。None の項目は据え置き。

    character_name / variant_label は空文字で解除(未分類・ラベル無し)。
    """
    model = await get_avatar(db, avatar_id)
    if name is not None:
        model.name = sanitize_avatar_name(name, fallback=model.name)
    if character_name is not None:
        model.character_name = sanitize_optional_label(character_name)
    if variant_label is not None:
        model.variant_label = sanitize_optional_label(variant_label)
    await db.commit()
    await db.refresh(model)
    return model


async def rename_avatar(db: AsyncSession, avatar_id: str, name: str) -> AvatarModel:
    return await update_avatar(db, avatar_id, name=name)


async def auto_classify_avatars(db: AsyncSession) -> list[AvatarModel]:
    """未設定の項目だけをモデル名からの自動分類で埋め、更新したモデルを返す。

    キャラクター未設定のモデルにはキャラクター名と差分ラベルを、キャラクター設定済み
    で差分ラベルが空のモデルには差分ラベルだけを入れる。ユーザーが既に決めた分類は
    変えない(この機能の更新前に登録したモデルを、削除せずにまとめて整理する用途)。
    """
    updated: list[AvatarModel] = []
    for model in await list_avatars(db):
        has_character = bool(_text(model.character_name))
        has_variant = bool(_text(model.variant_label))
        if has_character and has_variant:
            continue
        character, variant = classify_avatar_filename(model.name)
        if character is None:
            continue
        if not has_character:
            model.character_name = character
        if not has_variant:
            model.variant_label = variant
        updated.append(model)
    if updated:
        await db.commit()
        for model in updated:
            await db.refresh(model)
    return updated


async def list_avatar_variants(db: AsyncSession, avatar_id: str) -> list[AvatarModel]:
    """同じキャラクターとして分類されたモデル(自身を含む)を差分ラベル順で返す。

    未分類のモデルは自身だけを返す。未登録 ID は空リスト。
    """
    model = await db.get(AvatarModel, avatar_id)
    if model is None:
        return []
    character = _text(model.character_name)
    if not character:
        return [model]
    result = await db.execute(
        select(AvatarModel)
        .where(AvatarModel.character_name == model.character_name)
        .order_by(AvatarModel.variant_label, AvatarModel.name, AvatarModel.created_at)
    )
    return list(result.scalars().all())


async def delete_avatar(db: AsyncSession, avatar_id: str) -> None:
    model = await get_avatar(db, avatar_id)
    path = resolve_avatar_file(model)
    await db.delete(model)
    await db.commit()
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("Failed to remove avatar file %s: %s", path, error)


__all__ = [
    "AVATAR_NAME_MAX_LEN",
    "AvatarError",
    "VrmInfo",
    "auto_classify_avatars",
    "avatar_display_name",
    "avatar_exists",
    "avatar_file_url",
    "avatar_variant_label",
    "classify_avatar_filename",
    "delete_avatar",
    "get_avatar",
    "list_avatar_variants",
    "list_avatars",
    "parse_vrm_meta",
    "rename_avatar",
    "resolve_avatar_file",
    "sanitize_avatar_name",
    "sanitize_optional_label",
    "save_upload",
    "serialize_avatar",
    "update_avatar",
]
