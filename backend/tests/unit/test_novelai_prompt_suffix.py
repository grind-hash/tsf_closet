"""NovelAI の正のプロンプトに、避けたい概念を名指しする英文の否定を入れないことのテスト。

タグのモデルは "no split screen" のような否定を解釈せず、その語に引っ張られて分割・比較・
重複の絵を呼び込む。避けたい語はネガティブ側にだけ置く。
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from PIL import Image

from gateway.services import image_generation as ig

PRIMING_WORDS = (
    "split screen",
    "side-by-side",
    "side by side",
    "before/after",
    "before and after",
    "comparison",
    "twin",
    "clone",
    "duplicate",
    "transformed state",
)


@pytest.fixture
def client(monkeypatch):
    instance = ig.NovelAIImageClient(
        api_key="test-key",
        model="nai-diffusion-4-5-full",
        negative_prompt="lowres",
        i2i_strength=0.9,
        i2i_noise=0.2,
    )
    sent: dict[str, object] = {}

    async def _generate(req):
        sent["req"] = req
        return [Image.new("RGB", (8, 8), "white")]

    fake_client = SimpleNamespace(
        api_client=SimpleNamespace(image=SimpleNamespace(generate=_generate))
    )

    async def _fake_get_client():
        return fake_client

    monkeypatch.setattr(instance, "_get_client", _fake_get_client)
    instance._sent = sent  # type: ignore[attr-defined]
    return instance


@pytest.mark.parametrize("multiple_people", [False, True])
def test_positive_suffix_has_no_negated_or_priming_words(client, multiple_people):
    prompt = client._format_prompt(
        "1girl, maid outfit", multiple_people=multiple_people
    )

    lowered = prompt.lower()
    assert not re.search(r"\bno\s", lowered)
    for word in PRIMING_WORDS:
        assert word not in lowered
    assert "single frame" in lowered


def test_single_character_suffix_keeps_identity_and_solo_cues(client):
    prompt = client._format_prompt("1girl, maid outfit")

    assert "solo portrait" in prompt
    assert "same face" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("characters", "expected"),
    [
        (None, ("split screen", "comparison", "side by side", "clone")),
        (
            [
                {"prompt": "1girl", "position": (0.3, 0.5)},
                {"prompt": "1boy", "position": (0.7, 0.5)},
            ],
            ("split screen", "comparison", "before and after"),
        ),
    ],
)
async def test_priming_words_go_to_the_negative_prompt(client, characters, expected):
    await client.generate(prompt="1girl, maid outfit", seed=1, characters=characters)

    params = client._sent["req"].parameters
    negative = params.negative_prompt or ""
    for word in expected:
        assert word in negative
    positive = client._sent["req"].input.lower()
    assert "split screen" not in positive
    assert "comparison" not in positive
