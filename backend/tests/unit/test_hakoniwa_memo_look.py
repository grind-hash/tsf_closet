"""AI箱庭の世界のメモの姿: LLM の判断を本来の性別ごとの姿に整える。"""

from __future__ import annotations

import pytest

from gateway.services import hakoniwa_generation as gen
from gateway.services.hakoniwa_logic import HakoniwaError


def _stub(monkeypatch, output: str) -> None:
    async def fake(system, user, *, novelai_model, max_tokens=1400):
        return output

    monkeypatch.setattr(gen, "_generate_text", fake)


@pytest.mark.asyncio
async def test_plan_keeps_each_sex_apart_and_drops_unsafe_tags(monkeypatch):
    _stub(
        monkeypatch,
        '{"changes_look": true, "female": null, "male": {"appearance_tags": '
        '"beautiful girl, feminine_face, female body, large breasts, '
        'women\'s clothes, blouse, skirt, bra", "body_gender": "keep"}}',
    )

    groups = await gen.plan_memo_look("男性は美少女の巨乳になる", novelai_model=None)

    assert groups["female"] is None
    # 人物・性別の語、漠然とした服、上着と一緒の下着は外す
    assert groups["male"] == {
        "tags": "feminine_face, large breasts, blouse, skirt",
        "body_gender": None,
    }


@pytest.mark.asyncio
async def test_plan_keeps_underwear_when_it_is_the_whole_look(monkeypatch):
    _stub(
        monkeypatch,
        '{"changes_look": true, "female": {"appearance_tags": "bra, panties", '
        '"body_gender": "keep"}, "male": {"appearance_tags": "boxers", '
        '"body_gender": "keep"}}',
    )

    groups = await gen.plan_memo_look("家では下着で過ごす", novelai_model=None)

    assert groups["female"]["tags"] == "bra, panties"
    assert groups["male"]["tags"] == "boxers"


@pytest.mark.asyncio
async def test_plan_without_groups_applies_to_both_sexes(monkeypatch):
    _stub(
        monkeypatch,
        '{"changes_look": true, "appearance_tags": "maid outfit", '
        '"body_gender": "female"}',
    )

    groups = await gen.plan_memo_look("全員メイド", novelai_model=None)

    assert groups["female"] == {"tags": "maid outfit", "body_gender": "female"}
    assert groups["male"] == {"tags": "maid outfit", "body_gender": "female"}


def test_manual_memo_tags_allow_empty_and_drop_person_tags():
    assert gen.clean_manual_memo_tags("  ") == ""
    assert gen.clean_manual_memo_tags("1boy, large breasts\nbra") == (
        "large breasts, bra"
    )
    with pytest.raises(HakoniwaError) as error:
        gen.clean_manual_memo_tags("1girl, solo")
    assert error.value.code == "invalid_tags"
