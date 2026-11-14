"""箱庭の検索条件、資料の受け渡し、失敗時の会話継続を検証する。"""

import json
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services import hakoniwa_generation as generation
from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_web_search as web
from gateway.services import real_world_lookup as real
from gateway.services.cost_tracker import begin_cost_tracking
from gateway.settings.config import settings


@pytest.fixture
def state():
    state = logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("ren")]
    )
    state["web_search_enabled"] = True
    return state


@pytest.fixture(autouse=True)
def search_stub(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    search = AsyncMock(
        return_value=real.SearchInfo(
            query="科学 最新",
            answer="新しい望遠鏡が公開された。",
            sources=[
                real.SearchSource(
                    "科学の記事", "https://example.com/news", "観測技術", 0.9
                )
            ],
        )
    )
    monkeypatch.setattr(real, "tavily_search", search)
    return search


async def test_no_key_skips_planner_and_search(state, monkeypatch, search_stub):
    monkeypatch.setattr(settings, "tavily_api_key", "")
    generate = AsyncMock()
    assert await web.lookup(state, tuple(state["residents"]), "ja", generate) is None
    generate.assert_not_awaited()
    search_stub.assert_not_awaited()


@pytest.mark.parametrize("legacy", [False, True])
async def test_disabled_or_old_world_skips_planner_and_search(
    state, search_stub, legacy
):
    if legacy:
        state.pop("web_search_enabled")
    else:
        state["web_search_enabled"] = False
    generate = AsyncMock()
    assert await web.lookup(state, tuple(state["residents"]), "ja", generate) is None
    generate.assert_not_awaited()
    search_stub.assert_not_awaited()
    assert (
        web.choose_news_index(
            state, [tuple(state["residents"])], {}, {}, None, random.Random(1)
        )
        is None
    )
    assert logic.normalize_state(state)["web_search_enabled"] is False


@pytest.mark.parametrize("raw", ['{"query": null}', "invalid", RuntimeError("offline")])
async def test_no_query_or_failed_planner_skips_search(state, search_stub, raw):
    generate = (
        AsyncMock(side_effect=raw)
        if isinstance(raw, Exception)
        else AsyncMock(return_value=raw)
    )
    assert (
        await web.lookup(
            state, tuple(state["residents"]), "ja", generate, message="こんにちは"
        )
        is None
    )
    search_stub.assert_not_awaited()


async def test_chat_sends_only_query_and_preserves_follow_up_context(
    state, search_stub
):
    generate = AsyncMock(return_value='{"query": "科学 最新"}')
    result = await web.lookup(
        state,
        (state["residents"][0],),
        "ja",
        generate,
        message="そのニュース、どう思う？",
        history=[{"role": "resident", "text": "望遠鏡のニュースがあったね"}],
    )
    search_stub.assert_awaited_once_with("科学 最新", language="ja")
    context = json.loads(generate.await_args.args[1])
    assert context["latest_message"] == "そのニュース、どう思う？"
    assert context["recent_conversation"][0]["text"].startswith("望遠鏡")
    assert result.metadata["status"] == "used"
    assert result.metadata["sources"][0]["url"] == "https://example.com/news"
    assert "新しい望遠鏡" in result.prompt()
    assert "untrusted" in web.REFERENCE_RULE
    assert "different personal reactions" in result.prompt(daily=True)


@pytest.mark.parametrize(
    "message,query",
    [("ニュースを教えて", "AV女優 人気"), ("AV女優を調べて", "芸能 ニュース")],
)
async def test_disallowed_search_is_not_sent(state, search_stub, message, query):
    generate = AsyncMock(return_value=json.dumps({"query": query}))
    result = await web.lookup(
        state, tuple(state["residents"]), "ja", generate, message=message
    )
    assert result.metadata["status"] == "blocked"
    assert result.metadata["sources"] == []
    search_stub.assert_not_awaited()


@pytest.mark.parametrize("empty", [True, False])
async def test_empty_or_failed_search_does_not_invent_news(state, search_stub, empty):
    if empty:
        search_stub.return_value = real.SearchInfo(
            "科学 最新", "根拠のない要約", [], found=False
        )
    else:
        search_stub.side_effect = RuntimeError("offline")
    result = await web.lookup(
        state,
        tuple(state["residents"]),
        "ja",
        AsyncMock(return_value='{"query":"科学 最新"}'),
    )
    assert result.metadata["status"] == ("no_results" if empty else "failed")
    assert result.metadata["sources"] == []
    assert "Never invent current" in result.prompt()
    assert "根拠のない要約" not in result.prompt()


def test_daily_selects_only_one_eligible_conversation(state, monkeypatch):
    pair = tuple(state["residents"])
    groups = [pair, pair, pair, pair, (pair[0],)]
    assert (
        web.choose_news_index(
            state, groups, {0: "rule"}, {1: {"climax": True}}, 2, random.Random(1)
        )
        == 3
    )
    assert (
        web.choose_news_index(
            state, groups[:3], {0: "rule"}, {1: {"climax": True}}, 2, random.Random(1)
        )
        is None
    )
    monkeypatch.setattr(settings, "tavily_api_key", "")
    assert web.choose_news_index(state, [pair], {}, {}, None, random.Random(1)) is None


async def test_chat_generation_keeps_provider_cost_and_fallback_metadata(
    state, monkeypatch, search_stub
):
    calls = []

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        calls.append((system, user, novelai_model))
        if max_tokens == 250:
            return '{"query":"科学 最新"}'
        assert "新しい望遠鏡" in user
        assert "untrusted external data" in system
        return "望遠鏡の写真、見てみたいな。"

    monkeypatch.setattr(generation, "_generate_text", fake)
    result = await generation.generate_chat_reply(
        state,
        state["residents"][0],
        [],
        "最近の科学のニュースは？",
        "ja",
        random.Random(1),
        novelai_model="selected-model",
        nsfw=False,
    )
    assert result["source"] == "llm"
    assert result["web_search"]["status"] == "used"
    assert all(call[2] == "selected-model" for call in calls)

    async def broken_reply(system, user, *, novelai_model, max_tokens=1400):
        if max_tokens == 250:
            return '{"query":"科学 最新"}'
        raise RuntimeError("offline")

    monkeypatch.setattr(generation, "_generate_text", broken_reply)
    result = await generation.generate_chat_reply(
        state,
        state["residents"][0],
        [],
        "ニュースは？",
        "ja",
        random.Random(1),
        novelai_model="selected-model",
        nsfw=False,
    )
    assert result["source"] == "template"
    assert result["web_search"]["status"] == "unused"
    assert result["web_search"]["sources"] == []


async def test_daily_event_passes_news_and_preserves_it_through_normalization(
    state, monkeypatch
):
    async def fake(system, user, *, novelai_model, max_tokens=1400):
        if max_tokens == 250:
            return '{"query":"科学 最新"}'
        assert "main subject of this everyday conversation" in user
        return json.dumps(
            {
                "title": "望遠鏡の話",
                "narration": "リビングで二人は新しい望遠鏡の記事を読んでいた。",
                "lines": [
                    {"speaker": "高瀬 葵", "text": "写真が楽しみだね。"},
                    {"speaker": "苑田 蓮", "text": "仕組みが気になるな。"},
                ],
                "mood_delta": {},
                "affinity_delta": 0,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(generation, "_generate_text", fake)
    event = await generation.generate_event(
        state,
        tuple(state["residents"]),
        "ja",
        random.Random(1),
        novelai_model=None,
        nsfw=False,
        use_web_search=True,
    )
    assert event["source"] == "llm"
    updated = logic.normalize_state(logic.apply_event(state, event, random.Random(1)))
    assert updated["events"][-1]["web_search"] == event["web_search"]


async def test_planner_and_reply_costs_use_existing_tracker(state, monkeypatch):
    generate = AsyncMock(
        side_effect=[
            SimpleNamespace(content='{"query":"科学 最新"}', cost_usd=0.01),
            SimpleNamespace(content="写真が楽しみだね。", cost_usd=0.02),
        ]
    )
    monkeypatch.setattr(generation.llm_service, "generate_feeling", generate)
    tracker = begin_cost_tracking()
    await generation.generate_chat_reply(
        state,
        state["residents"][0],
        [],
        "科学のニュースは？",
        "ja",
        random.Random(1),
        novelai_model="selected-model",
        nsfw=False,
    )
    assert tracker.total_usd == pytest.approx(0.03)
    assert all(
        call.kwargs["novelai_model_override"] == "selected-model"
        for call in generate.await_args_list
    )
