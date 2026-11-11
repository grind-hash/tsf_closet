"""AI箱庭の場面の絵の服装: 場面だけ着替えさせる(住民の姿は変えない)。"""

from __future__ import annotations

import json

import pytest

from gateway.services import hakoniwa_generation as gen
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_scene import (
    dress_for_scene,
    scene_request,
    strip_clothing_tags,
)

AOI_TAGS = logic.preset_resident("aoi")["base_tags"]


def _state():
    return logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("ren")]
    )


def test_strip_clothing_keeps_hair_and_body():
    stripped = strip_clothing_tags(AOI_TAGS)

    assert "long brown hair" in stripped
    assert "brown eyes" in stripped
    for clothing in ("delivery uniform", "cap", "casual jacket"):
        assert clothing not in stripped


def test_strip_clothing_catches_compound_words():
    stripped = strip_clothing_tags(
        "1girl, long hair, glasses, sundress, swimsuit, thighhighs, holding book"
    )

    assert stripped == "1girl, long hair, glasses"


def test_dress_for_scene_swaps_the_outfit_only():
    towel = dress_for_scene(AOI_TAGS, "towel", "female", nsfw=True)

    assert towel.endswith("naked towel, bath towel")
    assert "casual jacket" not in towel
    assert "long brown hair" in towel


def test_dress_for_scene_uses_male_tags_for_a_male_body():
    tags = dress_for_scene("1boy, short hair, apron", "swimsuit", "male", nsfw=True)

    assert tags == "1boy, short hair, swim trunks, topless male"


def test_nude_becomes_a_towel_when_nsfw_is_off():
    assert "nude" not in dress_for_scene(AOI_TAGS, "nude", "female", nsfw=False)
    assert "naked towel" in dress_for_scene(AOI_TAGS, "nude", "female", nsfw=False)
    assert "completely nude" in dress_for_scene(AOI_TAGS, "nude", "female", nsfw=True)


@pytest.mark.parametrize("attire", [None, "as_is", "space suit"])
def test_unknown_or_as_is_keeps_the_look(attire):
    assert dress_for_scene(AOI_TAGS, attire, "female", nsfw=True) == AOI_TAGS


def test_scene_request_dresses_each_character():
    state = _state()
    event = {"participants": ["aoi", "ren"], "area": "living", "location": "bathroom"}

    request = scene_request(
        state, event, "bathing", {"aoi": "nude", "ren": "towel"}, nsfw=True
    )

    aoi, ren = (frame["prompt"] for frame in request["characters"])
    assert "completely nude" in aoi
    assert "casual jacket" not in aoi
    assert "towel around waist" in ren
    assert "apron" not in ren
    # 住民の姿そのものは変えない
    assert "casual jacket" in logic.find_resident(state, "aoi")["base_tags"]


# --- 場面のタグと服装の生成 ---


def _stub(monkeypatch, outputs):
    calls: list[tuple[str, str]] = []
    queue = list(outputs)

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        calls.append((system, user))
        return queue.pop(0) if queue else ""

    monkeypatch.setattr(gen, "_generate_text", fake)
    return calls


@pytest.mark.asyncio
async def test_scene_tags_map_attire_by_name(monkeypatch):
    _stub(
        monkeypatch,
        [
            json.dumps(
                {
                    "tags": "bathing, steam, smile",
                    "attire": {
                        "高瀬葵": "nude",
                        "苑田 蓮": "space suit",
                        "誰か": "towel",
                    },
                },
                ensure_ascii=False,
            )
        ],
    )
    event = {"title": "湯けむり", "narration": "二人は湯船に浸かった。", "lines": []}
    event["participants"] = ["aoi", "ren"]
    names = {"aoi": "高瀬 葵", "ren": "苑田 蓮"}

    scene = await gen.convert_scene_to_tags(
        event, names, "bathroom", novelai_model=None, nsfw=True
    )

    assert scene is not None
    assert scene.tags == "bathing, steam, smile"
    assert scene.attire == {"aoi": "nude"}


@pytest.mark.asyncio
async def test_scene_tags_offer_nude_only_with_nsfw(monkeypatch):
    calls = _stub(monkeypatch, ['{"tags": "smile", "attire": {}}'] * 2)
    event = {"title": "t", "narration": "n", "lines": [], "participants": ["aoi"]}
    names = {"aoi": "高瀬 葵"}

    await gen.convert_scene_to_tags(event, names, "x", novelai_model=None, nsfw=False)
    await gen.convert_scene_to_tags(event, names, "x", novelai_model=None, nsfw=True)

    assert "nude" not in calls[0][0]
    assert "nude" in calls[1][0]
    assert '"高瀬 葵": "one of the attire ids"' in calls[1][0]


def test_covered_attire_adds_a_nude_negative():
    state = _state()
    event = {"participants": ["aoi", "ren"], "area": "living", "location": "beach"}

    request = scene_request(
        state, event, "splashing", {"aoi": "swimsuit", "ren": "nude"}, nsfw=True
    )

    aoi, ren = request["characters"]
    assert "nipples" in aoi["negative_prompt"]
    # 裸に選ばれた人物には付けない
    assert "completely nude" not in ren.get("negative_prompt", "")
