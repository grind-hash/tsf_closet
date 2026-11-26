"""キャラクター(CharacterPreset)から始めるセッション: 人物像の変換・立ち絵の写し・来店候補・旧カスタムキャラクターの取り込み。"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gateway.databases.models import CharacterPreset, User
from gateway.services import character_preset_portrait
from gateway.services.character_preset_portrait import (
    CharacterPresetPortraitError,
    import_custom_characters,
    upload_preset_portrait,
)
from gateway.services.custom_sessions import (
    delete_custom_session_metadata,
    imported_preset_id,
    list_unimported_custom_character_profiles,
    load_custom_session_metadata,
)
from gateway.services.game_service import GameServiceError, game_service
from gateway.services.preset_sessions import (
    list_playable_presets,
    list_salon_preset_customers,
    preset_play_profile,
)
from gateway.services.session import DEFAULT_USER_ID, session_store
from gateway.services.session_request_service import session_profile
from gateway.settings.config import settings

_PROFILE = {
    "pronoun": "俺",
    "personality": "明るくて人懐っこい",
    "gender": "man",
    "tsf_attitude": "女の子の姿に興味がある",
    "memo": "大学二年生",
}


def _png(color: str = "white") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _webp() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(buffer, format="WEBP")
    return buffer.getvalue()


@pytest.fixture
def data_dir(isolated_db, tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "data"
    images = root / "history_images"
    images.mkdir(parents=True)
    monkeypatch.setattr(settings, "history_images_dir", images)
    # 履歴の画像も一時フォルダへ(実データの history_images に書かない)
    monkeypatch.setattr(session_store, "_history_images_dir", images)
    with isolated_db.sync_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.commit()
    return root


def _add_preset(
    isolated_db,
    data_dir: Path,
    preset_id: str,
    name: str,
    *,
    portrait: bytes | None = None,
    suffix: str = ".png",
    salon_enabled: bool = True,
) -> None:
    portrait_path = None
    if portrait is not None:
        directory = data_dir / "character_images" / preset_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"source-1{suffix}").write_bytes(portrait)
        portrait_path = f"character_images/{preset_id}/source-1{suffix}"
    with isolated_db.sync_factory() as db:
        db.add(
            CharacterPreset(
                id=preset_id,
                name=name,
                appearance_natural="黒髪の青年",
                appearance_tags="short black hair, brown eyes, school uniform, standing",
                profile_json=json.dumps(_PROFILE, ensure_ascii=False),
                portrait_path=portrait_path,
                salon_enabled=salon_enabled,
            )
        )
        db.commit()


def test_preset_play_profile_maps_the_character_settings() -> None:
    preset = CharacterPreset(
        id="p1",
        name="ミナト",
        appearance_natural="黒髪の青年",
        appearance_tags="short black hair, brown eyes, school uniform, standing",
        profile_json=json.dumps(_PROFILE, ensure_ascii=False),
    )

    profile = preset_play_profile(preset)

    assert profile == {
        "name": "ミナト",
        "description": "大学二年生",
        "pronoun": "俺",
        "personality": "明るくて人懐っこい",
        "gender": "man",
        # 動作のタグは落とし、性別トークンを補う
        "base_tags": "1boy, short black hair, brown eyes, school uniform",
        "tsf_attitude": "女の子の姿に興味がある",
    }


def test_preset_play_profile_falls_back_without_a_profile() -> None:
    preset = CharacterPreset(
        id="p2", name="ナナシ", appearance_natural="銀髪", appearance_tags=""
    )

    profile = preset_play_profile(preset)

    assert profile["description"] == "銀髪"
    assert profile["pronoun"] == "僕"
    assert profile["gender"] == "other"
    assert profile["base_tags"] == ""


async def test_start_preset_session_copies_the_portrait(isolated_db, data_dir) -> None:
    _add_preset(isolated_db, data_dir, "p1", "ミナト", portrait=_webp(), suffix=".webp")

    session, stats, difficulty = await game_service.start_preset_session(
        preset_id="p1", difficulty="normal", nsfw_mode=True, self_mode=False
    )

    assert session.character_id is None
    assert difficulty == "normal"
    assert stats.nsfw_mode is True
    metadata = load_custom_session_metadata(session.id)
    assert metadata["character_preset_id"] == "p1"
    assert metadata["name"] == "ミナト"
    # 開始時点の立ち絵を PNG で写す。立ち絵を差し替えても元画像は残る
    copy = settings.history_images_dir / "preset_sessions" / metadata["base_image"]
    assert copy.read_bytes().startswith(b"\x89PNG")
    (data_dir / "character_images" / "p1" / "source-1.webp").unlink()
    assert copy.exists()
    # 写しは旧カスタムキャラクターの取り込み対象に混ざらない
    assert list_unimported_custom_character_profiles() == []
    # 依頼・口コミが読む人物像も同じメタデータから組み立てられる
    profile = await session_profile(session.id)
    assert profile["name"] == "ミナト"
    assert profile["tsf_attitude"] == "女の子の姿に興味がある"
    history = await session_store.get_latest_history(session.id)
    assert "1boy" in (history.after_description or "")

    # セッションを消すと、メタデータと一緒に写しも消える
    delete_custom_session_metadata(session.id)
    assert not copy.exists()
    assert load_custom_session_metadata(session.id) == {}


async def test_start_preset_session_fails_before_reset_without_a_portrait(
    isolated_db, data_dir
) -> None:
    _add_preset(isolated_db, data_dir, "p1", "ミナト", portrait=None)
    active = await session_store.create_session(image_path="")

    with pytest.raises(GameServiceError) as no_portrait:
        await game_service.start_preset_session(
            preset_id="p1", difficulty="normal", nsfw_mode=False, self_mode=False
        )
    with pytest.raises(GameServiceError) as missing:
        await game_service.start_preset_session(
            preset_id="nope", difficulty="normal", nsfw_mode=False, self_mode=False
        )

    assert no_portrait.value.code == "image_not_found"
    assert missing.value.code == "character_preset_not_found"
    # 失敗したときは、進行中のセッションをリセットしない
    still_active = await session_store.get_active_session()
    assert still_active is not None and still_active.id == active.id


async def test_salon_customers_need_a_portrait_and_the_visit_setting(
    isolated_db, data_dir
) -> None:
    _add_preset(isolated_db, data_dir, "a", "アオイ", portrait=_png())
    _add_preset(isolated_db, data_dir, "b", "ハルト", portrait=None)
    _add_preset(
        isolated_db, data_dir, "c", "ミナト", portrait=_png(), salon_enabled=False
    )

    async with isolated_db.async_factory() as db:
        customers = await list_salon_preset_customers(db)

    # 来客の種類(お客様の性別)で絞れるよう、性別も返す
    assert customers == [{"id": "a", "name": "アオイ", "gender": "man"}]


async def test_playable_presets_need_a_portrait_newest_first(
    isolated_db, data_dir
) -> None:
    from datetime import datetime

    _add_preset(isolated_db, data_dir, "a", "アオイ", portrait=_png())
    _add_preset(isolated_db, data_dir, "b", "ハルト", portrait=None)
    _add_preset(
        isolated_db, data_dir, "c", "ミナト", portrait=_png(), salon_enabled=False
    )
    with isolated_db.sync_factory() as db:
        db.get(CharacterPreset, "a").updated_at = datetime(2026, 1, 1)
        db.get(CharacterPreset, "c").updated_at = datetime(2026, 2, 1)
        db.commit()

    async with isolated_db.async_factory() as db:
        presets = await list_playable_presets(db, 5)
        limited = await list_playable_presets(db, 1)

    # 来店する設定に関わらず、立ち絵があれば始められる
    assert [item["id"] for item in presets] == ["c", "a"]
    assert presets[0]["name"] == "ミナト"
    assert presets[0]["personality"] == "明るくて人懐っこい"
    assert presets[0]["description"] == "大学二年生"
    assert presets[0]["gender"] == "man"
    assert [item["id"] for item in limited] == ["c"]


async def test_upload_portrait_stores_the_image_as_a_source_portrait(
    isolated_db, data_dir
) -> None:
    _add_preset(isolated_db, data_dir, "p1", "ミナト", portrait=None)
    encoded = base64.b64encode(_png("red")).decode()

    preset = await upload_preset_portrait("p1", f"data:image/png;base64,{encoded}")

    assert preset.portrait_path.startswith("character_images/p1/source-")
    assert preset.thumbnail_url.endswith(Path(preset.portrait_path).name)
    stored = data_dir / preset.portrait_path
    assert stored.read_bytes() == _png("red")
    # GIF のような形式は PNG に変換して置く
    gif = BytesIO()
    Image.new("RGB", (4, 4), "green").save(gif, format="GIF")
    replaced = await upload_preset_portrait(
        "p1", base64.b64encode(gif.getvalue()).decode()
    )
    assert replaced.portrait_path.endswith(".png")
    assert not stored.exists()


async def test_upload_portrait_rejects_broken_images_and_unknown_characters(
    isolated_db, data_dir
) -> None:
    _add_preset(isolated_db, data_dir, "p1", "ミナト", portrait=None)

    with pytest.raises(CharacterPresetPortraitError) as broken:
        await upload_preset_portrait("p1", base64.b64encode(b"not an image").decode())
    with pytest.raises(CharacterPresetPortraitError) as unknown:
        await upload_preset_portrait("nope", base64.b64encode(_png()).decode())

    assert broken.value.code == "invalid_image"
    assert unknown.value.code == "preset_not_found"


def _write_custom(custom_id: str, png: bytes, metadata: dict) -> None:
    """v0.11.0 以前の新規プレイが保存したカスタムキャラクターと同じ形で置く。"""
    directory = settings.history_images_dir / "custom"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{custom_id}.png").write_bytes(png)
    (directory / f"{custom_id}.json").write_text(
        json.dumps({"id": custom_id, **metadata}, ensure_ascii=False),
        encoding="utf-8",
    )


async def test_import_custom_characters_moves_them_to_the_character_screen(
    isolated_db, data_dir
) -> None:
    _write_custom(
        "custom-1",
        _png("pink"),
        {
            "name": "サクラ",
            "description": "図書委員の高校生",
            "pronoun": "僕",
            "personality": "物静か",
            "gender": "man",
            "base_tags": "1boy, short brown hair",
            "tsf_attitude": "可愛い服に憧れている",
        },
    )

    imported = await import_custom_characters()

    assert len(imported) == 1
    preset = imported[0]
    assert preset.name == "サクラ"
    assert preset.appearance_tags == "1boy, short brown hair"
    assert (data_dir / preset.portrait_path).read_bytes() == _png("pink")
    profile = json.loads(preset.profile_json)
    assert profile["memo"] == "図書委員の高校生"
    assert profile["pronoun"] == "僕"
    assert profile["gender"] == "man"
    assert profile["tsf_attitude"] == "可愛い服に憧れている"
    # 取り込み先は印から引ける(予約済みのサロンの来店を読み替えるため)
    assert imported_preset_id("custom-1") == preset.id
    assert list_unimported_custom_character_profiles() == []
    # 2回目(次の起動)は取り込むものがない
    assert await import_custom_characters() == []


async def test_import_custom_characters_skips_failures_and_retries_later(
    isolated_db, data_dir, monkeypatch
) -> None:
    _write_custom("broken", _png("red"), {"name": "アオイ"})
    _write_custom("ok", _png("blue"), {"name": "ハルト"})
    attach = character_preset_portrait.attach_preset_portrait

    def fail_on_broken(preset, source, *, generated):
        if source.stem == "broken":
            raise OSError("disk error")
        attach(preset, source, generated=generated)

    monkeypatch.setattr(
        character_preset_portrait, "attach_preset_portrait", fail_on_broken
    )
    imported = await import_custom_characters()

    # 1件の失敗で残りを止めず、失敗したものは作りかけのキャラクターを残さない
    assert [preset.name for preset in imported] == ["ハルト"]
    async with isolated_db.async_factory() as db:
        from gateway.databases.character_repo import fetch_character_presets

        assert [preset.name for preset in await fetch_character_presets(db)] == [
            "ハルト"
        ]
    assert imported_preset_id("broken") is None
    assert [item["id"] for item in list_unimported_custom_character_profiles()] == [
        "broken"
    ]

    # 次の起動で取り込み直す
    monkeypatch.setattr(character_preset_portrait, "attach_preset_portrait", attach)
    assert [preset.name for preset in await import_custom_characters()] == ["アオイ"]
