"""AI箱庭のルーター: 世界の作成・1日進める・掟・住民・変身・画像配信。

テキスト生成は失敗させて定型の出来事で進め、画像生成は小さな PNG を返す偽物にする。
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from gateway.databases.models import User
from gateway.routes.hakoniwa_router import router
from gateway.services import hakoniwa_generation as gen_module
from gateway.services import hakoniwa_service as service_module
from gateway.services.session import DEFAULT_USER_ID
from gateway.settings.config import settings

PRESETS = ["aoi", "shiori", "tamako", "ren", "ritsu"]


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def llm_outputs(monkeypatch) -> list:
    """_generate_text が順に返す値(例外なら送出)。空なら失敗させて定型へ落とす。"""
    outputs: list = []

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        if outputs:
            item = outputs.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        raise RuntimeError("LLM is not available in tests")

    monkeypatch.setattr(gen_module, "_generate_text", fake)
    return outputs


@pytest.fixture
def client(isolated_db, monkeypatch, tmp_path, llm_outputs) -> TestClient:
    with isolated_db.sync_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.commit()
    monkeypatch.setattr(settings, "history_images_dir", tmp_path / "history_images")

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _create(client: TestClient, presets=PRESETS) -> dict:
    response = client.post(
        "/api/hakoniwa/worlds",
        json={"name": "星屑荘", "preset_ids": presets, "language": "ja"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_catalog_lists_presets_and_rules(client: TestClient) -> None:
    body = client.get("/api/hakoniwa/catalog?language=en").json()

    assert [p["id"] for p in body["presets"]] == PRESETS
    assert body["presets"][0]["name"] == "Aoi Takase"
    assert body["presets"][0]["avatar_url"] == "/hakoniwa-assets/avatar_aoi.png"
    assert {c["id"] for c in body["rule_cards"]} >= {"swap", "dress"}


def test_create_world_and_list(client: TestClient) -> None:
    world = _create(client)

    assert world["day"] == 1
    assert [r["name"] for r in world["residents"]][0] == "高瀬 葵"
    assert (
        world["residents"][0]["display_avatar_url"] == "/hakoniwa-assets/avatar_aoi.png"
    )
    listed = client.get("/api/hakoniwa/worlds").json()["worlds"]
    assert listed[0]["id"] == world["id"]
    assert listed[0]["resident_count"] == 5


def test_create_world_validation(client: TestClient) -> None:
    blank = client.post(
        "/api/hakoniwa/worlds", json={"name": " ", "preset_ids": PRESETS}
    )
    few = client.post("/api/hakoniwa/worlds", json={"name": "a", "preset_ids": ["aoi"]})
    missing = client.get("/api/hakoniwa/worlds/00000000-0000-0000-0000-000000000000")

    assert blank.json()["detail"]["error"] == "empty_name"
    assert few.json()["detail"]["error"] == "too_few_residents"
    assert missing.status_code == 404


def test_advance_day_with_template_fallback(client: TestClient) -> None:
    world = _create(client)

    response = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/day", json={"language": "ja"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["world"]["day"] == 2
    assert len(body["new_events"]) == 3
    assert all(event["source"] == "template" for event in body["new_events"])
    titles = [event["title"] for event in body["new_events"]]
    assert len(set(titles)) == len(titles)
    ids = {r["id"] for r in body["world"]["residents"]}
    for event in body["new_events"]:
        assert set(event["participants"]) <= ids
        assert {line["speaker"] for line in event["lines"]} <= ids


def test_swap_rule_swaps_display_avatars(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren"])

    swapped = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/rules/swap", json={"active": True}
    ).json()

    by_id = {r["id"]: r for r in swapped["residents"]}
    assert by_id["aoi"]["display_avatar_url"] == "/hakoniwa-assets/avatar_ren.png"
    assert by_id["aoi"]["swapped_with"] == "ren"
    assert by_id["aoi"]["body_gender"] == "male"
    dressed = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/rules/dress", json={"active": True}
    ).json()
    by_id = {r["id"]: r for r in dressed["residents"]}
    assert by_id["ren"]["display_avatar_url"] == "/hakoniwa-assets/avatar_aoi_dress.png"


def test_custom_rules_and_favorites(client: TestClient) -> None:
    world = _create(client)
    wid = world["id"]

    added = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules",
        json={"name": "猫の日", "text": "猫耳を付ける"},
    ).json()
    rule = next(card for card in added["rule_cards"] if card["custom"])
    toggled = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/{rule['id']}", json={"active": True}
    )
    assert rule["id"] in toggled.json()["active_rules"]
    deleted = client.delete(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}"
    ).json()
    assert rule["id"] not in deleted["active_rules"]

    day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()
    event_id = day["new_events"][0]["id"]
    fav = client.put(
        f"/api/hakoniwa/worlds/{wid}/events/{event_id}/favorite",
        json={"favorite": True},
    ).json()
    assert next(e for e in fav["events"] if e["id"] == event_id)["favorite"] is True


def test_custom_resident_keeps_user_text_separate_from_tags(
    client: TestClient, llm_outputs: list
) -> None:
    world = _create(client, ["aoi", "ren"])
    llm_outputs.append("1girl, silver hair, red eyes, maid outfit")

    response = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents",
        json={
            "name": "ミナ",
            "personality": "明るい",
            "gender": "female",
            "appearance_text": "銀髪で赤い瞳のメイド",
        },
    )

    body = response.json()
    resident = next(
        r for r in body["world"]["residents"] if r["id"] == body["resident_id"]
    )
    assert resident["appearance_text"] == "銀髪で赤い瞳のメイド"
    assert resident["base_tags"] == "1girl, silver hair, red eyes, maid outfit"
    assert resident["display_avatar_url"] is None
    assert body["tag_expansion_failed"] is False


def test_tag_expansion_failure_keeps_default_tags(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren"])

    body = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents",
        json={
            "name": "ケン",
            "personality": "静か",
            "gender": "male",
            "appearance_text": "黒髪",
        },
    ).json()

    resident = next(
        r for r in body["world"]["residents"] if r["id"] == body["resident_id"]
    )
    assert body["tag_expansion_failed"] is True
    assert resident["base_tags"].startswith("1boy")
    assert resident["appearance_text"] == "黒髪"


def test_generate_avatar_and_serve_image(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]

    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/avatar", json={"variant": "base"}
    ).json()

    aoi = next(r for r in body["world"]["residents"] if r["id"] == "aoi")
    assert aoi["avatar_url"].startswith(f"/hakoniwa/worlds/{wid}/images/base_aoi_")
    image = client.get("/api" + aoi["avatar_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    traversal = client.get(f"/api/hakoniwa/worlds/{wid}/images/..%2Fsecret.png")
    assert traversal.status_code == 404


def test_transform_records_events_and_can_be_cleared(
    client: TestClient, llm_outputs: list
) -> None:
    world = _create(client, ["aoi", "ren", "ritsu"])
    wid = world["id"]
    llm_outputs.append("1girl, short dark green hair, green eyes, maid outfit")

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/ren/transform",
        json={"instruction": "メイド服の女の子にして", "language": "ja"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    ren = next(r for r in body["world"]["residents"] if r["id"] == "ren")
    assert ren["transformation"]["tags"].startswith("1girl")
    assert ren["body_gender"] == "female"
    assert ren["display_kind"] == "transform"
    assert [e.get("kind") for e in body["new_events"]] == ["transform", None]
    assert body["new_events"][1]["source"] == "template"
    image = ren["transformation"]["image"]

    cleared = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/ren/transform/clear", json={}
    )
    ren = next(r for r in cleared.json()["residents"] if r["id"] == "ren")
    assert ren["transformation"] is None
    reapplied = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/ren/transform/reapply",
        json={"image": image},
    )
    ren = next(r for r in reapplied.json()["residents"] if r["id"] == "ren")
    assert ren["transformation"]["image"] == image


def test_transform_fails_cleanly_when_tags_cannot_be_made(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren"])

    response = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents/ren/transform",
        json={"instruction": "メイド服"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "tag_conversion_failed"
    after = client.get(f"/api/hakoniwa/worlds/{world['id']}").json()
    assert after["events"] == []


@pytest.mark.parametrize("initial_look", ["transform", "dress"])
def test_partial_transform_uses_current_look_tags(
    client: TestClient, llm_outputs: list, monkeypatch, initial_look: str
) -> None:
    world = _create(client, ["aoi", "ren"])
    path = f"/api/hakoniwa/worlds/{world['id']}"
    if initial_look == "transform":
        expected_tags = "1girl, long black hair, blue dress"
        llm_outputs.append(expected_tags)
        first = client.post(
            f"{path}/residents/ren/transform", json={"instruction": "女性の姿に"}
        )
        assert first.status_code == 200
    else:
        dressed = client.put(f"{path}/rules/dress", json={"active": True})
        expected_tags = next(
            r for r in dressed.json()["residents"] if r["id"] == "ren"
        )["dress_tags"]
    captured = []

    async def convert(instruction, base_tags, *, novelai_model):
        captured.append(base_tags)
        return base_tags + ", silver hair"

    monkeypatch.setattr(service_module, "convert_change_to_tags", convert)
    response = client.post(
        f"{path}/residents/ren/transform", json={"instruction": "髪だけ銀色に"}
    )
    assert response.status_code == 200
    assert captured == [expected_tags]
    ren = next(r for r in response.json()["world"]["residents"] if r["id"] == "ren")
    assert ren["transformation"]["tags"] == expected_tags + ", silver hair"
    assert ren["body_gender"] == ("female" if initial_look == "transform" else "male")


def test_greet_and_remove_resident(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren", "ritsu"])
    wid = world["id"]

    greeting = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/greet", json={"language": "ja"}
    ).json()
    assert greeting["source"] == "template"
    assert greeting["text"]

    removed = client.delete(f"/api/hakoniwa/worlds/{wid}/residents/ritsu").json()
    assert [r["id"] for r in removed["residents"]] == ["aoi", "ren"]
    too_few = client.delete(f"/api/hakoniwa/worlds/{wid}/residents/ren")
    assert too_few.json()["detail"]["error"] == "too_few_residents"


def test_delete_world_removes_images(client: TestClient, tmp_path) -> None:
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    client.post(f"/api/hakoniwa/worlds/{wid}/residents/aoi/avatar", json={})
    world_dir = tmp_path / "hakoniwa" / wid
    assert world_dir.is_dir()

    assert client.delete(f"/api/hakoniwa/worlds/{wid}").status_code == 204
    assert not world_dir.exists()
    assert client.get(f"/api/hakoniwa/worlds/{wid}").status_code == 404


def _add_character(isolated_db, data_dir, preset_id: str, gender: str | None) -> None:
    import json

    from gateway.databases.models import CharacterPreset

    directory = data_dir / "character_images" / preset_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source-1.png").write_bytes(_png())
    profile = {"personality": "人懐っこい", "pronoun": "僕"}
    if gender:
        profile["gender"] = gender
    with isolated_db.sync_factory() as db:
        db.add(
            CharacterPreset(
                id=preset_id,
                name="ユウ",
                appearance_natural="黒髪の青年",
                appearance_tags="short black hair, brown eyes, school uniform",
                profile_json=json.dumps(profile, ensure_ascii=False),
                portrait_path=f"character_images/{preset_id}/source-1.png",
            )
        )
        db.commit()


def test_registered_character_joins_with_copied_portrait(
    client: TestClient, isolated_db, tmp_path
) -> None:
    _add_character(isolated_db, tmp_path, "c1", "man")
    response = client.post(
        "/api/hakoniwa/worlds",
        json={
            "name": "w",
            "preset_ids": ["aoi"],
            "characters": [{"character_preset_id": "c1"}],
        },
    )

    assert response.status_code == 200, response.text
    character = response.json()["residents"][1]
    assert character["source"] == "character"
    assert character["name"] == "ユウ"
    assert character["gender"] == "male"
    assert character["base_tags"].startswith("1boy")
    assert "/images/avatar_" in character["display_avatar_url"]
    assert client.get("/api" + character["display_avatar_url"]).status_code == 200


def test_character_without_gender_requires_choice(
    client: TestClient, isolated_db, tmp_path
) -> None:
    _add_character(isolated_db, tmp_path, "c2", None)
    world = _create(client, ["aoi", "ren"])

    missing = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents/from-character",
        json={"character_preset_id": "c2"},
    )
    chosen = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents/from-character",
        json={"character_preset_id": "c2", "gender": "female"},
    )
    again = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents/from-character",
        json={"character_preset_id": "c2", "gender": "female"},
    )

    assert missing.json()["detail"]["error"] == "gender_required"
    assert chosen.status_code == 200
    assert again.json()["detail"]["error"] == "duplicate_resident"
