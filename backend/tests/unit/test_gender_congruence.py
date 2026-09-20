"""gender_congruence モジュールのユニットテスト。"""

from __future__ import annotations

from gateway.services.gender_congruence import (
    GenderCongruenceResult,
    evaluate_gender_congruence,
    evaluate_gender_congruence_rule,
    is_gender_aware_feeling_mode,
    normalize_feeling_mode,
    parse_congruence_llm_response,
    should_use_congruence_llm,
)
from gateway.settings.config import settings


def test_man_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツに着替えさせる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_plain_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("スーツを着せる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_ladies_suit_is_incongruent() -> None:
    """レディーススーツはスーツ部分一致でも女装扱い。"""
    result = evaluate_gender_congruence_rule("レディーススーツを着せる", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True
    assert "女性向け" in result.reason or "レディース" in result.reason


def test_man_ladies_pajamas_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("レディースパジャマ", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_pajamas_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("パジャマを着せる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_skirt_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("スカートを履かせる", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_maid_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("メイド服に変身", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_lingerie_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("ランジェリーに着替える", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_bunny_suit_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("バニースーツを着せる", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_onepi_abbrev_is_incongruent() -> None:
    """ワンピース略語「ワンピ」も女性寄りとして拾う。"""
    result = evaluate_gender_congruence_rule("タイトミニワンピに着替え", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_woman_mens_suit_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツを着せる", "woman")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_woman_ladies_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("レディーススーツ", "woman")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_woman_dress_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("ドレスに着替える", "woman")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_ambiguous_defaults_to_discomfort() -> None:
    result = evaluate_gender_congruence_rule("不思議な光に包まれる", "man")
    assert result.fit == "ambiguous"
    assert result.should_feel_gender_discomfort is True


def test_normalize_feeling_mode() -> None:
    assert normalize_feeling_mode("legacy") == "legacy"
    assert normalize_feeling_mode("gender_aware") == "gender_aware"
    # 誤保存互換
    assert normalize_feeling_mode("new") == "gender_aware"
    assert normalize_feeling_mode("experimental") == "gender_aware"
    assert normalize_feeling_mode(None) == "legacy"
    assert normalize_feeling_mode("unknown") == "legacy"


def test_is_gender_aware_feeling_mode() -> None:
    assert is_gender_aware_feeling_mode("legacy") is False
    assert is_gender_aware_feeling_mode("gender_aware") is True
    assert is_gender_aware_feeling_mode("new") is True
    assert is_gender_aware_feeling_mode("experimental") is True


def test_should_use_congruence_llm() -> None:
    assert should_use_congruence_llm("legacy", True) is False
    assert should_use_congruence_llm("gender_aware", False) is False
    assert should_use_congruence_llm("gender_aware", True) is True
    assert should_use_congruence_llm("new", True) is True


def test_parse_llm_json() -> None:
    raw = (
        '{"fit":"congruent","discomfort":false,'
        '"body":"original","social":"original","reason":"スーツで自然"}'
    )
    parsed = parse_congruence_llm_response(raw)
    assert parsed is not None
    assert parsed.fit == "congruent"
    assert parsed.should_feel_gender_discomfort is False
    assert parsed.source == "llm"


def test_parse_llm_json_in_code_fence() -> None:
    raw = """```json
{"fit":"incongruent","discomfort":true,"body":"altered","social":"opposite","reason":"女体化残存"}
```"""
    parsed = parse_congruence_llm_response(raw)
    assert parsed is not None
    assert parsed.fit == "incongruent"
    assert parsed.body_state == "altered"
    assert parsed.should_feel_gender_discomfort is True


# ---------------------------------------------------------------------------
# 判定器 (汎用 LLM / Jev) の切り替え
# ---------------------------------------------------------------------------


class _FakeLLMResult:
    def __init__(self, content: str) -> None:
        self.content = content


def _stub_llm(monkeypatch, content: str) -> list[str]:
    """llm_service.generate_feeling を差し替え、呼ばれた回数を数える。"""
    calls: list[str] = []

    async def _generate_feeling(*, system_prompt, user_prompt, **_kwargs):
        calls.append(user_prompt)
        return _FakeLLMResult(content)

    from gateway.services import llm_service as llm_module

    monkeypatch.setattr(
        llm_module.llm_service, "generate_feeling", _generate_feeling, raising=True
    )
    return calls


def _stub_jev(monkeypatch, result) -> list[dict]:
    """gender_congruence_jev.evaluate_with_jev を差し替える。"""
    calls: list[dict] = []

    async def _evaluate_with_jev(**kwargs):
        calls.append(kwargs)
        return result

    from gateway.services import gender_congruence_jev as jev_module

    monkeypatch.setattr(jev_module, "evaluate_with_jev", _evaluate_with_jev)
    return calls


_LLM_JSON = (
    '{"fit":"congruent","discomfort":false,'
    '"body":"original","social":"original","reason":"llm"}'
)


async def test_jev_disabled_by_default_uses_the_existing_llm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "off")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    llm_calls = _stub_llm(monkeypatch, _LLM_JSON)
    jev_calls = _stub_jev(monkeypatch, None)

    result = await evaluate_gender_congruence("パジャマに着替える", "man", use_llm=True)

    assert result.source == "llm"
    assert len(llm_calls) == 1
    assert jev_calls == []


async def test_hard_marker_skips_every_judge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", "all")
    llm_calls = _stub_llm(monkeypatch, _LLM_JSON)
    jev_calls = _stub_jev(monkeypatch, None)

    result = await evaluate_gender_congruence(
        "レディーススーツを着せる", "man", use_llm=True
    )

    assert result.fit == "incongruent"
    assert result.source == "rule"
    assert llm_calls == []
    assert jev_calls == []


async def test_live_target_prefers_jev(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", "congruence")
    llm_calls = _stub_llm(monkeypatch, _LLM_JSON)
    jev_calls = _stub_jev(
        monkeypatch,
        GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            reason="jev: ...",
            source="jev",
        ),
    )

    result = await evaluate_gender_congruence("ジャージを着る", "man", use_llm=True)

    assert result.source == "jev"
    assert len(jev_calls) == 1
    assert llm_calls == []


async def test_live_target_falls_back_to_the_llm_when_jev_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", "congruence")
    llm_calls = _stub_llm(monkeypatch, _LLM_JSON)
    _stub_jev(monkeypatch, None)

    result = await evaluate_gender_congruence("ジャージを着る", "man", use_llm=True)

    assert result.source == "llm"
    assert len(llm_calls) == 1


async def test_shadow_keeps_the_llm_verdict_but_still_calls_jev(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", "")
    llm_calls = _stub_llm(monkeypatch, _LLM_JSON)
    jev_calls = _stub_jev(
        monkeypatch,
        GenderCongruenceResult(
            fit="incongruent",
            should_feel_gender_discomfort=True,
            reason="jev",
            source="jev",
        ),
    )

    result = await evaluate_gender_congruence("ジャージを着る", "man", use_llm=True)

    # 挙動は従来のまま。Jev は比較のためだけに呼ばれる
    assert result.source == "llm"
    assert len(llm_calls) == 1
    assert len(jev_calls) == 1


async def test_under_detection_override_also_applies_to_jev(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", "congruence")
    _stub_llm(monkeypatch, _LLM_JSON)
    # hard marker に当たらないが、ルールでは不適合が確定する指示
    _stub_jev(
        monkeypatch,
        GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            reason="jev said congruent",
            source="jev",
        ),
    )

    rule = evaluate_gender_congruence_rule("メイド服を着せる", "man")
    assert rule.fit == "incongruent"
    assert rule.should_feel_gender_discomfort is True

    from gateway.services.gender_congruence import _apply_under_detection_override

    overridden = _apply_under_detection_override(
        rule,
        GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            reason="jev said congruent",
            source="jev",
        ),
    )
    assert overridden.should_feel_gender_discomfort is True
    assert overridden.source == "fallback"
