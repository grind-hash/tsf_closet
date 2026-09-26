"""services/providers.py: プロバイダー判定の正規化と設定への追従。"""

from __future__ import annotations

import json

from gateway.services.providers import (
    JEV_TARGETS,
    KNOWN_PROVIDERS,
    DecisionTransport,
    Provider,
    cost_tracking_enabled,
    jev_judge_enabled,
    jev_live,
    normalize_provider,
    resolve_decision_transport,
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


def test_jev_is_not_part_of_the_generation_provider_axis() -> None:
    # Jev はテキストを生成せず chat/completions でも呼べないため Provider には入れない
    assert "jev" not in KNOWN_PROVIDERS
    assert normalize_provider("jev") is Provider.SELFHOST


def test_decision_transport_normalizes_and_defaults_to_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", " OpenRouter ")
    assert resolve_decision_transport() is DecisionTransport.OPENROUTER

    monkeypatch.setattr(settings, "jev_provider", "typesafe")
    assert resolve_decision_transport() is DecisionTransport.TYPESAFE

    monkeypatch.setattr(settings, "jev_provider", "bogus")
    assert resolve_decision_transport() is DecisionTransport.OFF

    monkeypatch.setattr(settings, "jev_provider", "")
    assert resolve_decision_transport() is DecisionTransport.OFF


def test_api_key_alone_never_enables_jev(monkeypatch) -> None:
    # 開発者は複数プロバイダーのキーを .env に持つ。キーの存在は利用の根拠にしない
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "typesafe_api_key", "ts-key")
    monkeypatch.setattr(settings, "jev_provider", "off")
    assert jev_judge_enabled() is False

    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    assert jev_judge_enabled() is True

    # 明示的に選んでも、その経路のキーが無ければ使わない
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    assert jev_judge_enabled() is False

    monkeypatch.setattr(settings, "jev_provider", "typesafe")
    assert jev_judge_enabled() is True
    monkeypatch.setattr(settings, "typesafe_api_key", "")
    assert jev_judge_enabled() is False


def test_live_targets_default_to_shadow(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_live_targets", "")
    assert all(not jev_live(target) for target in JEV_TARGETS)

    monkeypatch.setattr(settings, "jev_live_targets", "all")
    assert all(jev_live(target) for target in JEV_TARGETS)

    monkeypatch.setattr(settings, "jev_live_targets", " congruence , tags ")
    assert jev_live("congruence") is True
    assert jev_live("tags") is True
    assert jev_live("chat_lookup") is False


def test_cost_tracking_includes_the_judge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "image_provider", "novelai")
    monkeypatch.setattr(settings, "feeling_provider", "novelai")
    monkeypatch.setattr(settings, "image_description_provider", "selfhost")
    monkeypatch.setattr(settings, "jev_provider", "off")
    assert cost_tracking_enabled() is False

    # 生成はすべて NovelAI/selfhost でも、判定が OpenRouter なら課金が発生する
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    assert cost_tracking_enabled() is True

    monkeypatch.setattr(settings, "jev_provider", "off")
    monkeypatch.setattr(settings, "feeling_provider", "openrouter")
    assert cost_tracking_enabled() is True
