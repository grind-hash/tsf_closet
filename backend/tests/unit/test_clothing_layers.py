"""衣装レイヤー考慮機能の単体テスト。"""

from types import SimpleNamespace

import pytest

from gateway.models import PlayRequest
from gateway.routes.game_router import PlayStreamRequest, preview_prompt
from gateway.services.clothing_layers import (
    CLOTHING_LAYER_COVERED_NEGATIVE,
    CLOTHING_LAYER_FEELING_RULE,
    CLOTHING_LAYER_IMAGE_RULE,
    append_clothing_layer_feeling_rule,
    append_clothing_layer_image_rule,
    append_worn_under_layers,
    clothing_layer_negative_suffix,
    ensure_worn_under_layers,
    extract_undergarment_tags,
    peel_undergarment_tags,
    split_worn_under_layers,
    strip_worn_under_layers_for_image,
)
from gateway.services.game_service import game_service


def test_image_rule_is_noop_when_disabled() -> None:
    base = "base image prompt"

    assert append_clothing_layer_image_rule(base, False) == base


def test_image_rule_defines_coverage_and_inventory_channel() -> None:
    result = append_clothing_layer_image_rule("base", True)

    assert CLOTHING_LAYER_IMAGE_RULE in result
    assert "body/anatomy, underwear, inner garments, outer garments" in result
    assert "WORN_UNDER_LAYERS:" in result
    assert "You decide visibility from the CURRENT user instruction" in result
    assert "Covered does NOT mean removed" in result
    assert "Reveal / check / sheer / undress" in result
    assert "Omit covered underwear" not in result


def test_feeling_rule_is_noop_when_disabled() -> None:
    base = "base feeling prompt"

    assert append_clothing_layer_feeling_rule(base, False) == base


def test_feeling_rule_defers_visibility_to_instruction_intent() -> None:
    result = append_clothing_layer_feeling_rule("base", True)

    assert CLOTHING_LAYER_FEELING_RULE in result
    assert "布越しの感触" in result
    assert "WORN_UNDER_LAYERS" in result
    assert "意図から判断" in result
    assert "頑なに「見えない」と打ち消さない" in result


def test_split_and_strip_worn_under_layers() -> None:
    text = (
        "1girl, white knit top, black skirt\n\n"
        "WORN_UNDER_LAYERS: turquoise bra, turquoise panties"
    )
    visual, inventory = split_worn_under_layers(text)

    assert "white knit top" in visual
    assert "turquoise bra" in inventory
    assert "WORN_UNDER_LAYERS" not in visual
    assert strip_worn_under_layers_for_image(text) == visual
    assert "turquoise bra" not in strip_worn_under_layers_for_image(text)


def test_ensure_trusts_llm_visual_when_bra_shown_with_outer() -> None:
    """露出意図で LLM が visual に bra を載せた場合、コードは剥がさない。"""
    previous = append_worn_under_layers(
        "1girl, white sleeveless knit top, black skirt",
        "turquoise bra, turquoise panties",
    )
    current = (
        "1girl, white sleeveless knit top, clothes lift, turquoise bra, black skirt"
    )

    result = ensure_worn_under_layers(
        current,
        previous,
        respect_clothing_layers=True,
        instruction="トップスをずらして、ブラの色を確認してみる",
    )
    visual, inventory = split_worn_under_layers(result)

    assert "turquoise bra" in visual.lower()
    assert "turquoise bra" in inventory.lower()
    assert (
        clothing_layer_negative_suffix(
            result,
            respect_clothing_layers=True,
            instruction="anything",
        )
        == ""
    )


def test_ensure_keeps_covered_inventory_without_forcing_visual() -> None:
    """LLM が inventory のみにした場合、visual へ強制注入しない。"""
    previous = append_worn_under_layers(
        "1girl, white shirt",
        "turquoise bra, turquoise panties",
    )
    current = "1girl, white sleeveless knit top, black skirt"

    result = ensure_worn_under_layers(
        current,
        previous,
        respect_clothing_layers=True,
        instruction="トップスをずらして、ブラの色を確認してみる",
    )
    visual, inventory = split_worn_under_layers(result)

    assert "turquoise bra" not in visual.lower()
    assert "turquoise bra" in inventory.lower()


def test_ensure_inherits_previous_inventory_for_outer_change() -> None:
    previous = append_worn_under_layers(
        "1girl, white shirt",
        "turquoise bra, turquoise panties",
    )
    current = "1girl, red dress"

    result = ensure_worn_under_layers(
        current,
        previous,
        respect_clothing_layers=True,
        instruction="赤いドレスを着る",
    )
    visual, inventory = split_worn_under_layers(result)

    assert "turquoise bra" in inventory
    assert "panties" in inventory
    # 継承しても visual には載せない（見せる判定は LLM）
    assert "turquoise bra" not in visual.lower()


def test_ensure_keeps_bra_visible_when_underwear_only() -> None:
    current = "1girl, turquoise bra, turquoise panties"

    result = ensure_worn_under_layers(
        current,
        None,
        respect_clothing_layers=True,
        instruction="ターコイズブルーのブラとパンティ",
    )
    visual, inventory = split_worn_under_layers(result)

    assert "bra" in visual.lower()
    assert "bra" in inventory.lower()


def test_ensure_noop_when_disabled() -> None:
    prompt = "1girl, white shirt, bra"

    assert (
        ensure_worn_under_layers(
            prompt, None, respect_clothing_layers=False, instruction="x"
        )
        == prompt
    )


def test_peel_skips_braid_and_bracelet() -> None:
    visual, moved = peel_undergarment_tags(
        "long braid, gold bracelet, turquoise bra, blue dress"
    )

    assert "braid" in visual
    assert "bracelet" in visual
    assert "dress" in visual
    assert "bra" in moved
    assert "braid" not in moved


def test_covered_negative_uses_visual_not_keywords() -> None:
    covered = append_worn_under_layers("1girl, white shirt", "turquoise bra")
    assert (
        clothing_layer_negative_suffix(
            covered, respect_clothing_layers=True, instruction="ずらして確認"
        )
        == CLOTHING_LAYER_COVERED_NEGATIVE
    )

    revealed = "1girl, white shirt, turquoise bra\n\nWORN_UNDER_LAYERS: turquoise bra"
    assert (
        clothing_layer_negative_suffix(
            revealed, respect_clothing_layers=True, instruction="上着を着る"
        )
        == ""
    )

    underwear_only = "1girl, turquoise bra"
    assert (
        clothing_layer_negative_suffix(
            underwear_only, respect_clothing_layers=True, instruction="下着だけ"
        )
        == ""
    )


def test_extract_undergarment_tags() -> None:
    tags = extract_undergarment_tags("black hair, turquoise bra, red panties, skirt")
    assert "turquoise bra" in tags
    assert "red panties" in tags
    assert "skirt" not in tags


def test_request_models_default_to_disabled() -> None:
    play_request = PlayRequest(instruction="着替える")
    stream_request = PlayStreamRequest(instruction="着替える")

    assert play_request.respect_clothing_layers is False
    assert stream_request.respect_clothing_layers is False


def test_request_models_accept_enabled_value() -> None:
    play_request = PlayRequest(
        instruction="着替える",
        respect_clothing_layers=True,
    )
    stream_request = PlayStreamRequest(
        instruction="着替える",
        respect_clothing_layers=True,
    )

    assert play_request.respect_clothing_layers is True
    assert stream_request.respect_clothing_layers is True


def test_prepare_payload_strips_inventory_and_trusts_visual() -> None:
    # LLM が被覆配置（inventory のみ）にしたケース
    state_prompt, image_prompt, _sc, _ic, neg = (
        game_service._prepare_clothing_layer_image_payload(
            append_worn_under_layers(
                "1girl, white shirt, black skirt",
                "turquoise bra, turquoise panties",
            ),
            None,
            previous_prompt=append_worn_under_layers(
                "1girl, white shirt",
                "turquoise bra, turquoise panties",
            ),
            instruction="白いシャツと黒スカート",
            respect_clothing_layers=True,
            negative_prompt="lowres",
        )
    )

    assert "WORN_UNDER_LAYERS:" in state_prompt
    assert "WORN_UNDER_LAYERS:" not in image_prompt
    assert "bra" not in image_prompt.lower()
    assert "braless" in (neg or "")
    assert "lowres" in (neg or "")

    # LLM が露出配置（visual に bra）にしたケース
    _sp, image_prompt2, _sc2, _ic2, neg2 = (
        game_service._prepare_clothing_layer_image_payload(
            "1girl, white shirt, clothes lift, turquoise bra\n\n"
            "WORN_UNDER_LAYERS: turquoise bra",
            None,
            previous_prompt=append_worn_under_layers(
                "1girl, white shirt", "turquoise bra"
            ),
            instruction="トップスをずらしてブラの色を確認",
            respect_clothing_layers=True,
            negative_prompt="lowres",
        )
    )
    assert "turquoise bra" in image_prompt2.lower()
    assert "braless" not in (neg2 or "")


@pytest.mark.asyncio
async def test_image_prompt_generation_appends_rule_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    async def fake_generate_image_edit_prompt(**kwargs):
        captured.append(kwargs["extra_system_suffix"])
        return SimpleNamespace(content="generated", provider="test", cost_usd=None)

    monkeypatch.setattr(
        "gateway.services.game_service.llm_service.generate_image_edit_prompt",
        fake_generate_image_edit_prompt,
    )

    await game_service._generate_image_edit_prompt(
        instruction="シフォンブラウスとタイトスカート",
        current_description="underwear, pubic hair",
        use_memory=False,
        respect_clothing_layers=False,
    )
    await game_service._generate_image_edit_prompt(
        instruction="シフォンブラウスとタイトスカート",
        current_description="underwear, pubic hair",
        use_memory=False,
        respect_clothing_layers=True,
    )

    assert captured[0] == ""
    assert CLOTHING_LAYER_IMAGE_RULE in captured[1]


@pytest.mark.asyncio
async def test_feeling_generation_appends_rule_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    async def fake_generate_feeling(**kwargs):
        captured.append(kwargs["system_prompt"])
        return SimpleNamespace(content="generated", provider="test", cost_usd=None)

    monkeypatch.setattr(
        "gateway.services.game_service.llm_service.generate_feeling",
        fake_generate_feeling,
    )

    await game_service._generate_feeling(
        before_desc="before",
        after_desc="after",
        instruction="着替える",
        pronoun="僕",
        respect_clothing_layers=False,
    )
    await game_service._generate_feeling(
        before_desc="before",
        after_desc="after",
        instruction="着替える",
        pronoun="僕",
        respect_clothing_layers=True,
    )

    assert CLOTHING_LAYER_FEELING_RULE not in captured[0]
    assert CLOTHING_LAYER_FEELING_RULE in captured[1]


@pytest.mark.asyncio
async def test_preview_route_propagates_enabled_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_preview_prompts(**kwargs):
        captured.update(kwargs)
        return {
            "image_edit_prompt": "image",
            "feeling_system_prompt": "system",
            "feeling_user_prompt": "user",
            "instruction_type": "dress_up",
            "novelai_tag_prompt": None,
        }

    monkeypatch.setattr(game_service, "preview_prompts", fake_preview_prompts)

    await preview_prompt(
        PlayRequest(instruction="着替える", respect_clothing_layers=True)
    )

    assert captured["respect_clothing_layers"] is True
