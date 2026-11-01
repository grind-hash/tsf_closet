"""NovelAI 着せ替えタグ生成での、ショーツ / ハーフパンツの取り違え防止。"""

from __future__ import annotations

import pytest

from gateway.services.llm_service import LLMResult, LLMService
from gateway.services.prompt_expander_prompts import JAPANESE_TAG_GLOSSARY_RULE


class _FakeNovelAIClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.system_prompts: list[str] = []

    async def generate_text(self, system_prompt, user_prompt, model_override=None):
        self.system_prompts.append(system_prompt)
        return LLMResult(content=self.content, provider="novelai")


def _service_with(content: str) -> tuple[LLMService, _FakeNovelAIClient]:
    service = LLMService()
    client = _FakeNovelAIClient(content)
    service._novelai_client = client
    return service, client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generated",
    [
        '{"character": "1girl, polo shirt, half pants, men\'s shorts", "scene": ""}',
        '{"character": "1boy, white t-shirt, black shorts", "scene": ""}',
        '{"character": "1girl, denim shorts, boyshorts", "scene": ""}',
    ],
)
async def test_outerwear_shorts_are_not_turned_into_panties(generated):
    service, _client = _service_with(generated)

    result = await service.generate_novelai_image_prompt(
        instruction="水色のポロシャツ、ハーフパンツ（メンズズボン）",
        previous_prompt="1girl, white t-shirt, shorts",
    )

    assert result == generated
    assert "panties" not in result


@pytest.mark.asyncio
async def test_shorts_from_japanese_shorts_becomes_panties():
    service, _client = _service_with('{"character": "1girl, shorts", "scene": ""}')

    result = await service.generate_novelai_image_prompt(
        instruction="白いショーツ",
        previous_prompt="1girl, white t-shirt",
    )

    assert result == '{"character": "1girl, panties", "scene": ""}'


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [None, "Custom tag system prompt."])
async def test_glossary_rule_is_added_to_every_system_prompt(override):
    service, client = _service_with('{"character": "1girl", "scene": ""}')

    await service.generate_novelai_image_prompt(
        instruction="ハーフパンツ",
        system_prompt_override=override,
        extra_system_suffix="\nSUFFIX",
    )

    system_prompt = client.system_prompts[0]
    assert JAPANESE_TAG_GLOSSARY_RULE in system_prompt
    assert "ハーフパンツ" in system_prompt
    assert system_prompt.endswith("\nSUFFIX")
