"""AI箱庭のルーター: 世界の作成・1日進める・掟・住民・変身・画像配信。

テキスト生成は失敗させて定型の出来事で進め、画像生成は小さな PNG を返す偽物にする。
"""

from __future__ import annotations

import json
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
    monkeypatch.setattr(settings, "tavily_api_key", "")
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

    response = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/rules/swap",
        json={"active": True, "area_id": "living"},
    ).json()
    swapped = response["world"]
    # 切り替え直後の反応: 入れ替わった二人の一言(年代記には残らない)
    reaction = response["reaction"]
    assert reaction["card_id"] == "swap" and reaction["active"] is True
    assert {line["resident_id"] for line in reaction["lines"]} == {"aoi", "ren"}
    assert swapped["events"] == []

    by_id = {r["id"]: r for r in swapped["residents"]}
    assert by_id["aoi"]["display_avatar_url"] == "/hakoniwa-assets/avatar_ren.png?v=3"
    assert by_id["aoi"]["swapped_with"] == "ren"
    assert by_id["aoi"]["body_gender"] == "male"
    dressed = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/rules/dress", json={"active": True}
    ).json()["world"]
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
    assert rule["id"] in toggled.json()["world"]["active_rules"]
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


def test_resident_tags_are_made_from_text_and_saved_as_sent(
    client: TestClient, llm_outputs: list
) -> None:
    world = _create(client, ["aoi", "ren"])
    # 変換が逆の性別を書いても、住民の性別にそろえる
    llm_outputs.append("1boy, silver hair, red eyes, maid outfit")

    made = client.post(
        "/api/hakoniwa/tags/resident",
        json={"appearance_text": "銀髪で赤い瞳のメイド", "gender": "female"},
    )
    assert made.status_code == 200, made.text
    tags = made.json()["tags"]
    assert tags == "1girl, silver hair, red eyes, maid outfit"
    # 英語のタグなら LLM を呼ばずに整える
    english = client.post(
        "/api/hakoniwa/tags/resident",
        json={"appearance_text": "black hair, suit", "gender": "male"},
    ).json()
    assert english["tags"] == "1boy, black hair, suit"

    response = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents",
        json={
            "name": "ミナ",
            "personality": "明るい",
            "gender": "female",
            "appearance_text": "銀髪で赤い瞳のメイド",
            "base_tags": tags,
        },
    )

    body = response.json()
    resident = next(
        r for r in body["world"]["residents"] if r["id"] == body["resident_id"]
    )
    assert resident["appearance_text"] == "銀髪で赤い瞳のメイド"
    assert resident["base_tags"] == tags
    assert resident["dress_tags"] == ""
    assert resident["display_avatar_url"] is None


def test_resident_needs_usual_tags_and_tag_failure_is_reported(
    client: TestClient,
) -> None:
    world = _create(client, ["aoi", "ren"])

    missing = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/residents",
        json={
            "name": "ケン",
            "personality": "静か",
            "gender": "male",
            "appearance_text": "黒髪",
        },
    )
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "tags_required"

    failed = client.post(
        "/api/hakoniwa/tags/resident",
        json={"appearance_text": "黒髪", "gender": "male", "dress": True},
    )
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "tags_failed"
    empty = client.post(
        "/api/hakoniwa/tags/resident", json={"appearance_text": " ", "gender": "male"}
    )
    assert empty.json()["detail"]["code"] == "look_source_empty"


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


def test_reality_with_look_is_accepted_as_always_true(
    client: TestClient, llm_outputs: list
) -> None:
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    before = world["dissonance"]["value"]
    llm_outputs.append("1girl, brown hair, bikini")

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/realities",
        json={"instruction": "昔からグラビアアイドル", "change_look": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    aoi = next(r for r in body["world"]["residents"] if r["id"] == "aoi")
    assert [item["text"] for item in aoi["realities"]] == ["昔からグラビアアイドル"]
    # 姿は変身と同じ仕組みで付くが、改変の姿として区別し、慣れの段階は始めない
    assert aoi["transformation"]["kind"] == "reality"
    assert aoi["display_kind"] == "transform"
    assert aoi["adaptation"] is None
    assert [e.get("kind") for e in body["new_events"]] == ["reality"]
    assert body["world"]["dissonance"]["value"] > before

    # 改変を消すと、その改変で変えた姿も解ける
    reality_id = aoi["realities"][0]["id"]
    removed = client.delete(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/realities/{reality_id}"
    )
    aoi = next(r for r in removed.json()["residents"] if r["id"] == "aoi")
    assert aoi["realities"] == []
    assert aoi["transformation"] is None
    missing = client.delete(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/realities/{reality_id}"
    )
    assert missing.json()["detail"]["code"] == "reality_not_found"


def test_reality_without_look_changes_only_the_facts(
    client: TestClient, llm_outputs: list
) -> None:
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/ren/realities",
        json={"instruction": "昔から料理が得意", "change_look": False},
    )

    assert response.status_code == 200, response.text
    ren = next(r for r in response.json()["world"]["residents"] if r["id"] == "ren")
    assert ren["transformation"] is None
    assert ren["realities"][0]["text"] == "昔から料理が得意"
    for index in range(4):
        client.post(
            f"/api/hakoniwa/worlds/{wid}/residents/ren/realities",
            json={"instruction": f"事実{index}", "change_look": False},
        )
    over = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/ren/realities",
        json={"instruction": "6件目", "change_look": False},
    )
    assert over.json()["detail"]["code"] == "too_many_realities"


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
            r for r in dressed.json()["world"]["residents"] if r["id"] == "ren"
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


def test_world_lists_areas_and_furniture_and_places_items(client: TestClient) -> None:
    world = _create(client, ["aoi", "ren"])

    assert [area["id"] for area in world["areas"]] == ["living", "garden", "study"]
    assert world["areas"][1]["background_url"] == "/hakoniwa-assets/area_garden.png"
    assert {item["id"] for item in world["furniture_catalog"]} >= {"lamp", "kotatsu"}
    ren = next(r for r in world["residents"] if r["id"] == "ren")
    assert ren["current_area"] == "garden"

    placed = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/furniture",
        json={"area_id": "garden", "slot": 1, "furniture_id": "lamp"},
    ).json()
    assert placed["areas"][1]["slots"][1]["furniture_id"] == "lamp"
    unknown = client.put(
        f"/api/hakoniwa/worlds/{world['id']}/furniture",
        json={"area_id": "moon", "slot": 1, "furniture_id": "lamp"},
    )
    assert unknown.status_code == 404


def test_day_returns_digest_and_event_areas(client: TestClient) -> None:
    world = _create(client)

    body = client.post(f"/api/hakoniwa/worlds/{world['id']}/day", json={}).json()

    assert body["digest"]["day"] == 1
    assert body["digest"]["highlight"]["event_id"] in {
        event["id"] for event in body["new_events"]
    }
    assert body["world"]["last_digest"] == body["digest"]
    assert all(
        event["area"] in {"living", "garden", "study"} for event in body["new_events"]
    )


def test_scene_image_is_generated_with_fallback_tags(
    client: TestClient, monkeypatch
) -> None:
    captured: dict = {}

    async def fake_scene(request, *, image_model, nsfw_mode):
        captured.update(request)
        return _png()

    monkeypatch.setattr(service_module, "generate_scene_bytes", fake_scene)
    world = _create(client, ["aoi", "ren"])
    day = client.post(f"/api/hakoniwa/worlds/{world['id']}/day", json={}).json()
    event = next(e for e in day["new_events"] if len(e["participants"]) == 2)

    body = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/events/{event['id']}/scene-image",
        json={},
    ).json()

    assert "cinematic scene" in captured["prompt"]
    assert len(captured["characters"]) == 2
    updated = next(e for e in body["world"]["events"] if e["id"] == event["id"])
    assert updated["scene_image_url"].startswith(
        f"/hakoniwa/worlds/{world['id']}/images/scene_"
    )
    assert updated["scene_suggestion"] is None
    assert client.get("/api" + updated["scene_image_url"]).status_code == 200
    missing = client.post(
        f"/api/hakoniwa/worlds/{world['id']}/events/nope/scene-image", json={}
    )
    assert missing.status_code == 404


def test_dissonance_toggle_and_confrontation_on_rule_changes(client: TestClient):
    world = _create(client)
    wid = world["id"]
    assert world["dissonance"] == {
        "enabled": True,
        "value": 0,
        "stage": "stillness",
        "acknowledged": False,
        "next_stage": "stirring",
        "remaining": 20,
    }

    confrontation = None
    for index in range(10):
        body = client.put(
            f"/api/hakoniwa/worlds/{wid}/rules/dress",
            json={"active": index % 2 == 0, "language": "ja"},
        ).json()
        if body["new_events"]:
            confrontation = body
    assert confrontation is not None
    event = confrontation["new_events"][0]
    assert event["kind"] == "confrontation"
    assert event["scene_suggestion"]["level"] == "strong"
    assert confrontation["world"]["dissonance"]["acknowledged"] is True
    assert confrontation["world"]["dissonance"]["value"] == 40
    ritsu = next(r for r in confrontation["world"]["residents"] if r["id"] == "ritsu")
    kinds = [memory["kind"] for memory in ritsu["memories"]]
    assert "confrontation" in kinds
    assert (
        ritsu["memories"][-1]["text"]
        == "世界を書き換えている存在（書き手）へ呼びかけた"
    )

    off = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"dissonance_enabled": False}
    ).json()
    assert off["dissonance"]["enabled"] is False
    assert off["image_model"] == "default"


def test_world_created_without_dissonance_never_gains(client: TestClient):
    response = client.post(
        "/api/hakoniwa/worlds",
        json={"name": "静かな荘", "preset_ids": PRESETS, "dissonance_enabled": False},
    )
    wid = response.json()["id"]

    body = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/dress", json={"active": True}
    ).json()

    assert body["world"]["dissonance"]["enabled"] is False
    assert body["world"]["dissonance"]["value"] == 0
    day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()
    assert day["digest"]["dissonance"] is None


def test_swap_rule_shows_adaptation_and_remnant(client: TestClient):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]

    swapped = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/swap", json={"active": True}
    ).json()["world"]
    assert {r["adaptation"]["kind"] for r in swapped["residents"]} == {"swap"}
    assert {r["world_adaptation"]["stage"] for r in swapped["residents"]} == {0}

    for _ in range(2):
        day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()
    assert any(arc["kind"] == "swap" for arc in day["world"]["story_arcs"])
    assert "arcs" in day["digest"]

    ended = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/swap",
        json={"active": False, "language": "en"},
    ).json()["world"]
    for resident in ended["residents"]:
        assert resident["adaptation"] is None
        assert resident["remnant"]["kind"] == "swap"
        assert resident["remnant"]["text"]


def _custom_rule(client, wid, **body):
    added = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules",
        json={"name": "メイドの日", "text": "全員がメイド服で過ごす", **body},
    ).json()
    rule = next(card for card in added["rule_cards"] if card["custom"])
    client.put(f"/api/hakoniwa/worlds/{wid}/rules/{rule['id']}", json={"active": True})
    return rule


def test_rule_look_generates_one_resident_at_a_time(
    client: TestClient, llm_outputs, monkeypatch
):
    import asyncio

    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(client, wid, appearance_tags="maid outfit, 1girl")
    assert rule["appearance_tags"] == "maid outfit"
    assert rule["look"] == {
        "ready": 0,
        "stale": 0,
        "total": 2,
        "pending": ["aoi", "ren"],
    }

    running = {"now": 0, "max": 0}
    captured: list[str] = []

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        captured.append(tags)
        await asyncio.sleep(0)
        running["now"] -= 1
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    llm_outputs.extend(["1girl, brown hair, maid outfit", "brown hair, maid outfit"])

    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look", json={}
    ).json()

    assert (body["generated"], body["failed"]) == (2, 0)
    assert running["max"] == 1
    # 男性の住民のタグには 1boy が付く
    assert captured[1].startswith("1boy, brown hair, maid outfit")
    by_id = {r["id"]: r for r in body["world"]["residents"]}
    assert by_id["aoi"]["display_kind"] == "rule"
    card = next(c for c in body["world"]["rule_cards"] if c["id"] == rule["id"])
    assert card["look"] == {"ready": 2, "stale": 0, "total": 2, "pending": []}

    again = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look", json={}
    ).json()
    assert again["generated"] == 0


def test_rule_look_for_one_resident_saves_each_time(
    client: TestClient, llm_outputs, monkeypatch
):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(client, wid, appearance_tags="maid outfit")

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    llm_outputs.extend(["1girl, brown hair, maid outfit"])
    url = f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look"

    first = client.post(url, json={"resident_id": "aoi"}).json()
    assert (first["generated"], first["failed"]) == (1, 0)
    card = next(c for c in first["world"]["rule_cards"] if c["id"] == rule["id"])
    # 1人ぶんで保存され、進み具合が数に出る
    assert card["look"]["ready"] == 1
    assert card["look"]["pending"] == ["ren"]
    saved = client.get(f"/api/hakoniwa/worlds/{wid}").json()
    saved_card = next(c for c in saved["rule_cards"] if c["id"] == rule["id"])
    assert saved_card["look"]["ready"] == 1

    # 生成済みの住民をもう一度頼んでも、描き直しでなければ何もしない
    again = client.post(url, json={"resident_id": "aoi"}).json()
    assert (again["generated"], again["failed"]) == (0, 0)

    missing = client.post(url, json={"resident_id": "nobody"})
    assert missing.json()["detail"]["code"] == "resident_not_found"


def test_world_memo_look_is_planned_then_drawn_one_by_one(
    client: TestClient, llm_outputs, monkeypatch
):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    captured: list[str] = []

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        captured.append(tags)
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings",
        json={"world_memo": "住民は全員グラビアアイドルとして暮らしている"},
    )
    llm_outputs.append(
        '{"changes_look": true, "appearance_tags": "1girl, bikini", "body_gender": "keep"}'
    )
    planned = client.post(f"/api/hakoniwa/worlds/{wid}/memo-look/plan", json={})
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["changes_look"] is True
    # 人物の性別・人数のタグは外す
    assert body["world"]["memo_look"]["tags"] == "bikini"
    assert body["world"]["memo_look"]["pending"] == ["aoi", "ren"]
    assert body["world"]["memo_look_planned"] is True

    # 同じメモでは LLM を呼ばない(呼べば出力が足りず失敗する)
    again = client.post(f"/api/hakoniwa/worlds/{wid}/memo-look/plan", json={})
    assert again.json()["changes_look"] is True

    llm_outputs.append("1girl, brown hair, bikini")
    drawn = client.post(
        f"/api/hakoniwa/worlds/{wid}/memo-look", json={"resident_id": "aoi"}
    ).json()
    assert drawn["generated"] == 1
    aoi = next(r for r in drawn["world"]["residents"] if r["id"] == "aoi")
    assert aoi["display_kind"] == "memo"
    assert drawn["world"]["memo_look"]["pending"] == ["ren"]

    # メモを変えると、確かめ直すまでメモの姿は効かない
    client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"world_memo": "文体は軽めに"}
    )
    changed = client.get(f"/api/hakoniwa/worlds/{wid}").json()
    assert changed["memo_look"] is None
    assert changed["memo_look_planned"] is False
    aoi = next(r for r in changed["residents"] if r["id"] == "aoi")
    assert aoi["display_kind"] != "memo"
    llm_outputs.append(
        '{"changes_look": false, "appearance_tags": "", "body_gender": "keep"}'
    )
    style_only = client.post(f"/api/hakoniwa/worlds/{wid}/memo-look/plan", json={})
    assert style_only.json()["changes_look"] is False
    missing = client.post(f"/api/hakoniwa/worlds/{wid}/memo-look", json={})
    assert missing.json()["detail"]["code"] == "no_memo_look"


def test_body_changing_rule_look_sets_gender_token(
    client: TestClient, llm_outputs, monkeypatch
):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(
        client,
        wid,
        appearance_tags="long hair, chiffon blouse",
        body_gender="female",
    )
    assert rule["body_gender"] == "female"
    assert rule["appearance_tags"] == "long hair, chiffon blouse"

    captured: list[str] = []

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        captured.append(tags)
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    # 変換が男性の性別トークンを残しても、掟の性別に差し替える
    llm_outputs.extend(
        ["1girl, long hair, chiffon blouse", "1boy, long hair, chiffon blouse"]
    )
    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look", json={}
    ).json()

    assert body["generated"] == 2
    assert captured[1] == "1girl, long hair, chiffon blouse"
    by_id = {r["id"]: r for r in body["world"]["residents"]}
    assert by_id["ren"]["body_gender"] == "female"

    edited = client.patch(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}",
        json={
            "name": "メイドの日",
            "text": "全員がメイド服で過ごす",
            "appearance_tags": "long hair, chiffon blouse",
        },
    ).json()
    card = next(c for c in edited["rule_cards"] if c["id"] == rule["id"])
    assert card["body_gender"] is None
    assert card["look"] == {
        "ready": 0,
        "stale": 2,
        "total": 2,
        "pending": ["aoi", "ren"],
    }
    by_id = {r["id"]: r for r in edited["residents"]}
    assert by_id["ren"]["body_gender"] == "male"


def test_rule_without_look_cannot_generate_and_tags_are_made_on_request(
    client: TestClient, llm_outputs
):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(client, wid)
    # タグも体の性別も無い掟は見た目を変えない
    assert rule["appearance_tags"] == ""
    refused = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look", json={}
    )
    assert refused.status_code == 400
    assert refused.json()["detail"]["code"] == "rule_has_no_look"

    # 説明が空なら掟の本文から考える。人物の性別・人数のタグは外す
    llm_outputs.append("1girl, solo, maid outfit, apron")
    made = client.post(
        "/api/hakoniwa/tags/rule-look",
        json={"name": "メイドの日", "text": "全員がメイド服で過ごす"},
    )
    assert made.json()["tags"] == "maid outfit, apron"
    failed = client.post(
        "/api/hakoniwa/tags/rule-look",
        json={"name": "メイドの日", "appearance_text": "メイド服"},
    )
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "tags_failed"
    empty = client.post("/api/hakoniwa/tags/rule-look", json={"name": "メイドの日"})
    assert empty.json()["detail"]["code"] == "look_source_empty"


def test_body_only_rule_is_a_look_rule(client: TestClient, llm_outputs):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(client, wid, body_gender="female")
    assert rule["appearance_tags"] == ""
    llm_outputs.extend(["1girl, brown hair", "1boy, black hair"])

    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/custom-rules/{rule['id']}/look", json={}
    ).json()

    assert body["generated"] == 2
    by_id = {r["id"]: r for r in body["world"]["residents"]}
    assert by_id["ren"]["display_kind"] == "rule"
    assert by_id["ren"]["body_gender"] == "female"
    card = next(c for c in body["world"]["rule_cards"] if c["id"] == rule["id"])
    assert card["look"]["ready"] == 2


def test_combo_look_with_dress_rule(client: TestClient, llm_outputs):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    rule = _custom_rule(client, wid, appearance_tags="cat ears")
    no_combo = client.post(f"/api/hakoniwa/worlds/{wid}/combo-look", json={})
    assert no_combo.json()["detail"]["error"] == "no_combo"

    dressed = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/dress", json={"active": True}
    ).json()["world"]
    assert dressed["combo_look"]["names"] == ["メイドの日"]
    assert dressed["combo_look"]["includes_dress"] is True
    llm_outputs.extend(["1girl, dress, cat ears", "1boy, dress, cat ears"])

    body = client.post(f"/api/hakoniwa/worlds/{wid}/combo-look", json={}).json()

    assert body["generated"] == 2
    assert {r["display_kind"] for r in body["world"]["residents"]} == {"combo"}
    assert body["world"]["combo_look"]["ready"] == 2
    off = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/{rule['id']}", json={"active": False}
    ).json()["world"]
    assert off["combo_look"] is None
    assert {r["display_kind"] for r in off["residents"]} == {"dress"}


def test_world_memo_and_intervention_flow(client: TestClient):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    assert world["intervention"] == {
        "selected": "watch",
        "choices": ["watch", "nudge", "rewrite"],
    }

    memo = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"world_memo": "全員が敬語"}
    ).json()
    assert memo["world_memo"] == "全員が敬語"
    assert memo["player_name"] == ""
    named = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"player_name": " ユウ "}
    ).json()
    assert named["player_name"] == "ユウ"
    assert named["world_memo"] == "全員が敬語"
    too_long = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"player_name": "あ" * 21}
    )
    assert too_long.status_code == 422
    cleared = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"player_name": ""}
    ).json()
    assert cleared["player_name"] == ""
    bad = client.put(
        f"/api/hakoniwa/worlds/{wid}/intervention", json={"choice": "arc_boost"}
    )
    assert bad.json()["detail"]["error"] == "invalid_intervention"
    chosen = client.put(
        f"/api/hakoniwa/worlds/{wid}/intervention", json={"choice": "rewrite"}
    ).json()
    assert chosen["intervention"]["selected"] == "rewrite"

    day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()

    assert day["digest"]["intervention"] == "rewrite"
    assert day["world"]["dissonance"]["value"] == 5
    assert day["world"]["intervention"]["selected"] == "watch"


def test_touch_changes_mood_without_chronicle(client: TestClient):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    before = next(r for r in world["residents"] if r["id"] == "aoi")["mood"]

    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/touch",
        json={"part": "head", "language": "ja"},
    ).json()

    assert body["source"] == "template"
    assert body["text"]
    assert body["mood_delta"] == 2
    aoi = next(r for r in body["world"]["residents"] if r["id"] == "aoi")
    assert aoi["mood"] == before + 2
    assert body["world"]["events"] == []


def test_chat_moves_player_affinity_and_marks_the_reply(
    client: TestClient, monkeypatch
):
    world = _create(client, ["aoi", "ren"])
    path = f"/api/hakoniwa/worlds/{world['id']}/residents/aoi/chat"
    deltas = ['{"delta": 3}', '{"delta": 0}', "not json"]

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        if system.startswith("You judge how a message"):
            return deltas.pop(0)
        return "ありがとう。そう言ってもらえると、すごくうれしいな。"

    monkeypatch.setattr(gen_module, "_generate_text", fake)

    kind = client.post(path, json={"message": "いつもありがとう", "language": "ja"})
    body = kind.json()
    assert body["reply"]["affinity_delta"] == 3
    aoi = next(r for r in body["world"]["residents"] if r["id"] == "aoi")
    assert aoi["player_affinity"] == 3
    ren = next(r for r in body["world"]["residents"] if r["id"] == "ren")
    assert ren["player_affinity"] == 0
    assert body["history"][-1]["affinity_delta"] == 3

    for message in ("今日は晴れだね", "ふーん"):
        later = client.post(path, json={"message": message, "language": "ja"}).json()
        assert later["reply"]["affinity_delta"] is None
        aoi = next(r for r in later["world"]["residents"] if r["id"] == "aoi")
        assert aoi["player_affinity"] == 3
    history = client.get(path).json()["history"]
    assert [
        entry.get("affinity_delta") for entry in history if entry["role"] == "resident"
    ] == [3, None, None]


def test_chat_reply_transform_confirmation_and_clear(client: TestClient, llm_outputs):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    path = f"/api/hakoniwa/worlds/{wid}/residents/aoi/chat"
    llm_outputs.append("「おはよう。今日も配達、がんばるね」")

    talked = client.post(path, json={"message": "おはよう", "language": "ja"}).json()
    assert talked["reply"] == {
        "role": "resident",
        "text": "おはよう。今日も配達、がんばるね",
        "kind": None,
        "source": "llm",
        "web_search": None,
        "affinity_delta": None,
    }
    assert [entry["role"] for entry in talked["history"]] == ["player", "resident"]

    waiting = client.post(
        path, json={"message": "メイド服に着替えて", "allow_image": False}
    ).json()
    assert waiting["alteration"]["needs_confirmation"] is True
    assert waiting["world"] is None
    assert len(waiting["history"]) == 2

    llm_outputs.append("1girl, brown hair, maid outfit")
    done = client.post(
        path,
        json={
            "message": "メイド服に着替えて",
            "confirmed_instruction": "メイド服に着替えて",
            "language": "ja",
        },
    ).json()
    assert done["alteration"]["executed"] is True
    assert done["new_events"][0]["kind"] == "transform"
    assert [entry["role"] for entry in done["history"][-3:]] == [
        "player",
        "system",
        "resident",
    ]
    aoi = next(r for r in done["world"]["residents"] if r["id"] == "aoi")
    assert aoi["display_kind"] == "transform"

    cleared = client.post(path, json={"message": "元に戻して", "language": "ja"}).json()
    assert cleared["reply"]["text"] == "変身を解いて、元の姿に戻しました。"
    aoi = next(r for r in cleared["world"]["residents"] if r["id"] == "aoi")
    assert aoi["transformation"] is None
    history = client.get(path).json()["history"]
    assert len(history) == 7


def test_chat_web_search_is_saved_and_returned_after_reload(
    client, monkeypatch, llm_outputs
):
    from gateway.services import real_world_lookup as real

    world = _create(client, ["aoi", "ren"])
    client.patch(
        f"/api/hakoniwa/worlds/{world['id']}/settings",
        json={"web_search_enabled": True},
    )
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    calls = []

    async def search(query, *, language):
        calls.append((query, language))
        return real.SearchInfo(
            query,
            "宇宙のニュース",
            [
                real.SearchSource(
                    "科学の記事", "https://example.com/news", "新しい望遠鏡"
                )
            ],
        )

    monkeypatch.setattr(real, "tavily_search", search)
    llm_outputs.extend(['{"query":"科学 最新"}', "新しい望遠鏡の写真、見てみたいな。"])
    path = f"/api/hakoniwa/worlds/{world['id']}/residents/aoi/chat"
    response = client.post(
        path, json={"message": "科学のニュースを教えて", "language": "ja"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    metadata = body["reply"]["web_search"]
    assert metadata["status"] == "used"
    assert metadata["sources"] == [
        {"title": "科学の記事", "url": "https://example.com/news"}
    ]
    assert client.get(path).json()["history"][-1]["web_search"] == metadata
    assert calls == [("科学 最新", "ja")]


def test_daily_news_is_assigned_once_and_saved(client, monkeypatch):
    world = _create(client, ["aoi", "ren"])
    client.patch(
        f"/api/hakoniwa/worlds/{world['id']}/settings",
        json={"web_search_enabled": True},
    )
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    assignments = []
    metadata = {
        "query": "科学 最新",
        "retrieved_at": "2026-11-14T03:00:00+00:00",
        "status": "used",
        "sources": [{"title": "科学の記事", "url": "https://example.com/news"}],
    }

    async def event(state, group, language, rng, **options):
        assignments.append(options["use_web_search"])
        result = gen_module.template_event(state, group, language, rng)
        result["source"] = "llm"
        if options["use_web_search"]:
            result["web_search"] = metadata
        return result

    monkeypatch.setattr(service_module, "generate_event", event)
    path = f"/api/hakoniwa/worlds/{world['id']}"
    response = client.post(f"{path}/day", json={"language": "ja"})
    assert response.status_code == 200, response.text
    assert len(assignments) == 3
    assert sum(assignments) == 1
    news = [item for item in response.json()["new_events"] if item["web_search"]]
    assert len(news) == 1
    assert news[0]["web_search"] == metadata
    saved = client.get(path).json()
    assert (
        next(item for item in saved["events"] if item["id"] == news[0]["id"])[
            "web_search"
        ]
        == metadata
    )


def test_web_search_setting_defaults_off_and_is_saved_per_world(client, monkeypatch):
    world = _create(client, ["aoi", "ren"])
    other = _create(client, ["aoi", "ren"])
    path = f"/api/hakoniwa/worlds/{world['id']}"
    assert world["web_search_enabled"] is False
    assert world["web_search_configured"] is False
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    assert client.get(path).json()["web_search_configured"] is True
    enabled = client.patch(f"{path}/settings", json={"web_search_enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["web_search_enabled"] is True
    assert client.get(path).json()["web_search_enabled"] is True
    assert (
        client.get(f"/api/hakoniwa/worlds/{other['id']}").json()["web_search_enabled"]
        is False
    )
    unchanged = client.patch(f"{path}/settings", json={"player_name": "テスト"})
    assert unchanged.json()["web_search_enabled"] is True
    client.patch(f"{path}/settings", json={"web_search_enabled": False})
    assert client.get(path).json()["web_search_enabled"] is False
    monkeypatch.setattr(settings, "tavily_api_key", "")
    no_key = client.patch(f"{path}/settings", json={"web_search_enabled": True}).json()
    assert no_key["web_search_enabled"] is True
    assert no_key["web_search_configured"] is False


def test_random_residents_fall_back_to_templates(client: TestClient) -> None:
    body = client.post(
        "/api/hakoniwa/random-residents",
        json={"count": 3, "exclude_names": ["高瀬 葵"], "language": "ja"},
    ).json()
    assert body["source"] == "template"
    assert len(body["residents"]) == 3
    assert all(item["base_tags"] for item in body["residents"])
    assert (
        client.post("/api/hakoniwa/random-residents", json={"count": 9}).status_code
        == 422
    )


def test_random_residents_from_llm_get_tags(client: TestClient, llm_outputs) -> None:
    llm_outputs.append(
        '{"residents": [{"name": "Kaede Fujiwara", "gender": "male", "age": "30s", '
        '"job": "potter", "personality": "Calm and curious.", "pronoun": "I", '
        '"appearance": "Short black hair and a work apron.", "appearance_tags": ""}]}'
    )
    body = client.post(
        "/api/hakoniwa/random-residents", json={"count": 1, "language": "en"}
    ).json()
    assert body["source"] == "llm"
    resident = body["residents"][0]
    assert resident["name"] == "Kaede Fujiwara"
    # タグが使えなかったので性別の既定のタグ(英語の説明はタグにしない)
    assert resident["base_tags"].startswith("1boy")


def test_create_world_with_random_residents_and_theme(client: TestClient) -> None:
    random_body = client.post(
        "/api/hakoniwa/random-residents", json={"count": 2, "language": "ja"}
    ).json()
    response = client.post(
        "/api/hakoniwa/worlds",
        json={
            "name": "おまかせ荘",
            "preset_ids": ["aoi"],
            "custom_residents": random_body["residents"],
            "experiment_theme": {"preset_id": "dress", "text": ""},
            "language": "ja",
        },
    )
    assert response.status_code == 200, response.text
    world = response.json()
    assert len(world["residents"]) == 3
    custom = [r for r in world["residents"] if r["source"] == "custom"]
    expected = random_body["residents"][0]
    assert custom[0]["name"] == expected["name"]
    assert custom[0]["age"] == expected["age"]
    assert custom[0]["job"] == expected["job"]
    assert custom[0]["pronoun"] == expected["pronoun"]
    assert custom[0]["base_tags"] == expected["base_tags"]
    assert world["experiment_theme"] == {"preset_id": "dress", "text": ""}

    wid = world["id"]
    client.put(f"/api/hakoniwa/worlds/{wid}/rules/dress", json={"active": True})
    day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()
    assert day["digest"]["theme"]["preset_id"] == "dress"
    assert day["digest"]["theme"]["dress_days"] == 1

    changed = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings",
        json={"experiment_theme": {"preset_id": None, "text": "猫好きの世界"}},
    ).json()
    assert changed["experiment_theme"] == {"preset_id": None, "text": "猫好きの世界"}
    cleared = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings",
        json={"experiment_theme": {"preset_id": None, "text": ""}},
    ).json()
    assert cleared["experiment_theme"] is None
    kept = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings", json={"world_memo": "雪の日"}
    ).json()
    assert kept["experiment_theme"] is None
    bad = client.patch(
        f"/api/hakoniwa/worlds/{wid}/settings",
        json={"experiment_theme": {"preset_id": "unknown"}},
    )
    assert bad.status_code == 400


def test_free_text_theme_goes_to_one_event_a_day(client: TestClient, monkeypatch):
    seen: list = []
    original = service_module.generate_event

    async def spy(*args, **kwargs):
        seen.append(kwargs.get("include_theme"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(service_module, "generate_event", spy)
    world = client.post(
        "/api/hakoniwa/worlds",
        json={
            "name": "猫の世界",
            "preset_ids": PRESETS,
            "experiment_theme": {"text": "住民みんなが猫好きになっていく"},
            "language": "ja",
        },
    ).json()
    client.post(f"/api/hakoniwa/worlds/{world['id']}/day", json={})
    assert len(seen) == 3
    assert seen.count(True) == 1

    seen.clear()
    plain = _create(client)
    client.post(f"/api/hakoniwa/worlds/{plain['id']}/day", json={})
    assert seen == [False, False, False]


def test_hakoniwa_achievements_unlock_once_across_worlds(client: TestClient) -> None:
    from gateway.services.achievements import get_user_achievements

    world = _create(client, ["aoi", "ren"])
    assert world["new_achievements"] == []
    wid = world["id"]

    dressed = client.put(
        f"/api/hakoniwa/worlds/{wid}/rules/dress", json={"active": True}
    ).json()
    unlocked = {item["achievement_id"] for item in dressed["world"]["new_achievements"]}
    assert unlocked == {"hakoniwa_dress_all"}
    assert all(
        item["category"] == "hakoniwa" for item in dressed["world"]["new_achievements"]
    )

    day = client.post(f"/api/hakoniwa/worlds/{wid}/day", json={}).json()
    assert "hakoniwa_first_day" in {
        item["achievement_id"] for item in day["world"]["new_achievements"]
    }

    # 開き直しても、もう達成した分は出ない
    reopened = client.get(f"/api/hakoniwa/worlds/{wid}").json()
    assert reopened["new_achievements"] == []

    second = _create(client, ["aoi", "ren"])
    assert [item["achievement_id"] for item in second["new_achievements"]] == [
        "hakoniwa_new_world"
    ]
    saved = {
        status.achievement_id for status in get_user_achievements() if status.unlocked
    }
    assert {"hakoniwa_dress_all", "hakoniwa_first_day", "hakoniwa_new_world"} <= saved


def _edit_aoi(client: TestClient, wid: str, **fields):
    body = {
        "name": "高瀬 葵",
        "personality": "明るく世話好き",
        "gender": "female",
        "base_tags": "1girl, brown hair, bob cut",
        **fields,
    }
    return client.patch(f"/api/hakoniwa/worlds/{wid}/residents/aoi", json=body)


def _aoi(body: dict) -> dict:
    return next(r for r in body["world"]["residents"] if r["id"] == "aoi")


def test_resident_tags_are_saved_as_written(
    client: TestClient, llm_outputs: list
) -> None:
    wid = _create(client, ["aoi", "ren"])["id"]

    edited = _aoi(
        _edit_aoi(client, wid, base_tags="solo, short silver hair,\nmaid outfit").json()
    )
    # 性別トークンを補い、改行もカンマとして扱う
    assert edited["base_tags"] == "1girl, solo, short silver hair, maid outfit"

    # 説明を変えても、タグは送られたものを使う(保存では LLM を呼ばない)
    llm_outputs.append("1girl, blonde long hair")
    kept = _aoi(
        _edit_aoi(
            client,
            wid,
            appearance_text="金髪のロング",
            base_tags="1girl, solo, short silver hair, maid outfit",
        ).json()
    )
    assert kept["base_tags"] == "1girl, solo, short silver hair, maid outfit"
    assert kept["appearance_text"] == "金髪のロング"
    assert llm_outputs == ["1girl, blonde long hair"]

    missing = _edit_aoi(client, wid, base_tags=" ")
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "tags_required"


def test_hand_written_tags_are_checked(client: TestClient) -> None:
    wid = _create(client, ["aoi", "ren"])["id"]

    japanese = _edit_aoi(client, wid, base_tags="銀髪, メイド服")
    assert japanese.status_code == 400
    assert japanese.json()["detail"]["code"] == "invalid_tags"
    mismatch = _edit_aoi(client, wid, dress_tags="1boy, suit")
    assert mismatch.json()["detail"]["code"] == "tags_gender_mismatch"
    # 個数は制限しない(プレイと同じ)。長さはつないだあと 2000 文字まで
    many = _edit_aoi(client, wid, base_tags=", ".join(f"tag{i}" for i in range(60)))
    assert many.status_code == 200
    # 改行はカンマ区切りに直すので、入力が 2000 文字以内でもつなぐと超えることがある
    too_long = _edit_aoi(
        client, wid, base_tags="\n".join(f"tag{i:04d}" for i in range(250))
    )
    assert too_long.json()["detail"]["code"] == "too_many_tags"


def test_custom_rule_look_tags_are_saved_as_written(client: TestClient) -> None:
    wid = _create(client, ["aoi", "ren"])["id"]
    path = f"/api/hakoniwa/worlds/{wid}/custom-rules"

    added = client.post(
        path,
        json={
            "name": "猫の日",
            "text": "猫耳を付ける",
            "appearance_tags": "1girl, cat ears",
        },
    ).json()
    rule = next(card for card in added["rule_cards"] if card["custom"])
    # 人物の性別・人数のタグは外す
    assert rule["appearance_tags"] == "cat ears"

    # 説明を変えても、タグは送られたものを使う
    kept = client.patch(
        f"{path}/{rule['id']}",
        json={
            "name": "猫の日",
            "text": "猫耳を付ける",
            "appearance_text": "bunny ears",
            "appearance_tags": "cat ears",
        },
    ).json()
    kept_rule = next(card for card in kept["rule_cards"] if card["id"] == rule["id"])
    assert kept_rule["appearance_tags"] == "cat ears"

    # タグを空にすると、見た目を変えない掟になる
    cleared = client.patch(
        f"{path}/{rule['id']}",
        json={"name": "猫の日", "text": "猫耳を付ける", "appearance_tags": ""},
    ).json()
    cleared_rule = next(c for c in cleared["rule_cards"] if c["id"] == rule["id"])
    assert cleared_rule["appearance_tags"] == ""


def test_address_style_is_saved_on_edit_and_add(client: TestClient) -> None:
    wid = _create(client, ["aoi", "ren"])["id"]

    edited = _aoi(_edit_aoi(client, wid, address_style="family_san").json())
    assert edited["address_style"] == "family_san"
    assert edited["addresses"] == {"ren": "苑田さん"}
    # 呼び方を送らない編集では今のまま
    assert _aoi(_edit_aoi(client, wid).json())["address_style"] == "family_san"

    added = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents",
        json={
            "name": "佐倉 美咲",
            "personality": "穏やか",
            "gender": "female",
            "address_style": "given",
            "base_tags": "1girl, black hair",
        },
    ).json()
    misaki = next(
        r for r in added["world"]["residents"] if r["id"] == added["resident_id"]
    )
    assert misaki["address_style"] == "given"
    assert misaki["addresses"]["aoi"] == "葵"


# --- 指示した出来事 ---

DIRECTED_INSTRUCTION = "二人で一緒にお風呂に入る"


def _directed_event_json(names: list[str]) -> str:
    return json.dumps(
        {
            "title": "湯けむり",
            "narration": "湯気の立つ浴室で、二人は肩を並べて湯船に浸かった。",
            "lines": [{"speaker": name, "text": "……あったかいね"} for name in names],
            "participants": names,
            "mood_delta": {name: 6 for name in names},
            "affinity_delta": 5,
        },
        ensure_ascii=False,
    )


def test_directed_event_is_recorded_and_moves_partners(
    client: TestClient, llm_outputs: list
):
    world = _create(client, ["aoi", "ren", "ritsu"])
    wid = world["id"]
    llm_outputs.append(_directed_event_json(["高瀬 葵", "苑田 蓮"]))

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={
            "instruction": DIRECTED_INSTRUCTION,
            "scope": "selected",
            "partner_ids": ["ren"],
            "language": "ja",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    event = body["new_events"][0]
    assert event["kind"] == "directed"
    assert event["source"] == "player"
    assert event["instruction"] == DIRECTED_INSTRUCTION
    assert event["participants"] == ["aoi", "ren"]
    assert event["area"] == "living"
    assert body["world"]["events"][-1]["id"] == event["id"]
    ren = next(r for r in body["world"]["residents"] if r["id"] == "ren")
    assert ren["current_area"] == "living"
    assert body["world"]["dissonance"]["value"] == 10


def test_directed_event_scene_image_works(
    client: TestClient, llm_outputs: list, monkeypatch
):
    async def fake_scene(request, *, image_model, nsfw_mode):
        return _png()

    monkeypatch.setattr(service_module, "generate_scene_bytes", fake_scene)
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    llm_outputs.append(_directed_event_json(["高瀬 葵"]))
    event = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={"instruction": DIRECTED_INSTRUCTION, "scope": "solo"},
    ).json()["new_events"][0]

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/events/{event['id']}/scene-image", json={}
    )

    assert response.status_code == 200, response.text
    updated = next(
        e for e in response.json()["world"]["events"] if e["id"] == event["id"]
    )
    assert updated["scene_image_url"]


def test_directed_event_failure_leaves_the_world_unchanged(client: TestClient):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={"instruction": DIRECTED_INSTRUCTION, "scope": "solo"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "event_generation_failed"
    after = client.get(f"/api/hakoniwa/worlds/{wid}").json()
    assert after["events"] == []
    assert after["dissonance"]["value"] == 0


def test_directed_event_request_validation(client: TestClient):
    world = _create(client, ["aoi", "ren"])
    path = f"/api/hakoniwa/worlds/{world['id']}/residents/ren/event"

    empty_room = client.post(
        path, json={"instruction": DIRECTED_INSTRUCTION, "scope": "room"}
    )
    too_many = client.post(
        path,
        json={
            "instruction": DIRECTED_INSTRUCTION,
            "scope": "selected",
            "partner_ids": ["aoi", "x", "y"],
        },
    )
    blank = client.post(path, json={"instruction": "   ", "scope": "solo"})

    assert empty_room.status_code == 400
    assert empty_room.json()["detail"]["error"] == "event_room_empty"
    assert too_many.status_code == 422
    assert blank.status_code == 400
    assert blank.json()["detail"]["error"] == "invalid_event_text"


def test_directed_event_at_an_outside_place(client: TestClient, llm_outputs: list):
    world = _create(client, ["aoi", "ren"])
    wid = world["id"]
    assert {
        "id": "shopping_street",
        "name": "商店街",
        "background_url": "/hakoniwa-assets/location_shopping_street.png",
    } in world["locations"]
    llm_outputs.append(_directed_event_json(["高瀬 葵"]))

    body = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={
            "instruction": "商店街へ買い物に出かける",
            "scope": "solo",
            "location": "shopping_street",
        },
    ).json()

    event = body["new_events"][0]
    assert event["location"] == "shopping_street"
    assert event["area"] == "living"
    bad = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={"instruction": "月へ行く", "scope": "solo", "location": "moon"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["error"] == "invalid_location"


# --- 続きを指示 ---


def _directed(client: TestClient, wid: str, llm_outputs: list, **extra) -> dict:
    llm_outputs.append(_directed_event_json(["高瀬 葵", "苑田 蓮"]))
    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={
            "instruction": DIRECTED_INSTRUCTION,
            "scope": "selected",
            "partner_ids": ["ren"],
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["new_events"][0]


def test_continue_event_is_recorded_as_a_follow_up(
    client: TestClient, llm_outputs: list
):
    wid = _create(client, ["aoi", "ren", "ritsu"])["id"]
    first = _directed(client, wid, llm_outputs, location="hotel")
    llm_outputs.append(_directed_event_json(["高瀬 葵", "苑田 蓮"]))

    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/events/{first['id']}/continue",
        json={"instruction": "そのまま寄り添う", "language": "ja"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    event = body["new_events"][0]
    assert event["id"] != first["id"]
    assert event["kind"] == "directed"
    assert event["source"] == "player"
    assert event["instruction"] == "そのまま寄り添う"
    assert event["continues"] == first["id"]
    assert event["participants"] == ["aoi", "ren"]
    # 生成が場所を示さなければ、前の場面の場所で続く
    assert event["location"] == "hotel"
    assert [e["id"] for e in body["world"]["events"][-2:]] == [first["id"], event["id"]]
    # 続きは同じ介入の延長なので、違和感は小さく溜まる(10 + 3)
    assert body["world"]["dissonance"]["value"] == 13


def test_continue_event_failure_leaves_the_world_unchanged(
    client: TestClient, llm_outputs: list
):
    wid = _create(client, ["aoi", "ren"])["id"]
    first = _directed(client, wid, llm_outputs)

    failed = client.post(
        f"/api/hakoniwa/worlds/{wid}/events/{first['id']}/continue",
        json={"instruction": "そのまま寄り添う"},
    )
    missing = client.post(
        f"/api/hakoniwa/worlds/{wid}/events/nope/continue",
        json={"instruction": "そのまま寄り添う"},
    )
    blank = client.post(
        f"/api/hakoniwa/worlds/{wid}/events/{first['id']}/continue",
        json={"instruction": "   "},
    )

    assert failed.status_code == 502
    assert failed.json()["detail"]["error"] == "event_generation_failed"
    assert missing.status_code == 404
    assert blank.status_code == 400
    assert blank.json()["detail"]["error"] == "invalid_event_text"
    after = client.get(f"/api/hakoniwa/worlds/{wid}").json()
    assert [e["id"] for e in after["events"]] == [first["id"]]
    assert after["dissonance"]["value"] == 10


# --- 出来事で立ち絵も変える ---

SWAP_INSTRUCTION = "葵と珠子が服を交換する"
AOI_AFTER = "1girl, brown hair, ponytail, white blouse, pencil skirt"
TAMAKO_AFTER = "1girl, silver hair, wavy hair, denim jacket, leggings"


def _resident(world: dict, resident_id: str) -> dict:
    return next(r for r in world["residents"] if r["id"] == resident_id)


def _swap_event(client: TestClient, wid: str, llm_outputs: list) -> dict:
    llm_outputs.append(_directed_event_json(["高瀬 葵", "大島 珠子"]))
    response = client.post(
        f"/api/hakoniwa/worlds/{wid}/residents/aoi/event",
        json={
            "instruction": SWAP_INSTRUCTION,
            "scope": "selected",
            "partner_ids": ["tamako"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["new_events"][0]


def test_event_looks_are_planned_once_then_drawn_one_by_one(
    client: TestClient, llm_outputs: list, monkeypatch
):
    drawn: list[str] = []

    async def fake_avatar(tags, *, image_model, nsfw_mode):
        drawn.append(tags)
        return _png()

    monkeypatch.setattr(service_module, "generate_avatar_bytes", fake_avatar)
    wid = _create(client, ["aoi", "tamako", "ren"])["id"]
    event = _swap_event(client, wid, llm_outputs)
    llm_outputs.append(
        json.dumps(
            {
                "changes": [
                    {
                        "name": "高瀬 葵",
                        "tags": AOI_AFTER,
                        "description": "珠子のブラウスとスカートを着ている",
                    },
                    {
                        "name": "大島 珠子",
                        "tags": TAMAKO_AFTER,
                        "description": "葵のデニムジャケットを着ている",
                    },
                    # 出来事に出ていない住民は計画に入れない
                    {"name": "苑田 蓮", "tags": "1boy, suit", "description": "x"},
                ]
            },
            ensure_ascii=False,
        )
    )
    base = f"/api/hakoniwa/worlds/{wid}/events/{event['id']}/looks"

    plan = client.post(f"{base}/plan", json={"language": "ja"})

    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["changes"] == [
        {"resident_id": "aoi", "description": "珠子のブラウスとスカートを着ている"},
        {"resident_id": "tamako", "description": "葵のデニムジャケットを着ている"},
    ]
    # 計画では画像を作らず、姿も変えない
    assert drawn == []
    assert _resident(body["world"], "aoi")["transformation"] is None

    first = client.post(f"{base}/aoi", json={})
    assert first.status_code == 200, first.text
    aoi = _resident(first.json()["world"], "aoi")
    assert aoi["transformation"]["tags"] == AOI_AFTER
    assert aoi["transformation"]["description"] == "珠子のブラウスとスカートを着ている"
    assert aoi["display_kind"] == "transform"
    assert aoi["adaptation"]["kind"] == "transform"
    assert len(aoi["transformation_history"]) == 1
    assert _resident(first.json()["world"], "tamako")["transformation"] is None

    second = client.post(f"{base}/tamako", json={})
    assert second.status_code == 200, second.text
    # 2人目も、1人目を変える前に決めた計画のタグで描く
    assert drawn == [AOI_AFTER, TAMAKO_AFTER]
    world = second.json()["world"]
    assert _resident(world, "tamako")["transformation"]["tags"] == TAMAKO_AFTER
    # 反応の出来事は足さず、違和感も出来事ぶんのまま
    assert [e["id"] for e in world["events"]] == [event["id"]]
    assert world["dissonance"]["value"] == 10

    outsider = client.post(f"{base}/ren", json={})
    assert outsider.status_code == 400
    assert outsider.json()["detail"]["error"] == "event_look_not_planned"


def test_event_look_plan_can_be_empty_or_fail(client: TestClient, llm_outputs: list):
    wid = _create(client, ["aoi", "tamako"])["id"]
    event = _swap_event(client, wid, llm_outputs)
    base = f"/api/hakoniwa/worlds/{wid}/events/{event['id']}/looks"

    failed = client.post(f"{base}/plan", json={})
    assert failed.status_code == 502
    assert failed.json()["detail"]["error"] == "event_look_failed"
    unplanned = client.post(f"{base}/aoi", json={})
    assert unplanned.json()["detail"]["error"] == "event_look_not_planned"

    llm_outputs.append('{"changes": []}')
    empty = client.post(f"{base}/plan", json={})
    assert empty.status_code == 200, empty.text
    assert empty.json()["changes"] == []

    missing = client.post(f"/api/hakoniwa/worlds/{wid}/events/nope/looks/plan", json={})
    assert missing.status_code == 404
