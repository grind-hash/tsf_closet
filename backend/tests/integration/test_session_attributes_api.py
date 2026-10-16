"""セッション属性 API と、指示・属性の文字数上限の結合テスト。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from gateway.consts.play_limits import (
    ATTRIBUTE_TEXT_MAX_LENGTH,
    INSTRUCTION_MAX_LENGTH,
    REALITY_ATTRIBUTE_PREFIX,
)
from gateway.databases.models import User
from gateway.routes.game_router import router
from gateway.schemas.play import PlayRequest, PlayStreamRequest
from gateway.services.session import session_store


async def _seed(factory) -> str:
    async with factory() as db:
        db.add(User(id="default-user"))
        await db.commit()
    created = await session_store.create_session(image_path="session/start.png")
    return created.id


@pytest.fixture
def client_and_session(isolated_db):
    session_id = asyncio.run(_seed(isolated_db.async_factory))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as test_client:
        yield test_client, session_id


def test_attribute_accepts_reality_attribute_of_max_instruction(client_and_session):
    client, session_id = client_and_session
    longest = REALITY_ATTRIBUTE_PREFIX + "a" * INSTRUCTION_MAX_LENGTH
    assert len(longest) == ATTRIBUTE_TEXT_MAX_LENGTH

    res = client.post(
        "/api/game/attributes",
        json={"session_id": session_id, "attribute_text": longest},
    )
    assert res.status_code == 200
    assert res.json()["attribute"]["attribute_text"] == longest

    res = client.post(
        "/api/game/attributes",
        json={"session_id": session_id, "attribute_text": longest + "a"},
    )
    assert res.status_code == 422


def test_update_attribute_keeps_order_and_original_on_failure(client_and_session):
    client, session_id = client_and_session
    first = client.post(
        "/api/game/attributes",
        json={"session_id": session_id, "attribute_text": "猫耳"},
    ).json()["attribute"]
    client.post(
        "/api/game/attributes",
        json={"session_id": session_id, "attribute_text": "眼鏡"},
    )

    res = client.patch(
        f"/api/game/attributes/{first['id']}",
        json={"attribute_text": "白い猫耳"},
    )
    assert res.status_code == 200
    assert res.json()["attribute"]["attribute_text"] == "白い猫耳"

    # 上限を超える更新は弾かれ、元の属性はそのまま残る
    res = client.patch(
        f"/api/game/attributes/{first['id']}",
        json={"attribute_text": "a" * (ATTRIBUTE_TEXT_MAX_LENGTH + 1)},
    )
    assert res.status_code == 422

    res = client.get(f"/api/game/attributes/{session_id}")
    texts = [a["attribute_text"] for a in res.json()["attributes"]]
    assert texts == ["白い猫耳", "眼鏡"]

    res = client.patch("/api/game/attributes/missing", json={"attribute_text": "x"})
    assert res.status_code == 404


@pytest.mark.parametrize("model", [PlayRequest, PlayStreamRequest])
def test_instruction_limit(model):
    assert model(instruction="a" * INSTRUCTION_MAX_LENGTH).instruction
    with pytest.raises(ValidationError):
        model(instruction="a" * (INSTRUCTION_MAX_LENGTH + 1))
