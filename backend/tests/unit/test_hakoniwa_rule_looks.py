"""AI箱庭の掟の姿と複合の姿: 表示の優先順位・生成状況・プロンプトの姿の説明。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_generation import clean_look_tags
from gateway.services.hakoniwa_prompts import (
    REALITY_STANCE,
    active_rules_text,
    appearance_focus_text,
    appearance_note,
    current_appearance_summary,
    look_hint,
    male_confusion_guidance,
    memo_section,
    residents_text,
    risque_focus_text,
    rule_look_instruction,
    transform_reaction_prompts,
)
from gateway.services.hakoniwa_scene import look_tags


def _world():
    return logic.new_world_state([logic.preset_resident(pid) for pid in ("aoi", "ren")])


def _with_rule(state, name="メイドの日", tags="maid outfit, apron", body_gender=None):
    state = logic.add_custom_rule(
        state, name, "全員がメイド服で過ごす", "", tags, body_gender=body_gender
    )
    rule_id = state["custom_rules"][-1]["id"]
    return logic.set_rule(state, rule_id, True, random.Random(0)), rule_id


def _look(
    state,
    resident_id,
    kind,
    key,
    tags="maid outfit",
    source="maid outfit",
    body=None,
):
    return logic.set_look_image(
        state,
        resident_id,
        kind=kind,
        key=key,
        entry={
            "image": f"{kind}_{resident_id}.png",
            "tags": tags,
            "source_tags": source,
            "source_body": body,
        },
    )


def test_clean_look_tags_drops_person_tags():
    assert clean_look_tags("1girl, maid outfit, solo, cat ears, 2boys") == (
        "maid outfit, cat ears"
    )
    assert clean_look_tags("メイド服") is None


def test_display_priority_transform_combo_rule_dress_base():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    aoi = logic.find_resident(state, "aoi")
    assert logic.own_look(state, aoi)["kind"] == "base"
    assert logic.appearance_kind(state, aoi) == "rule"

    state = _look(state, "aoi", "rule", rule_id)
    assert logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "rule"

    state = logic.set_rule(state, "dress", True, random.Random(0))
    combo = logic.active_combo(state)
    assert combo["includes_dress"] is True
    # 複合の姿がまだ無ければ、掟の姿のまま
    assert logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "rule"
    state = _look(state, "aoi", "combo", combo["digest"], source="maid outfit")
    look = logic.own_look(state, logic.find_resident(state, "aoi"))
    assert (look["kind"], look["tags"]) == ("combo", "maid outfit")

    state = logic.set_transformation(
        state,
        "aoi",
        {
            "description": "魔法少女",
            "tags": "1girl, magical girl",
            "image": "tf.png",
            "day": 1,
        },
    )
    assert (
        logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "transform"
    )
    # 掟を外すと、ドレス姿へ戻る
    plain = logic.set_rule(
        logic.clear_transformation(state, "aoi"), rule_id, False, random.Random(0)
    )
    assert logic.own_look(plain, logic.find_resident(plain, "aoi"))["kind"] == "dress"


def test_later_rule_wins_and_swap_shows_partner_look():
    state, first = _with_rule(_world(), "メイドの日", "maid outfit")
    state, second = _with_rule(state, "猫の日", "cat ears")
    state = _look(state, "ren", "rule", first, tags="1boy, maid outfit")
    state = _look(state, "ren", "rule", second, tags="1boy, cat ears")

    assert logic.own_look(state, logic.find_resident(state, "ren"))["rule_id"] == second
    state = {
        **state,
        "active_rules": [*state["active_rules"], "swap"],
        "swap_pair": ["aoi", "ren"],
    }
    shown = logic.display_look(state, logic.find_resident(state, "aoi"))
    assert (shown["owner"], shown["kind"]) == ("ren", "rule")
    assert look_tags(state, logic.find_resident(state, "aoi")) == "1boy, cat ears"


def test_combo_needs_a_custom_rule_and_two_components():
    state, first = _with_rule(_world())
    assert logic.active_combo(state) is None
    dress_only = logic.set_rule(_world(), "dress", True, random.Random(0))
    assert logic.active_combo(dress_only) is None

    state, second = _with_rule(state, "猫の日", "cat ears")
    combo = logic.active_combo(state)
    assert combo["rule_ids"] == [first, second]
    assert logic.combo_tags(state, combo["rule_ids"]) == "maid outfit, apron, cat ears"
    reordered = logic.combo_digest([second, first], False)
    assert reordered == combo["digest"]


def test_look_status_tracks_stale_images_and_rule_deletion():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    state = _look(state, "aoi", "rule", rule_id, source="maid outfit")
    state = _look(state, "ren", "rule", rule_id, source="old outfit")

    assert logic.rule_look_status(state, rule_id) == {
        "ready": 1,
        "stale": 1,
        "total": 2,
        "pending": ["ren"],
        "resident_ids": ["aoi", "ren"],
    }
    deleted = logic.delete_custom_rule(state, rule_id)
    assert all(not r["rule_images"] for r in deleted["residents"])


def test_prompt_links_rule_look_to_rule_text_and_feminine_form():
    state, _ = _with_rule(_world(), tags="maid outfit, frilled apron")
    ren = logic.find_resident(state, "ren")

    summary = current_appearance_summary(state, ren)
    assert summary.startswith("a look set by the rule 'メイドの日'")
    assert logic.is_male_in_feminine_form(state, ren)
    text = appearance_focus_text(state, (logic.find_resident(state, "aoi"), ren), "ja")
    assert "set by the world rules ('メイドの日': 全員がメイド服で過ごす)" in text


def test_rule_look_is_lived_as_common_sense_without_complaints():
    state, _ = _with_rule(_world(), name="グラビアの日", tags="bikini")
    aoi = logic.find_resident(state, "aoi")
    ren = logic.find_resident(state, "ren")

    assert logic.is_reality_look(state, aoi)
    text = appearance_focus_text(state, (aoi, ren), "ja")
    # 掟の姿には、変身のような照れ・ぼやきの反応を要求しない
    assert "grumbling" not in text
    assert "always show the current look as part of everyday life" in text
    assert REALITY_STANCE in text
    # 元は男性の住民も、戸惑いではなく受け入れたうえでのかすかな違和感だけ
    guidance = male_confusion_guidance(state, ren, "Ren")
    assert "takes it as normal" in guidance
    assert "Do not have him accept it calmly" not in text
    assert "normal in this world" in look_hint(state, aoi)
    assert REALITY_STANCE in active_rules_text(state, "ja")


def test_transform_look_still_asks_for_reactions():
    state = logic.set_transformation(
        _world(),
        "aoi",
        {"description": "猫耳", "tags": "1girl, cat ears", "image": "tf.png", "day": 1},
    )
    aoi = logic.find_resident(state, "aoi")

    assert not logic.is_reality_look(state, aoi)
    text = appearance_focus_text(state, (aoi,), "ja")
    assert "always include reactions to the current look" in text


def test_reality_look_and_facts_are_written_as_always_true():
    state, reality = logic.add_reality(_world(), "aoi", "昔からグラビアアイドル")
    state = logic.set_transformation(
        state,
        "aoi",
        {
            "description": "昔からグラビアアイドル",
            "tags": "1girl, bikini",
            "image": "tf.png",
            "day": 1,
            "kind": "reality",
            "reality_id": reality["id"],
        },
    )
    aoi = logic.find_resident(state, "aoi")
    ren = logic.find_resident(state, "ren")

    assert logic.is_reality_look(state, aoi)
    assert aoi["adaptation"] is None
    assert "always show the current look as part of everyday life" in (
        appearance_focus_text(state, (aoi, ren), "ja")
    )
    # 際どい姿も、照れではなく当たり前として描く
    risque = risque_focus_text(state, (aoi,), "ja")
    assert "carries it naturally" in risque
    assert "trying to cover up" not in risque
    assert "common sense about" in residents_text(state, "ja")
    system, user = transform_reaction_prompts(
        state, aoi, "昔からグラビアアイドル", [ren], "ja", nsfw=False, reality=True
    )
    assert "nobody notices any change" in system
    assert "surprise, embarrassment" not in system
    assert "The new common sense" in user


def test_world_memo_is_passed_as_the_reality_of_the_world():
    state = {**_world(), "world_memo": "住民は全員グラビアアイドルとして暮らしている"}

    section = memo_section(state)
    assert "common sense" in section
    assert REALITY_STANCE in section
    assert section.endswith("住民は全員グラビアアイドルとして暮らしている")


def test_normalize_keeps_looks_and_old_rules_get_empty_appearance():
    state, rule_id = _with_rule(_world())
    state = _look(state, "aoi", "rule", rule_id)
    legacy = {**state, "custom_rules": [{"id": rule_id, "name": "n", "text": "t"}]}

    normalized = logic.normalize_state(legacy)

    assert normalized["custom_rules"][0]["appearance_tags"] == ""
    assert logic.find_resident(normalized, "aoi")["rule_images"][rule_id]["image"]
    assert normalized["custom_rules"][0]["body_gender"] is None


def test_set_gender_token_replaces_gender_tags():
    assert logic.set_gender_token(
        "1boy, solo, male focus, short black hair, maid outfit", "female"
    ) == ("1girl, solo, short black hair, maid outfit")
    assert logic.set_gender_token("woman, long hair", "male") == "1boy, long hair"
    assert logic.set_gender_token("", "male") == logic.ensure_gender_token("", "male")


def test_body_changing_rule_changes_body_gender_and_story_note():
    plain, _ = _with_rule(_world())
    ren = logic.find_resident(plain, "ren")
    assert logic.body_gender(plain, ren) == "male"
    assert "his body stays male" in appearance_note(plain, ren)

    state, rule_id = _with_rule(
        _world(), tags="long hair, maid outfit", body_gender="female"
    )
    ren = logic.find_resident(state, "ren")
    assert logic.body_gender(state, ren) == "female"
    assert "originally a man, now in a woman's body" in appearance_note(state, ren)
    # 掟を外せば元の体に戻る
    off = logic.set_rule(state, rule_id, False, random.Random(0))
    assert logic.body_gender(off, logic.find_resident(off, "ren")) == "male"

    state, _ = _with_rule(_world(), tags="suit", body_gender="male")
    aoi = logic.find_resident(state, "aoi")
    assert logic.body_gender(state, aoi) == "male"
    assert "originally a woman, now in a man's body" in appearance_note(state, aoi)


def test_combo_body_gender_follows_the_later_rule():
    state, _ = _with_rule(_world(), tags="long hair", body_gender="female")
    state, second = _with_rule(state, "猫の日", "cat ears")
    combo = logic.active_combo(state)
    assert logic.look_body_gender(state, combo["rule_ids"]) == "female"
    assert logic.body_gender(state, logic.find_resident(state, "ren")) == "female"

    state, _ = _with_rule(state, "紳士の日", "suit", body_gender="male")
    combo = logic.active_combo(state)
    assert logic.look_body_gender(state, combo["rule_ids"]) == "male"
    assert second in combo["rule_ids"]


def test_look_status_is_stale_after_body_gender_changes():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    state = _look(state, "aoi", "rule", rule_id, source="maid outfit")
    assert logic.rule_look_status(state, rule_id)["ready"] == 1

    changed = logic.update_custom_rule(
        state, rule_id, "メイドの日", "全員がメイド服で過ごす", body_gender="female"
    )
    assert logic.custom_rule(changed, rule_id)["body_gender"] == "female"
    assert logic.rule_look_status(changed, rule_id) == {
        "ready": 0,
        "stale": 1,
        "total": 2,
        "pending": ["aoi", "ren"],
        "resident_ids": ["aoi", "ren"],
    }
    redrawn = _look(changed, "aoi", "rule", rule_id, body="female")
    assert logic.rule_look_status(redrawn, rule_id)["ready"] == 1
    # 編集で性別を送らなければ「変えない」に戻る
    reset = logic.update_custom_rule(
        redrawn, rule_id, "メイドの日", "全員がメイド服で過ごす"
    )
    assert logic.custom_rule(reset, rule_id)["body_gender"] is None


def test_rule_look_instruction_states_body_change():
    keep = rule_look_instruction("long hair, maid outfit")
    assert "long hair replaces short hair" in keep
    assert "Keep the person's own gender." in keep
    female = rule_look_instruction("long hair", body_gender="female")
    assert "1girl instead of 1boy" in female
    assert "Keep the person's own gender." not in female


def _transform(state, resident_id="aoi", tags="1girl, magical girl", image="tf.png"):
    return logic.set_transformation(
        state,
        resident_id,
        {"description": "魔法少女", "tags": tags, "image": image, "day": 1},
    )


def _layered(state, resident_id, kind, key, tags="1girl, magical girl, maid outfit"):
    source = logic.layer_source(state, {"kind": kind, "key": key})
    return logic.set_layered_look_image(
        state,
        resident_id,
        kind=kind,
        key=key,
        entry={
            "image": f"layer_{kind}_{resident_id}.png",
            "tags": tags,
            "source_tags": source["source_tags"],
            "source_body": source["body_gender"],
        },
    )


def test_rule_enabled_after_transform_is_layered_on_top():
    state = _transform(_world())
    state, rule_id = _with_rule(state, tags="maid outfit")
    aoi = logic.find_resident(state, "aoi")

    assert [layer["kind"] for layer in logic.due_layers(state, aoi)] == ["rule"]
    # 重ねた姿がまだ無いうちは変身のまま。生成状況では未生成に数える
    assert logic.own_look(state, aoi)["kind"] == "transform"
    assert "aoi" in logic.rule_look_status(state, rule_id)["pending"]

    state = _layered(state, "aoi", "rule", rule_id)
    aoi = logic.find_resident(state, "aoi")
    look = logic.own_look(state, aoi)
    assert (look["kind"], look["layered"], look["tags"]) == (
        "rule",
        True,
        "1girl, magical girl, maid outfit",
    )
    assert "aoi" not in logic.rule_look_status(state, rule_id)["pending"]
    assert logic.layered_look_ready(state, aoi, logic.due_layers(state, aoi)[0])
    # 文章には変身と掟の装いの両方を渡す
    summary = current_appearance_summary(state, aoi)
    assert "a look transformed into: '魔法少女'" in summary
    assert "on top of that now a look set by the rule 'メイドの日'" in summary

    # 掟を切れば変身の姿に戻る
    off = logic.set_rule(state, rule_id, False, random.Random(0))
    assert logic.own_look(off, logic.find_resident(off, "aoi"))["kind"] == "transform"
    # 変身を解けば、本人の掟の姿(まだ無いので通常の姿)
    cleared = logic.clear_transformation(state, "aoi")
    assert logic.own_look(cleared, logic.find_resident(cleared, "aoi"))["kind"] == (
        "base"
    )


def test_transform_after_rule_stays_on_top_until_rule_is_enabled_again():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    state = _look(state, "aoi", "rule", rule_id)
    state = _transform(state)
    aoi = logic.find_resident(state, "aoi")

    assert logic.due_layers(state, aoi) == []
    assert logic.own_look(state, aoi)["kind"] == "transform"
    assert "on top of that" not in current_appearance_summary(state, aoi)
    # 変身が上の住民は、本人の掟の姿の記録で生成状況を数える(これまでどおり)
    assert "aoi" not in logic.rule_look_status(state, rule_id)["pending"]

    # 掟を有効にし直すと、あとから行った掟が上になる
    state = logic.set_rule(state, rule_id, False, random.Random(0))
    state = logic.set_rule(state, rule_id, True, random.Random(0))
    aoi = logic.find_resident(state, "aoi")
    assert [layer["key"] for layer in logic.due_layers(state, aoi)] == [rule_id]


def test_dress_layer_history_and_reapply():
    state = _transform(_world(), "ren", tags="1boy, knit sweater", image="knit.png")
    state = logic.set_rule(state, "dress", True, random.Random(0))
    ren = logic.find_resident(state, "ren")

    layer = logic.transform_layer(state, ren)
    assert layer["kind"] == "dress"
    # 元が男性の住民がドレスを重ねられたら、女性的な姿への戸惑いを描く
    assert logic.is_male_in_feminine_form(state, ren)
    assert "wearing a dress (the dress rule)" in current_appearance_summary(state, ren)
    # 変身していない住民のドレスは重ねる姿ではない(住民の「ドレス姿を生成」で作る)
    aoi = logic.find_resident(state, "aoi")
    assert logic.look_entry_for(state, aoi, "dress", logic.DRESS_LAYER_KEY) == {}

    state = _layered(state, "ren", "dress", logic.DRESS_LAYER_KEY, "1boy, dress")
    ren = logic.find_resident(state, "ren")
    assert logic.own_look(state, ren)["kind"] == "dress"
    # 履歴の同じ変身にも写るので、履歴から戻したときにも使える
    assert ren["transformation_history"][-1]["looks"]

    # 履歴から戻すのは新しい変身なので、それまでのドレスより上になる
    state = logic.reapply_transformation(state, "ren", "knit.png")
    ren = logic.find_resident(state, "ren")
    assert logic.due_layers(state, ren) == []
    assert logic.own_look(state, ren)["kind"] == "transform"


def test_layered_rule_decides_body_gender_and_old_states_keep_transform_on_top():
    state = _transform(_world(), "ren", tags="1boy, knit sweater")
    state, rule_id = _with_rule(state, "女の子の日", "", body_gender="female")
    ren = logic.find_resident(state, "ren")
    assert logic.own_body_gender(state, ren) == "female"

    # 番号の無い古い状態は、これまでどおり変身が上
    old = logic.normalize_state(
        {
            **state,
            "rule_seq": None,
            "look_seq": None,
            "residents": [
                {**item, "transformation": {**item["transformation"], "seq": None}}
                if item.get("transformation")
                else item
                for item in state["residents"]
            ],
        }
    )
    assert old["rule_seq"] == {} and old["look_seq"] == 0
    assert logic.due_layers(old, logic.find_resident(old, "ren")) == []
    # 正規化しても番号は残る
    kept = logic.normalize_state(state)
    assert kept["rule_seq"] == state["rule_seq"] and kept["look_seq"] > 0


# --- 世界のメモの姿(本来の性別ごと) ---


def _with_memo(state, memo="男性は胸が大きくなる"):
    state = dict(state)
    state["world_memo"] = memo
    return state


def test_old_memo_look_reads_as_the_same_look_for_both_sexes():
    state = _with_memo(_world())
    state["memo_look"] = {
        "memo": "男性は胸が大きくなる",
        "tags": "bikini",
        "body_gender": "female",
    }
    aoi, ren = state["residents"]

    look = logic.active_memo_look(state)
    # 本来と同じ体の性別は「体は変えない」として扱う
    assert look["groups"]["female"] == {"tags": "bikini", "body_gender": None}
    assert look["groups"]["male"] == {"tags": "bikini", "body_gender": "female"}
    assert look["edited"] is False
    assert logic.body_gender(state, aoi) == "female"
    assert logic.body_gender(state, ren) == "female"


def test_memo_look_changes_only_the_matching_original_sex():
    state = logic.set_memo_look(
        _with_memo(_world()),
        {"female": None, "male": {"tags": "large breasts", "body_gender": None}},
    )
    aoi, ren = state["residents"]

    assert logic.memo_look_for(state, aoi) is None
    assert logic.memo_look_for(state, ren) == {
        "tags": "large breasts",
        "body_gender": None,
    }
    assert logic.appearance_kind(state, aoi) is None
    assert logic.appearance_kind(state, ren) == "memo"
    assert logic.body_gender(state, ren) == "male"
    status = logic.memo_look_status(state)
    assert (status["total"], status["pending"]) == (1, ["ren"])
    assert "large breasts" in current_appearance_summary(state, ren)
    assert current_appearance_summary(state, aoi) is None

    # メモを変えると、確かめ直すまで効かない
    changed = _with_memo(state, "文体は軽めに")
    assert logic.memo_look_for(changed, ren) is None
