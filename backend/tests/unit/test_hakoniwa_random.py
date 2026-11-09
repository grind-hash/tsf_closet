"""AI箱庭: おまかせの住民(ランダムな住民構成)と実験テーマ。"""

from __future__ import annotations

import asyncio
import json
import random

import pytest

from gateway.services import hakoniwa_generation as gen_module
from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_play as play
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_generation import (
    clean_profile,
    generate_random_resident_profiles,
)
from gateway.services.hakoniwa_prompts import event_user_prompt, theme_section
from gateway.services.hakoniwa_random import name_key, template_residents


@pytest.mark.parametrize("language", ["ja", "en"])
def test_template_residents_are_complete_adults_with_unique_names(language):
    residents = template_residents(7, language, random.Random(3), ["佐倉 美咲"])
    assert len(residents) == 7
    keys = [name_key(item["name"]) for item in residents]
    assert len(set(keys)) == 7
    assert name_key("佐倉 美咲") not in keys
    for item in residents:
        assert item["gender"] in ("female", "male")
        assert item["personality"] and item["job"] and item["appearance_text"]
        token = "1girl" if item["gender"] == "female" else "1boy"
        assert item["base_tags"].startswith(f"{token}, solo, ")
        assert "years old" in item["base_tags"]
        if language == "en":
            assert item["pronoun"] == "I"
            assert all(ord(char) < 128 for char in item["appearance_text"])
        else:
            assert item["pronoun"]


def test_template_residents_mix_genders():
    for seed in range(20):
        genders = {
            item["gender"] for item in template_residents(2, "ja", random.Random(seed))
        }
        assert genders == {"female", "male"}


def test_template_residents_depend_on_the_seed_and_validate_count():
    first = template_residents(3, "ja", random.Random(1))
    again = template_residents(3, "ja", random.Random(1))
    other = template_residents(3, "ja", random.Random(2))
    assert first == again
    assert first != other
    with pytest.raises(HakoniwaError):
        template_residents(0, "ja", random.Random(1))
    with pytest.raises(HakoniwaError):
        template_residents(8, "ja", random.Random(1))


def test_clean_profile_trims_and_fixes_text_and_tags():
    profile = clean_profile(
        {
            "name": "  水野   澪 ",
            "gender": "female",
            "personality": "违和感に敏感で、几帳面。" * 40,
            "appearance": "黒髪のボブ。",
            "appearance_tags": "solo, bob cut, black hair",
        },
        "ja",
    )
    assert profile["name"] == "水野 澪"
    assert profile["personality"].startswith("違和感")
    assert len(profile["personality"]) == 300
    assert profile["pronoun"] == "私"
    assert profile["appearance_text"] == "黒髪のボブ。"
    assert profile["base_tags"].startswith("1girl, ")
    assert (
        clean_profile({"name": "x", "appearance_tags": "黒髪"}, "en")["base_tags"] == ""
    )


def _llm_json(names, gender="female"):
    return json.dumps(
        {
            "residents": [
                {
                    "name": name,
                    "gender": gender,
                    "age": "20代後半",
                    "job": "花屋の店主",
                    "personality": "穏やかで聞き上手。",
                    "pronoun": "私",
                    "appearance": "栗色のロングヘア。",
                    "appearance_tags": "1girl, solo, long hair, chestnut hair",
                }
                for name in names
            ]
        },
        ensure_ascii=False,
    )


def test_llm_profiles_are_validated_for_count_and_names(monkeypatch):
    outputs = [
        _llm_json(["藤原 楓", "藤原 楓"]),  # 名前の重複 -> 修復を依頼
        _llm_json(["藤原 楓", "森 紬"]),
    ]

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        return outputs.pop(0)

    monkeypatch.setattr(gen_module, "_generate_text", fake)
    profiles = asyncio.run(
        generate_random_resident_profiles(
            2, "ja", exclude_names=["高瀬 葵"], novelai_model=None
        )
    )
    assert [item["name"] for item in profiles] == ["藤原 楓", "森 紬"]
    assert profiles[0]["base_tags"] == "1girl, solo, long hair, chestnut hair"


def test_llm_profiles_return_none_when_names_keep_clashing(monkeypatch):
    async def fake(system, user, *, novelai_model, max_tokens=1400):
        return _llm_json(["高瀬 葵"])

    monkeypatch.setattr(gen_module, "_generate_text", fake)
    profiles = asyncio.run(
        generate_random_resident_profiles(
            1, "ja", exclude_names=["高瀬葵"], novelai_model=None
        )
    )
    assert profiles is None


# --- 実験テーマ ---


def _world(ids=("aoi", "ren")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in ids])


def test_validate_theme_prefers_text_and_rejects_unknown_presets():
    assert play.validate_theme("dress", "") == {"preset_id": "dress", "text": ""}
    assert play.validate_theme("dress", " 猫好きの世界 ") == {
        "preset_id": None,
        "text": "猫好きの世界",
    }
    assert play.validate_theme(None, "") is None
    with pytest.raises(HakoniwaError):
        play.validate_theme("unknown", "")
    with pytest.raises(HakoniwaError):
        play.validate_theme(None, "あ" * 101)


def test_theme_survives_normalization_and_counts_rule_days():
    state = {**_world(), "experiment_theme": {"preset_id": "dress", "text": ""}}
    state = logic.normalize_state(state)
    assert state["experiment_theme"] == {"preset_id": "dress", "text": ""}
    state = logic.set_rule(state, "dress", True, random.Random(0))
    state = play.record_theme_day(play.record_theme_day(state))
    progress = play.theme_progress(state)
    assert progress["dress_days"] == 2
    assert progress["dress_target"] == 7
    assert logic.normalize_state(state)["theme_stats"]["dress_active_days"] == 2


def test_theme_progress_for_swap_dissonance_and_transform():
    state = logic.set_rule(_world(), "swap", True, random.Random(0))
    state = play.record_theme_day(
        {**state, "experiment_theme": {"preset_id": "swap", "text": ""}}
    )
    assert play.theme_progress(state)["swap_days"] == 1
    assert play.theme_progress(state)["swapping"] is True

    state = {**_world(), "experiment_theme": {"preset_id": "dissonance", "text": ""}}
    progress = play.theme_progress(state)
    assert progress["remaining"] == 80 and progress["dissonance_stage"] == "stillness"

    state = {**_world(), "experiment_theme": {"preset_id": "transform", "text": ""}}
    assert play.theme_progress(state)["transform_count"] == 0
    assert play.theme_progress({**_world(), "experiment_theme": None}) is None


def test_only_free_text_theme_reaches_the_prompt():
    preset = {**_world(), "experiment_theme": {"preset_id": "dress", "text": ""}}
    assert theme_section(preset) == ""
    free = {**_world(), "experiment_theme": {"preset_id": None, "text": "猫好きの世界"}}
    assert "猫好きの世界" in theme_section(free)
    group = tuple(free["residents"])
    prompt = event_user_prompt(free, group, "ja", nsfw=False)
    assert "experiment theme" in prompt and "猫好きの世界" in prompt


def test_japanese_profiles_with_simplified_chinese_are_rewritten(monkeypatch):
    chinese = json.loads(_llm_json(["桐谷 健吾"], gender="male"))
    chinese["residents"][0]["job"] = "系统工程师"
    outputs = [
        json.dumps(chinese, ensure_ascii=False),
        _llm_json(["桐谷 健吾"], gender="male"),
    ]

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        return outputs.pop(0)

    monkeypatch.setattr(gen_module, "_generate_text", fake)
    profiles = asyncio.run(
        generate_random_resident_profiles(1, "ja", exclude_names=[], novelai_model=None)
    )
    assert profiles[0]["job"] == "花屋の店主"
    assert outputs == []


def test_free_text_theme_can_be_left_out_of_an_event():
    free = {**_world(), "experiment_theme": {"preset_id": None, "text": "猫好きの世界"}}
    group = tuple(free["residents"])
    prompt = event_user_prompt(free, group, "ja", nsfw=False, include_theme=False)
    assert "猫好きの世界" not in prompt
