"""カスタム画像のキャラクターに付けた TSF への態度の保存と引き継ぎ。"""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from gateway.databases.models import User
from gateway.services.custom_sessions import (
    load_custom_character_profile,
    load_custom_session_metadata,
)
from gateway.services.game_service import game_service
from gateway.services.session import DEFAULT_USER_ID, session_store
from gateway.settings.config import settings


def _png_base64() -> str:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.asyncio
async def test_custom_session_saves_and_restores_tsf_attitude(
    isolated_db, monkeypatch, tmp_path
) -> None:
    history_dir = tmp_path / "data" / "history_images"
    history_dir.mkdir(parents=True)
    monkeypatch.setattr(settings, "history_images_dir", history_dir)
    monkeypatch.setattr(session_store, "_history_images_dir", history_dir)
    async with isolated_db.async_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        await db.commit()

    first, _, _ = await game_service.start_custom_session(
        custom_character_id=None,
        image=_png_base64(),
        name="テスト",
        description="",
        pronoun="僕",
        personality="",
        gender="man",
        base_tags="",
        difficulty="normal",
        nsfw_mode=False,
        self_mode=False,
        tsf_attitude=" 可愛い服に密かに憧れている ",
    )

    metadata = load_custom_session_metadata(first.id)
    assert metadata["tsf_attitude"] == "可愛い服に密かに憧れている"
    custom_id = metadata["custom_character_id"]
    profile = load_custom_character_profile(custom_id)
    assert profile["tsf_attitude"] == "可愛い服に密かに憧れている"

    # 保存済みの人物設定で始め直すと、TSF への態度も引き継ぐ
    second, _, _ = await game_service.start_custom_session(
        custom_character_id=custom_id,
        image=None,
        name="",
        description="",
        pronoun="",
        personality="",
        gender=None,
        base_tags="",
        difficulty="normal",
        nsfw_mode=False,
        self_mode=False,
        use_saved_profile=True,
    )
    assert load_custom_session_metadata(second.id)["tsf_attitude"] == (
        "可愛い服に密かに憧れている"
    )
