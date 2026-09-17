"""開始素材スナップショット(source_snapshot)の純関数と人物解決。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services import source_snapshot as snap
from gateway.services.source_snapshot import (
    history_visual_description,
    identity_tags_only,
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
