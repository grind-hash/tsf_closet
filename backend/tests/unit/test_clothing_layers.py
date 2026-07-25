"""衣装レイヤー考慮機能の単体テスト。"""

from types import SimpleNamespace

import pytest

from gateway.models import PlayRequest
from gateway.routes.game_router import PlayStreamRequest, preview_prompt
from gateway.services.clothing_layers import (
    CLOTHING_LAYER_FEELING_RULE,
    CLOTHING_LAYER_IMAGE_RULE,
    append_clothing_layer_feeling_rule,
    append_clothing_layer_image_rule,
)
from gateway.services.game_service import game_service


def test_image_rule_is_noop_when_disabled() -> None:
    base = "base image prompt"

    assert append_clothing_layer_image_rule(base, False) == base


def test_image_rule_defines_coverage_and_explicit_exceptions() -> None:
    result = append_clothing_layer_image_rule("base", True)

    assert CLOTHING_LAYER_IMAGE_RULE in result
    assert "body/anatomy, underwear, inner garments, outer garments" in result
    assert "pubic hair" in result
    assert "chiffon" in result
    assert "CURRENT user instruction explicitly requests" in result
    assert "normal properly worn state" in result


def test_feeling_rule_is_noop_when_disabled() -> None:
    base = "base feeling prompt"

    assert append_clothing_layer_feeling_rule(base, False) == base


def test_feeling_rule_keeps_hidden_elements_as_sensation_only() -> None:
    result = append_clothing_layer_feeling_rule("base", True)

    assert CLOTHING_LAYER_FEELING_RULE in result
    assert "布越しの感触" in result
    assert "「見えている」「露出している」" in result
    assert "陰毛の詳細が見えるとは描写しない" in result


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
