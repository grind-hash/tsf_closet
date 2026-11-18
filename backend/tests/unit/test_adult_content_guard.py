"""成人向けの場面で未成年を思わせる目印を見つける判定のテスト。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.services.adult_content_guard import (
    MinorMarkerError,
    find_minor_markers,
    has_minor_markers,
)
from gateway.services.game_service import (
    _ImagePayload,
    _raise_if_minor_markers,
    _with_adult_image_safeguards,
)
from gateway.services.session_request_service import (
    customer_minor_markers,
    experience_blocked_for,
    public_request_view,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1girl, teenager, long hair", ["teenager"]),
        ("1girl, school_uniform, blazer", ["school uniform"]),
        ("{{1girl, training bra, panties}}", ["training bra"]),
        ("1girl, (randoseru:1.2)", ["randoseru"]),
        ("1girl, 16 years old", ["16 years old"]),
        ("1girl, 17yo", ["17yo"]),
        ("1girl, jk, blazer", ["jk"]),
        ("女子高生の姿", ["女子高生"]),
        ("16歳の姿", ["16歳"]),
        ("ロリ体型", ["ロリ"]),
    ],
)
def test_finds_explicit_minor_markers(text: str, expected: list[str]) -> None:
    assert find_minor_markers(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # 成人にもある見た目の特徴は対象にしない
        "1girl, petite, short, flat chest, small breasts, twintails",
        # ロリータ服はファッション
        "1girl, gothic lolita, lolita fashion",
        "ロリータ服の女性",
        # 成人の学生
        "1girl, college student, cardigan",
        # 子どもと無関係な語
        "1girl, babydoll, kidney bean pendant, 25 years old",
        "",
    ],
)
def test_ignores_traits_adults_also_have(text: str) -> None:
    assert find_minor_markers(text) == []


def test_checks_every_text_and_skips_none() -> None:
    assert has_minor_markers(None, "1girl, dress", "teen")
    assert not has_minor_markers(None, "1girl, dress")


@pytest.mark.parametrize(
    "text",
    [
        # 性格・口調・経歴・職業の言い回しは、本人の年齢を示さない
        "明るく子どもっぽい性格",
        "少し子どもっぽい話し方",
        "子供っぽさが残る",
        "子どもの頃から体が弱い",
        "子供時代は海辺の町で育った",
        "子ども扱いされるのが嫌い",
        "高校の先生",
        "小学校教師",
        "She was shy as a child.",
        "A high school teacher who loves tea.",
    ],
)
def test_character_setting_ignores_phrases_without_age(text: str) -> None:
    assert find_minor_markers(text, character_setting=True) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 見た目を言うときは目印のまま
        ("子どもっぽい体型", ["子ども"]),
        ("子供っぽい顔立ち", ["子供"]),
        ("高校2年生", ["高校"]),
        ("女子高生", ["女子高生"]),
        ("16歳", ["16歳"]),
        ("a teenager who loves music", ["teenager"]),
    ],
)
def test_character_setting_still_finds_age_markers(
    text: str, expected: list[str]
) -> None:
    assert find_minor_markers(text, character_setting=True) == expected


def test_wishes_and_looks_stay_strict_about_childish_wording() -> None:
    # 願い・姿・場面の指示では、性格の言い回しも目印として扱う(慎重な側)
    assert find_minor_markers("子どもっぽい性格") == ["子ども"]


class _Store:
    def __init__(
        self, after_description: str | None, panel: dict | None = None
    ) -> None:
        self._after = after_description
        self._panel = panel

    async def get_latest_history(self, session_id: str):
        if self._after is None:
            return None
        return SimpleNamespace(after_description=self._after)

    async def get_protagonist_profile(self, session_id: str):
        return self._panel


@pytest.mark.asyncio
async def test_customer_markers_read_the_profile_panel_and_look() -> None:
    profile = {"personality": "穏やか", "description": "会社員"}
    assert await customer_minor_markers(_Store(None), "s", profile, "1boy, suit") == []
    # 人物パネルのメモ・興味にある目印
    panel = {"memo": "中学生", "interests": ["読書", "高校の部活"]}
    assert await customer_minor_markers(
        _Store(None, panel), "s", profile, "1boy, suit"
    ) == ["中学生", "高校"]
    # 来店時の姿は除外なしで見る
    assert await customer_minor_markers(
        _Store(None), "s", profile, "1girl, school uniform"
    ) == ["school uniform"]
    # 性格の言い回しは目印にしない
    childish = {"personality": "子どもっぽい性格", "speech_style": "子どもっぽい口調"}
    assert await customer_minor_markers(_Store(None), "s", childish, "1boy") == []


_REQUEST = {
    "sensitive": True,
    "wish": "a calm, elegant look",
    "experience": "a scene in a dream bedroom",
    "preferences": [],
}


@pytest.mark.asyncio
async def test_experience_is_hidden_when_the_look_has_markers() -> None:
    blocked = await experience_blocked_for(_Store("1girl, teenager"), _REQUEST, "s")
    view = public_request_view(
        _REQUEST, [], can_regenerate=False, experience_blocked=blocked
    )
    assert view["experience_blocked"] is True
    assert view["experience"] == ""


@pytest.mark.asyncio
async def test_experience_is_kept_for_traits_adults_also_have() -> None:
    blocked = await experience_blocked_for(_Store("1girl, petite"), _REQUEST, "s")
    view = public_request_view(
        _REQUEST, [], can_regenerate=False, experience_blocked=blocked
    )
    assert view["experience_blocked"] is False
    assert view["experience"] == "a scene in a dream bedroom"


@pytest.mark.asyncio
async def test_all_ages_requests_are_never_blocked() -> None:
    request = {**_REQUEST, "sensitive": False}
    assert not await experience_blocked_for(_Store("1girl, teenager"), request, "s")


def test_raise_if_minor_markers_stops_the_scene() -> None:
    with pytest.raises(MinorMarkerError):
        _raise_if_minor_markers("1girl, dress", "1girl, school uniform")
    _raise_if_minor_markers("1girl, dress", None)


def test_adult_safeguards_tag_every_character_and_add_negatives() -> None:
    payload = _ImagePayload(
        final_prompt="1girl, dress",
        api_prompt="bedroom",
        characters=None,
        api_characters=[
            {"prompt": "1girl, dress", "stage_index": 0},
            {"prompt": "1boy, adult", "stage_index": None},
        ],
        negative_prompt="lowres",
    )
    guarded = _with_adult_image_safeguards(payload, is_novelai=True)
    assert guarded.api_prompt == "bedroom, adult"
    assert [c["prompt"] for c in guarded.api_characters or []] == [
        "1girl, dress, adult",
        "1boy, adult",
    ]
    assert guarded.negative_prompt is not None
    assert guarded.negative_prompt.startswith("lowres, child, loli")
    # 履歴用の姿には足さない
    assert guarded.final_prompt == "1girl, dress"


def test_adult_safeguards_use_a_sentence_for_edit_instructions() -> None:
    payload = _ImagePayload(
        final_prompt="",
        api_prompt="Move the person to a bedroom.",
        characters=None,
        api_characters=None,
        negative_prompt=None,
    )
    guarded = _with_adult_image_safeguards(payload, is_novelai=False)
    assert guarded.api_prompt.endswith("Everyone in the image is an adult.")
