"""AI箱庭: プレイヤーが手で直した画像のタグ(説明から作るタグより優先し、上書きしない)。"""

from __future__ import annotations

import pytest

from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_generation import (
    clean_manual_look_tags,
    clean_manual_tags,
)


@pytest.mark.parametrize(
    ("edited", "regenerate", "manual", "changed", "expected"),
    [
        (None, False, False, False, "keep"),
        (None, False, False, True, "derive"),
        # 手で直したタグは、説明を変えても作り直さない
        (None, False, True, True, "keep"),
        (None, True, True, False, "derive"),
        ("cat ears", False, False, False, "manual"),
        # タグを空にして保存したら、説明から作るタグに戻す
        ("  ", False, True, False, "derive"),
        ("cat ears", True, False, False, "derive"),
    ],
)
def test_tag_action(edited, regenerate, manual, changed, expected):
    assert (
        logic.tag_action(
            edited=edited, regenerate=regenerate, manual=manual, source_changed=changed
        )
        == expected
    )


def test_manual_resident_tags_get_a_gender_token():
    assert clean_manual_tags("solo, maid outfit", "male") == "1boy, solo, maid outfit"
    assert clean_manual_tags("1girl, maid outfit", "female") == "1girl, maid outfit"
    with pytest.raises(HakoniwaError) as error:
        clean_manual_tags("1girl, maid outfit", "male")
    assert error.value.code == "tags_gender_mismatch"


def test_manual_look_tags_drop_person_tags():
    assert clean_manual_look_tags("1girl, solo, cat ears") == "cat ears"
    with pytest.raises(HakoniwaError) as error:
        clean_manual_look_tags("1girl, solo")
    assert error.value.code == "invalid_tags"


def test_preset_redraw_keeps_hand_edited_tags():
    entry = logic.preset_resident("ren")
    entry.update(
        preset_revision=2, base_tags="1boy, custom look", base_tags_manual=True
    )
    upgraded = logic.upgrade_preset_resident(entry)
    assert upgraded["base_tags"] == "1boy, custom look"
    assert upgraded["preset_revision"] == 3


def test_old_states_load_with_tags_not_hand_edited():
    state = logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("ren")]
    )
    state["custom_rules"] = [{"id": "r1", "name": "猫", "text": "猫耳"}]
    for resident in state["residents"]:
        resident.pop("base_tags_manual", None)
    normalized = logic.normalize_state(state)
    assert normalized["residents"][0]["base_tags_manual"] is False
    assert normalized["custom_rules"][0]["appearance_tags_manual"] is False
