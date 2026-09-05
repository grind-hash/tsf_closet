"""services/providers.py: プロバイダー判定の正規化と設定への追従。"""

from __future__ import annotations

import json

from gateway.services.providers import (
    KNOWN_PROVIDERS,
    Provider,
    normalize_provider,
    resolve_image_description_provider,
    resolve_image_provider,
    resolve_text_provider,
)
from gateway.settings.config import settings


def test_known_values_are_accepted_case_insensitively() -> None:
    assert KNOWN_PROVIDERS == ("selfhost", "openrouter", "novelai")
    assert normalize_provider("NovelAI") is Provider.NOVELAI
    assert normalize_provider(" openrouter ") is Provider.OPENROUTER
    assert normalize_provider(Provider.SELFHOST) is Provider.SELFHOST


def test_unknown_or_empty_values_fall_back_to_default() -> None:
    assert normalize_provider("comfyui") is Provider.SELFHOST
    assert normalize_provider("") is Provider.SELFHOST
    assert normalize_provider(None) is Provider.SELFHOST
    assert normalize_provider("openai", default=Provider.NOVELAI) is Provider.NOVELAI


def test_resolvers_follow_settings_and_prefer_overrides(monkeypatch) -> None:
    monkeypatch.setattr(settings, "image_provider", "OpenRouter")
    monkeypatch.setattr(settings, "feeling_provider", "novelai")
    monkeypatch.setattr(settings, "image_description_provider", "bogus")

    assert resolve_image_provider() is Provider.OPENROUTER
    assert resolve_text_provider() is Provider.NOVELAI
    assert resolve_image_description_provider() is Provider.SELFHOST

    assert resolve_image_provider("novelai") is Provider.NOVELAI
    assert resolve_text_provider("selfhost") is Provider.SELFHOST
    # 空の上書きは設定値へ戻る
    assert resolve_text_provider("") is Provider.NOVELAI


def test_provider_behaves_like_its_string_value() -> None:
    assert Provider.NOVELAI == "novelai"
    assert f"{Provider.NOVELAI}" == "novelai"
    assert json.dumps({"provider": Provider.NOVELAI}) == '{"provider": "novelai"}'
    assert Provider.NOVELAI in ("selfhost", "openrouter", "novelai")
