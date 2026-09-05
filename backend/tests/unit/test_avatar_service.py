"""VRM(GLB)の検証・meta 正規化・保存/一覧/改名/削除。"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import pytest
from fastapi import UploadFile

from gateway.services import avatar_service
from gateway.services.avatar_service import (
    AvatarError,
    avatar_display_name,
    avatar_variant_label,
    classify_avatar_filename,
    parse_vrm_meta,
    sanitize_avatar_name,
    serialize_avatar,
)
from gateway.settings.config import settings

_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942


def make_glb(payload: dict, binary: bytes = b"") -> bytes:
    """最小の GLB(ヘッダ + JSON チャンク [+ BIN チャンク])を組み立てる。"""
    body = json.dumps(payload).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    chunks = struct.pack("<II", len(body), _JSON_CHUNK) + body
    if binary:
        binary += b"\0" * ((4 - len(binary) % 4) % 4)
        chunks += struct.pack("<II", len(binary), _BIN_CHUNK) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


VRM0_PAYLOAD = {
    "asset": {"version": "2.0"},
    "extensions": {
        "VRM": {
            "exporterVersion": "UniVRM-0.51.0",
            "meta": {
                "title": "Alicia Solid",
                "author": "DWANGO",
                "licenseName": "Other",
                "otherLicenseUrl": "https://example.com/rule",
                "allowedUserName": "Everyone",
                "commercialUssageName": "Allow",
            },
        }
    },
}

VRM1_PAYLOAD = {
    "asset": {"version": "2.0"},
    "extensions": {
        "VRMC_vrm": {
            "specVersion": "1.0",
            "meta": {
                "name": "Sample 1.0",
                "authors": ["A", " B "],
                "licenseUrl": "https://vrm.dev/licenses/1.0/",
                "avatarPermission": "everyone",
                "commercialUsage": "personalProfit",
            },
        }
    },
}


# meta.title が無い VRM。モデル名がファイル名になるケース(自動分類の再適用対象)
NO_TITLE_PAYLOAD = {"asset": {}, "extensions": {"VRM": {"meta": {"author": "X"}}}}


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_parse_vrm_meta_v0(tmp_path: Path) -> None:
    info = parse_vrm_meta(_write(tmp_path, "a.vrm", make_glb(VRM0_PAYLOAD, b"bin")))
    assert info.spec_version == "0"
    assert info.meta == {
        "title": "Alicia Solid",
        "author": "DWANGO",
        "license": "Other",
        "license_url": "https://example.com/rule",
        "allowed_user": "Everyone",
        "commercial": "Allow",
    }


def test_parse_vrm_meta_v1(tmp_path: Path) -> None:
    info = parse_vrm_meta(_write(tmp_path, "b.vrm", make_glb(VRM1_PAYLOAD)))
    assert info.spec_version == "1"
    assert info.meta["title"] == "Sample 1.0"
    assert info.meta["author"] == "A, B"
    assert info.meta["license"] == "VRM Public License 1.0"
    assert info.meta["license_url"] == "https://vrm.dev/licenses/1.0/"
    assert info.meta["allowed_user"] == "everyone"
    assert info.meta["commercial"] == "personalProfit"


@pytest.mark.parametrize(
    "data",
    [
        b"not a glb at all",
        b"",
        make_glb({"asset": {"version": "2.0"}}),
        make_glb({"asset": {}, "extensions": {"KHR_materials_unlit": {}}}),
        # ヘッダは正しいが JSON チャンクが途中で切れている
        make_glb(VRM0_PAYLOAD)[:40],
        # JSON チャンクの中身が JSON でない
        b"glTF"
        + struct.pack("<II", 2, 24)
        + struct.pack("<II", 4, _JSON_CHUNK)
        + b"xxxx",
    ],
)
def test_parse_vrm_meta_rejects_invalid(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(AvatarError) as error:
        parse_vrm_meta(_write(tmp_path, "bad.vrm", data))
    assert error.value.code == "invalid_vrm"


def test_sanitize_avatar_name() -> None:
    assert sanitize_avatar_name("  My   Alicia \n") == "My Alicia"
    assert sanitize_avatar_name("", fallback="alicia") == "alicia"
    assert sanitize_avatar_name(None, fallback="  ") == "VRM"
    assert len(sanitize_avatar_name("x" * 200)) == 80


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        # 先頭の "_" までがキャラクター名、残りが差分("_" は空白へ)
        ("サクラ_水着_髪束ねたVer", ("サクラ", "水着 髪束ねたVer")),
        ("サクラ_ドレス", ("サクラ", "ドレス")),
        ("  Sakura_Swimsuit__Tied  ", ("Sakura", "Swimsuit Tied")),
        # 区切りが無い・どちらかが空なら未分類
        ("Alicia Solid", (None, None)),
        ("_水着", (None, None)),
        ("サクラ_", (None, None)),
        ("サクラ_   ", (None, None)),
        ("", (None, None)),
    ],
)
def test_classify_avatar_filename(stem: str, expected: tuple) -> None:
    assert classify_avatar_filename(stem) == expected


@pytest.fixture
def session_factory(isolated_db, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "avatar_models_dir", tmp_path / "models")
    monkeypatch.setattr(settings, "avatar_upload_max_bytes", 1024 * 1024)
    return isolated_db.async_factory


def _upload(data: bytes, filename: str = "alicia.vrm") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


async def test_save_list_rename_delete_round_trip(session_factory, tmp_path: Path):
    glb = make_glb(VRM0_PAYLOAD, b"binary")
    async with session_factory() as db:
        model = await avatar_service.save_upload(db, _upload(glb), name=None)
    # 名前は meta.title、保存名は {id}.vrm 固定で一時ファイルは残らない
    assert model.name == "Alicia Solid"
    assert model.file_path == f"{model.id}.vrm"
    path = tmp_path / "models" / f"{model.id}.vrm"
    assert path.read_bytes() == glb
    assert sorted(p.name for p in (tmp_path / "models").iterdir()) == [path.name]
    assert model.file_size == len(glb) and model.vrm_spec_version == "0"
    serialized = serialize_avatar(model)
    assert serialized["file_url"] == f"/avatars/{model.id}/file"
    assert serialized["meta"]["author"] == "DWANGO"
    assert serialized["created_at"]

    async with session_factory() as db:
        assert [m.id for m in await avatar_service.list_avatars(db)] == [model.id]
        assert await avatar_service.avatar_exists(db, model.id) is True
        assert await avatar_service.avatar_exists(db, "missing") is False
        renamed = await avatar_service.rename_avatar(db, model.id, "  My  Alicia ")
        assert renamed.name == "My Alicia"
        assert avatar_service.resolve_avatar_file(renamed) == path

    async with session_factory() as db:
        await avatar_service.delete_avatar(db, model.id)
    assert not path.exists()
    async with session_factory() as db:
        assert await avatar_service.list_avatars(db) == []
        with pytest.raises(AvatarError) as error:
            await avatar_service.get_avatar(db, model.id)
        assert error.value.code == "avatar_not_found"


async def test_save_upload_name_precedence(session_factory):
    without_title = {"asset": {}, "extensions": {"VRM": {"meta": {"author": "X"}}}}
    async with session_factory() as db:
        explicit = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD)), name="  Custom  "
        )
        from_file = await avatar_service.save_upload(
            db, _upload(make_glb(without_title), filename="dir/my model.vrm")
        )
    assert explicit.name == "Custom"
    assert from_file.name == "my model"


async def test_save_upload_classifies_character_from_filename(session_factory):
    async with session_factory() as db:
        auto = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_水着_髪束ねたVer.vrm")
        )
        plain = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD), filename="alicia.vrm")
        )
        # 空文字を明示すると形式に合っていても未分類
        forced_plain = await avatar_service.save_upload(
            db,
            _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_ドレス.vrm"),
            character_name="",
        )
        # キャラクター名を手で指定しても、差分はファイル名から流用する
        manual = await avatar_service.save_upload(
            db,
            _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_ニット_ロングヘアVer.vrm"),
            character_name="  Sakura ",
        )
        explicit = await avatar_service.save_upload(
            db,
            _upload(make_glb(VRM0_PAYLOAD), filename="alicia.vrm"),
            character_name="Alicia",
            variant_label=" 制服 ",
        )
    assert (auto.character_name, auto.variant_label) == ("サクラ", "水着 髪束ねたVer")
    # モデル名は従来どおり meta.title を優先する
    assert auto.name == "Alicia Solid"
    assert (plain.character_name, plain.variant_label) == (None, None)
    assert (forced_plain.character_name, forced_plain.variant_label) == (None, None)
    assert (manual.character_name, manual.variant_label) == (
        "Sakura",
        "ニット ロングヘアVer",
    )
    assert (explicit.character_name, explicit.variant_label) == ("Alicia", "制服")
    serialized = serialize_avatar(auto)
    assert serialized["character_name"] == "サクラ"
    assert serialized["variant_label"] == "水着 髪束ねたVer"
    assert serialize_avatar(plain)["character_name"] is None
    assert avatar_variant_label(auto) == "水着 髪束ねたVer"
    assert avatar_variant_label(plain) == "Alicia Solid"
    assert avatar_display_name(auto) == "サクラ / 水着 髪束ねたVer"
    assert avatar_display_name(plain) == "Alicia Solid"


async def test_update_avatar_and_list_variants(session_factory):
    async with session_factory() as db:
        swim = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_水着.vrm")
        )
        dress = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_ドレス.vrm")
        )
        other = await avatar_service.save_upload(
            db, _upload(make_glb(VRM0_PAYLOAD), filename="alicia.vrm")
        )
        # 同じキャラクターは差分ラベル順(自身を含む)。未分類は自身だけ
        ids = [m.id for m in await avatar_service.list_avatar_variants(db, swim.id)]
        assert ids == [dress.id, swim.id]
        assert [
            m.id for m in await avatar_service.list_avatar_variants(db, other.id)
        ] == [other.id]
        assert await avatar_service.list_avatar_variants(db, "missing") == []

        # 未分類のモデルをユーザーが同じキャラクターへ付け替える(削除せずに分類)
        joined = await avatar_service.update_avatar(
            db, other.id, character_name=" サクラ ", variant_label="制服"
        )
        assert (joined.character_name, joined.variant_label) == ("サクラ", "制服")
        assert joined.name == "Alicia Solid"
        # 差分ラベルの文字順(ドレス < 制服 < 水着)
        ids = [m.id for m in await avatar_service.list_avatar_variants(db, swim.id)]
        assert ids == [dress.id, joined.id, swim.id]

        # None は据え置き、空文字は解除
        renamed = await avatar_service.update_avatar(db, swim.id, name="Swim")
        assert renamed.name == "Swim" and renamed.character_name == "サクラ"
        detached = await avatar_service.update_avatar(
            db, dress.id, character_name="", variant_label=""
        )
        assert (detached.character_name, detached.variant_label) == (None, None)
        ids = [m.id for m in await avatar_service.list_avatar_variants(db, swim.id)]
        assert ids == [joined.id, swim.id]
        with pytest.raises(AvatarError):
            await avatar_service.update_avatar(db, "missing", name="x")


async def test_auto_classify_fills_only_empty_fields(session_factory):
    glb = make_glb(NO_TITLE_PAYLOAD)
    async with session_factory() as db:
        # 更新前に登録したモデル相当: 名前(ファイル名)は規則に合うが分類は空
        legacy = await avatar_service.save_upload(
            db, _upload(glb, filename="サクラ_水着_髪束ねたVer.vrm"), character_name=""
        )
        # キャラクターだけ手で付けた(差分ラベルが空)
        half = await avatar_service.save_upload(
            db,
            _upload(glb, filename="サクラ_ドレス.vrm"),
            character_name="別名",
            variant_label="",
        )
        # ユーザーが決めた分類は変えない
        decided = await avatar_service.save_upload(
            db,
            _upload(glb, filename="サクラ_ニット.vrm"),
            character_name="別名",
            variant_label="手入力",
        )
        # 規則に合わない名前は据え置き
        plain = await avatar_service.save_upload(
            db, _upload(glb, filename="alicia.vrm")
        )
        # meta.title があるモデルは名前がファイル名でないため対象にならない
        titled = await avatar_service.save_upload(
            db,
            _upload(make_glb(VRM0_PAYLOAD), filename="サクラ_バスタオル.vrm"),
            character_name="",
        )
        updated = await avatar_service.auto_classify_avatars(db)
    assert sorted(m.id for m in updated) == sorted([legacy.id, half.id])
    async with session_factory() as db:
        by_id = {m.id: m for m in await avatar_service.list_avatars(db)}
    assert (by_id[legacy.id].character_name, by_id[legacy.id].variant_label) == (
        "サクラ",
        "水着 髪束ねたVer",
    )
    # キャラクター名は手入力を保ち、差分ラベルだけ埋まる
    assert (by_id[half.id].character_name, by_id[half.id].variant_label) == (
        "別名",
        "ドレス",
    )
    assert (by_id[decided.id].character_name, by_id[decided.id].variant_label) == (
        "別名",
        "手入力",
    )
    assert (by_id[plain.id].character_name, by_id[plain.id].variant_label) == (
        None,
        None,
    )
    assert by_id[titled.id].name == "Alicia Solid"
    assert by_id[titled.id].character_name is None
    # 二度目は何も更新しない
    async with session_factory() as db:
        assert await avatar_service.auto_classify_avatars(db) == []


async def test_save_upload_rejects_oversize_and_cleans_temp(
    session_factory, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(settings, "avatar_upload_max_bytes", 100)
    async with session_factory() as db:
        with pytest.raises(AvatarError) as error:
            await avatar_service.save_upload(db, _upload(b"x" * 200))
        assert error.value.code == "file_too_large"
        assert list((tmp_path / "models").iterdir()) == []
        assert await avatar_service.list_avatars(db) == []


async def test_save_upload_rejects_invalid_vrm_and_cleans_temp(
    session_factory, tmp_path: Path
):
    async with session_factory() as db:
        with pytest.raises(AvatarError) as error:
            await avatar_service.save_upload(db, _upload(b"garbage" * 10))
        assert error.value.code == "invalid_vrm"
        with pytest.raises(AvatarError):
            await avatar_service.save_upload(db, _upload(b""))
        assert list((tmp_path / "models").iterdir()) == []
        assert await avatar_service.list_avatars(db) == []


def test_resolve_avatar_file_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "avatar_models_dir", tmp_path)
    (tmp_path / "secret.vrm").write_bytes(b"x")
    from gateway.databases.models import AvatarModel

    model = AvatarModel(id="a", name="a", file_path="../secret.vrm")
    assert avatar_service.resolve_avatar_file(model) is None
    model.file_path = "secret.vrm"
    assert avatar_service.resolve_avatar_file(model) == tmp_path / "secret.vrm"
