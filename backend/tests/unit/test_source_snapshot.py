"""開始素材スナップショット(source_snapshot)の純関数と人物解決。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services import source_snapshot as snap
from gateway.services.source_snapshot import (
    build_source_snapshot,
    history_visual_description,
    identity_tags_only,
    prompt_expander_visual_description,
    resolve_session_identity,
)


def test_identity_tags_only_drops_clothing_and_scene_tags() -> None:
    assert (
        identity_tags_only("1girl, brown hair, maid dress, apron, standing, mirror")
        == "1girl, brown hair, apron"
    )
    assert identity_tags_only("") == ""


def test_history_visual_description_splits_tags() -> None:
    history = SimpleNamespace(
        after_description="1girl, brown hair, black eyes, school uniform, skirt, standing",
        before_description=None,
    )
    appearance, clothing = history_visual_description(history)
    assert appearance == "1girl, brown hair, black eyes"
    assert clothing == "school uniform, skirt"


def test_history_visual_description_falls_back_to_prose() -> None:
    history = SimpleNamespace(
        after_description=None, before_description="茶髪の少女が制服を着ている"
    )
    assert history_visual_description(history) == ("茶髪の少女が制服を着ている", "")


def test_prompt_expander_visual_description_drops_prose_and_meta() -> None:
    """漫画の筋書き(英文)や画質・吹き出し・情景の指定を外見に含めない。"""
    appearance, clothing = prompt_expander_visual_description(
        "1girl, moe, anime, tsf, transformation, from male to female, breasts, "
        "underwear, pink bra, fitting room, mirror, surprised expression, "
        "japanese text, speech bubble, border, very aesthetic, best quality, "
        "There are four comic panels. The first panel shows a young man, "
        "now fully transformed, long hair",
        [
            "solo, long hair, silver hair, school uniform, looking at mirror, "
            'thought bubble: "え、これが僕？", shy pose'
        ],
    )
    assert appearance == (
        "1girl, moe, anime, from male to female, breasts, solo, long hair, silver hair"
    )
    assert clothing == "underwear, pink bra, school uniform"


def test_prompt_expander_visual_description_empty_prompt() -> None:
    assert prompt_expander_visual_description("", []) == ("", "")


@pytest.mark.asyncio
async def test_build_source_snapshot_uses_initial_history_for_unchanged_session(
    monkeypatch, tmp_path
) -> None:
    """画像を変えていないセッションは、初期状態の履歴から外見を取る。

    現在画像は開始時の元画像のままで、初期状態の履歴は同じ画像を別名で
    保存しているため、ファイル名では履歴を特定できない。
    """
    original_image = tmp_path / "custom" / "original.png"
    original_image.parent.mkdir()
    original_image.write_bytes(b"image")
    initial_history = SimpleNamespace(
        image_path="history_images/initial-copy.png",
        after_description="1girl, silver hair, purple eyes, school uniform",
        before_description="",
    )
    monkeypatch.setattr(
        snap.session_store,
        "get_session_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id="session-1",
                user_id=snap.DEFAULT_USER_ID,
                character_id=None,
                current_image_path=str(original_image),
            )
        ),
    )
    monkeypatch.setattr(
        snap.session_store, "get_history", AsyncMock(return_value=[initial_history])
    )
    monkeypatch.setattr(
        snap.session_store, "get_session_timeline_until", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        snap.session_store, "get_session_attributes", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        snap.session_store, "get_session_stats", AsyncMock(return_value=None)
    )

    snapshot, image_path, appearance, _ = await build_source_snapshot("session-1", None)

    assert image_path == original_image
    assert appearance == "1girl, silver hair, purple eyes"
    assert snapshot["clothing"] == "school uniform"


@pytest.mark.asyncio
async def test_resolve_session_identity_prefers_self_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        snap.session_store,
        "get_self_profile",
        AsyncMock(return_value={"display_name": "自分", "pronoun": "俺"}),
    )
    session = SimpleNamespace(id="s1", self_mode=True, character_id="char1")
    assert await resolve_session_identity(session) == ("自分", "俺")


@pytest.mark.asyncio
async def test_resolve_session_identity_template_then_custom(monkeypatch) -> None:
    session = SimpleNamespace(id="s1", self_mode=False, character_id="char1")
    name, pronoun = await resolve_session_identity(session)
    assert name == "水瀬ユウヤ"
    assert pronoun == "僕"

    monkeypatch.setattr(
        snap,
        "load_custom_session_metadata",
        lambda session_id: {"name": "サクラ", "pronoun": "私"},
    )
    custom = SimpleNamespace(id="s2", self_mode=False, character_id=None)
    assert await resolve_session_identity(custom) == ("サクラ", "私")

    monkeypatch.setattr(snap, "load_custom_session_metadata", lambda session_id: {})
    unknown = SimpleNamespace(id="s3", self_mode=False, character_id=None)
    assert await resolve_session_identity(unknown) == ("キャラクター", "僕")
