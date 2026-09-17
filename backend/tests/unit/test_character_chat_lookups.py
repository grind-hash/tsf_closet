"""キャラチャットの調べ物(DB 参照)の整形。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from gateway.consts.character_chat import PAST_PLAY_LOOKUP_KINDS
from gateway.databases.models import Conversation as ConversationORM
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import PlaySummary as PlaySummaryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionStats as SessionStatsORM
from gateway.databases.models import TransformationTag as TransformationTagORM
from gateway.databases.models import User
from gateway.services import character_chat_lookups as lookups
from gateway.services.character_chat_models import CharacterChatPlan
from gateway.services.real_world_lookup import SearchInfo, SearchSource, WeatherInfo
from gateway.services.session import DEFAULT_USER_ID


async def _seed(factory) -> None:
    async with factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.add(
            SessionORM(
                id="s1",
                user_id=DEFAULT_USER_ID,
                current_image_path="a.png",
                character_id="char1",
                transformation_count=2,
                updated_at=datetime(2026, 9, 1, 12),
            )
        )
        db.add(
            SessionORM(
                id="s2",
                user_id=DEFAULT_USER_ID,
                current_image_path="b.png",
                character_id="char2",
                transformation_count=1,
                updated_at=datetime(2026, 9, 3, 12),
            )
        )
        db.add(
            HistoryORM(
                id="h1",
                session_id="s1",
                instruction="メイド服に着替える",
                image_path="a.png",
                instruction_type="dress_up",
                created_at=datetime(2026, 9, 1, 10),
            )
        )
        db.add(
            HistoryORM(
                id="h2",
                session_id="s2",
                instruction="猫耳を生やす",
                image_path="b.png",
                instruction_type="reality_alter",
                created_at=datetime(2026, 9, 3, 10),
            )
        )
        db.add(TransformationTagORM(history_id="h1", costume_category="maid"))
        db.add(
            ConversationORM(
                id="c1",
                session_id="s2",
                role="user",
                content="猫耳は似合う？",
                created_at=datetime(2026, 9, 3, 11),
            )
        )
        db.add(SessionStatsORM(session_id="s1", bloom=30, shame=60, adaptation=10))
        db.add(
            PlaySummaryORM(
                session_id="s1",
                title="メイドの一日",
                summary="給仕をした",
                timeline_json="[]",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_session_candidates_and_recent_sessions(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    candidates = await lookups.session_candidates("ja")
    assert [item["id"] for item in candidates] == ["s2", "s1"]
    assert "星野エミ" in candidates[0]["label"]
    recent = await lookups.render_recent_sessions(5, "ja")
    text = recent.text
    assert "セッション総数: 2" in text
    assert "[s1] 2026-09-01 水瀬ユウヤ、変身2回、称号「メイドの一日」" in text
    assert "最後の指示: 猫耳を生やす" in text
    assert recent.session_ids == ("s2", "s1")


@pytest.mark.asyncio
async def test_session_detail_and_search(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    detail = await lookups.render_session_detail("s1", 5, "ja")
    assert "水瀬ユウヤ" in detail.text
    assert "揺らぎ・葛藤" in detail.text
    assert "要約: 給仕をした" in detail.text
    assert "[着替え] メイド服に着替える" in detail.text
    assert detail.session_ids == ("s1",)
    missing = await lookups.render_session_detail("nope", 5, "ja")
    assert missing.text == "(記録はありません)"
    assert missing.session_ids == ()

    found = await lookups.render_search_sessions("猫耳", 5, "ja")
    assert found.text.startswith("「猫耳」に一致するセッション(新しい順):")
    assert "[s2]" in found.text
    assert "猫耳は似合う？" in found.text
    assert found.session_ids == ("s2",)
    none = await lookups.render_search_sessions("存在しない", 5, "ja")
    assert none.text == "「存在しない」に一致する記録はありません。"
    assert none.session_ids == ()
    empty = await lookups.render_search_sessions("", 5, "ja")
    assert empty.text == "(取得できませんでした)"


@pytest.mark.asyncio
async def test_session_detail_self_mode_hides_stage(isolated_db, monkeypatch) -> None:
    # 自分自身モードは stats を追跡しないので、開花度由来の段階を出さない
    await _seed(isolated_db.async_factory)
    async with isolated_db.async_factory() as db:
        session = await db.get(SessionORM, "s1")
        session.self_mode = True
        await db.commit()
    monkeypatch.setattr(
        lookups.session_store,
        "get_self_profile",
        AsyncMock(return_value={"display_name": "自分", "pronoun": "俺"}),
    )
    detail = await lookups.render_session_detail("s1", 5, "ja")
    assert "自分 (自分自身モード)" in detail.text
    assert (
        "変身2回(自分自身モード: パラメータ・心理段階は追跡していません)" in detail.text
    )
    assert "開花" not in detail.text
    assert "揺らぎ・葛藤" not in detail.text
    english = await lookups.render_session_detail("s1", 5, "en")
    assert "self mode: no parameters or mental stage are tracked" in english.text
    assert "bloom" not in english.text


@pytest.mark.asyncio
async def test_search_sessions_strips_quotes_and_combines_terms(isolated_db) -> None:
    """判定 LLM が引用符ごと返した検索語や複数語でも空振りしない。"""
    await _seed(isolated_db.async_factory)
    quoted = await lookups.render_search_sessions('"猫耳"', 5, "ja")
    assert quoted.text.startswith("「猫耳」に一致するセッション(新しい順):")
    assert quoted.session_ids == ("s2",)
    bracketed = await lookups.render_search_sessions("「猫耳」", 5, "ja")
    assert bracketed.session_ids == ("s2",)

    # 全語一致(AND): s2 は指示「猫耳を生やす」と会話「猫耳は似合う？」の両方を持つ
    both = await lookups.render_search_sessions("猫耳 似合う", 5, "ja")
    assert both.text.startswith(
        "「猫耳」「似合う」のすべてに一致するセッション(新しい順):"
    )
    assert both.session_ids == ("s2",)

    # 全語一致が無ければ、いずれかの語に一致するものへ広げる(OR)
    either = await lookups.render_search_sessions("メイド 猫耳", 5, "ja")
    assert either.text.startswith(
        "「メイド」「猫耳」のすべてに一致する記録はありません。"
        "いずれかに一致するセッション(新しい順):"
    )
    assert either.session_ids == ("s2", "s1")
    assert "[s1] 2026-09-01 水瀬ユウヤ: メイド服に着替える" in either.text

    partial = await lookups.render_search_sessions("メイド 存在しない", 5, "ja")
    assert partial.session_ids == ("s1",)
    nothing = await lookups.render_search_sessions("無い 存在しない", 5, "ja")
    assert nothing.text == "「無い」「存在しない」に一致する記録はありません。"

    english = await lookups.render_search_sessions("メイド 猫耳", 5, "en")
    assert english.text.startswith(
        'No session matches all of "メイド", "猫耳"; sessions matching any of them '
        "(newest first):"
    )


@pytest.mark.asyncio
async def test_tendencies_counts(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    text = (await lookups.render_tendencies("ja")).text
    assert "セッション総数: 2" in text
    assert "着替え 1" in text
    assert "現実改変 1" in text
    assert "maid 1" in text


@pytest.mark.asyncio
async def test_run_lookups_survives_failures(isolated_db, monkeypatch) -> None:
    await _seed(isolated_db.async_factory)

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(lookups, "render_recent_adventures", broken)
    plan = CharacterChatPlan.model_validate(
        {"lookups": [{"kind": "recent_adventures"}, {"kind": "tendencies"}]}
    )
    run = await lookups.run_lookups(plan, language="ja")
    text, details = run.text, run.details
    assert run.real_world_text == ""
    assert [item["kind"] for item in details] == ["recent_adventures", "tendencies"]
    assert "## 最近のTSFシナリオ\n(取得できませんでした)" in text
    assert "## 傾向・統計" in text
    # 明細はプロンプトに載せた本文と同じものを引用表示用に持つ
    assert details[0] == {
        "kind": "recent_adventures",
        "query": None,
        "session_id": None,
        "text": "(取得できませんでした)",
        "session_ids": [],
    }
    assert details[1]["text"].startswith("セッション総数: 2")
    assert details[1]["session_ids"] == []


@pytest.mark.asyncio
async def test_run_lookups_details_carry_query_and_session_ids(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    plan = CharacterChatPlan.model_validate(
        {
            "lookups": [
                {"kind": "search_sessions", "query": '"猫耳"'},
                {"kind": "session_detail", "session_id": "s1"},
                {"kind": "recent_sessions", "limit": 1},
            ]
        }
    )
    run = await lookups.run_lookups(plan, language="ja")
    text, details = run.text, run.details
    assert "## 検索結果\n「猫耳」に一致するセッション(新しい順):" in text
    assert details[0]["query"] == "猫耳"
    assert details[0]["session_ids"] == ["s2"]
    assert details[1]["session_id"] == "s1"
    assert details[1]["session_ids"] == ["s1"]
    assert details[2]["session_ids"] == ["s2"]
    for item in details:
        assert f"## {lookups._TITLES[item['kind']]['ja']}\n{item['text']}" in text


# ---------------------------------------------------------------------------
# 現実世界の調べ物(Web 検索・天気)
# ---------------------------------------------------------------------------

_REAL_WORLD_ALLOWED = (*PAST_PLAY_LOOKUP_KINDS, "web_search", "weather")


def _real_world_plan(items: list[dict]) -> CharacterChatPlan:
    return CharacterChatPlan.model_validate(
        {"lookups": items}, context={"allowed_kinds": _REAL_WORLD_ALLOWED}
    )


@pytest.mark.asyncio
async def test_run_lookups_skips_real_world_kinds_by_default(monkeypatch) -> None:
    """許可されていなければ、計画に入っていても外部 API を呼ばない。"""
    search = AsyncMock()
    weather = AsyncMock()
    monkeypatch.setattr(lookups.real_world_lookup, "tavily_search", search)
    monkeypatch.setattr(lookups.real_world_lookup, "fetch_weather", weather)
    plan = _real_world_plan([{"kind": "web_search", "query": "q"}, {"kind": "weather"}])
    assert [item.kind for item in plan.lookups] == ["web_search", "weather"]

    run = await lookups.run_lookups(plan, language="ja")

    search.assert_not_awaited()
    weather.assert_not_awaited()
    assert run.details == []
    assert run.text == ""
    assert run.real_world_text == ""


@pytest.mark.asyncio
async def test_run_lookups_web_search_goes_to_real_world_text_with_sources(
    isolated_db, monkeypatch
) -> None:
    await _seed(isolated_db.async_factory)
    info = SearchInfo(
        query="秋 ファッション 2026",
        answer="要約です",
        sources=[
            SearchSource(title="記事A", url="https://example.com/a", snippet="本文A"),
            SearchSource(title="記事B", url="", snippet="本文B"),
        ],
    )
    search = AsyncMock(return_value=info)
    monkeypatch.setattr(lookups.real_world_lookup, "tavily_search", search)
    plan = _real_world_plan(
        [
            {"kind": "tendencies"},
            {"kind": "web_search", "query": "秋 ファッション 2026"},
        ]
    )

    run = await lookups.run_lookups(
        plan, language="ja", allowed_kinds=_REAL_WORLD_ALLOWED
    )

    search.assert_awaited_once_with("秋 ファッション 2026", language="ja")
    assert run.real_world_text.startswith(
        "## Web検索「秋 ファッション 2026」\n要約: 要約です"
    )
    assert "- 記事A: 本文A" in run.real_world_text
    assert "https://" not in run.real_world_text
    # 過去プレイの枠には混ぜない
    assert "## 傾向・統計" in run.text
    assert "Web検索" not in run.text
    tendencies, web = run.details
    assert "sources" not in tendencies
    assert web["kind"] == "web_search"
    assert web["query"] == "秋 ファッション 2026"
    # 出典リンクは http(s) の URL を持つものだけ
    assert web["sources"] == [{"title": "記事A", "url": "https://example.com/a"}]


@pytest.mark.asyncio
async def test_run_lookups_weather_renders_current_conditions(monkeypatch) -> None:
    weather = AsyncMock(
        return_value=WeatherInfo(
            location="東京",
            location_raw="Tokyo",
            weather_code=1,
            label_ja="晴れ",
            label_en="Mainly clear",
            temperature_c=29.4,
            humidity_pct=60,
        )
    )
    monkeypatch.setattr(lookups.real_world_lookup, "fetch_weather", weather)
    # 天気の検索語は使わない
    plan = _real_world_plan([{"kind": "weather", "query": "東京"}])

    run = await lookups.run_lookups(
        plan, language="ja", allowed_kinds=_REAL_WORLD_ALLOWED
    )

    assert run.real_world_text == "## 天気\n東京: 晴れ 29.4°C 湿度60%"
    assert run.details == [
        {
            "kind": "weather",
            "query": None,
            "session_id": None,
            "text": "東京: 晴れ 29.4°C 湿度60%",
            "session_ids": [],
        }
    ]


@pytest.mark.asyncio
async def test_run_lookups_real_world_failure_is_non_fatal(monkeypatch) -> None:
    monkeypatch.setattr(
        lookups.real_world_lookup,
        "tavily_search",
        AsyncMock(side_effect=RuntimeError("timeout")),
    )
    plan = _real_world_plan([{"kind": "web_search", "query": "q"}])

    run = await lookups.run_lookups(
        plan, language="en", allowed_kinds=_REAL_WORLD_ALLOWED
    )

    assert run.real_world_text == '## Web search: "q"\n(could not be retrieved)'
    assert run.details[0]["sources"] == []


def test_available_real_world_kinds_requires_toggle_and_config(monkeypatch) -> None:
    settings = lookups.real_world_lookup.settings
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(settings, "weather_location", "")
    assert lookups.available_real_world_kinds(
        use_web_search=True, use_weather=True
    ) == {"web_search"}
    assert (
        lookups.available_real_world_kinds(use_web_search=False, use_weather=True)
        == frozenset()
    )
    monkeypatch.setattr(settings, "weather_location", "Tokyo")
    assert lookups.available_real_world_kinds(
        use_web_search=True, use_weather=True
    ) == {"web_search", "weather"}


_POLICY_REFUSED_JA = (
    "(検索サービス Tavily の利用規約に反するおそれがあるため、検索しませんでした)"
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        # 判定 LLM が見送りの印を付けた
        {"kind": "web_search", "query": "グラビア 撮影会 2026", "refused": True},
        # 印が無くても、検索語が明白な性的語に当たれば送らない
        {"kind": "web_search", "query": "AV女優 人気 2026"},
    ],
    ids=["planner_refused", "policy_terms"],
)
async def test_run_lookups_refuses_web_search_under_search_policy(
    monkeypatch, item: dict
) -> None:
    search = AsyncMock()
    monkeypatch.setattr(lookups.real_world_lookup, "tavily_search", search)
    plan = _real_world_plan([item])

    run = await lookups.run_lookups(
        plan, language="ja", allowed_kinds=_REAL_WORLD_ALLOWED
    )

    search.assert_not_awaited()
    assert run.web_search_refused is True
    assert run.real_world_text == ""
    # 送らなかった検索語と理由は引用表示のために残す
    assert run.details == [
        {
            "kind": "web_search",
            "query": item["query"],
            "session_id": None,
            "text": _POLICY_REFUSED_JA,
            "session_ids": [],
            "sources": [],
            "refused": "search_policy",
        }
    ]


def test_is_policy_refused_ignores_ordinary_lookups() -> None:
    plan = _real_world_plan(
        [{"kind": "web_search", "query": "秋 ファッション 2026"}, {"kind": "weather"}]
    )
    assert [lookups.is_policy_refused(item) for item in plan.lookups] == [
        False,
        False,
    ]


@pytest.mark.asyncio
async def test_run_lookups_refuses_when_the_message_asks_for_explicit_content(
    monkeypatch,
) -> None:
    """判定 LLM が検索語を当たり障りのない形に言い換えても、元の発言で止める。"""
    search = AsyncMock()
    monkeypatch.setattr(lookups.real_world_lookup, "tavily_search", search)
    plan = _real_world_plan([{"kind": "web_search", "query": "人気 作品 新作 2026"}])
    assert not lookups.is_policy_refused(plan.lookups[0])

    run = await lookups.run_lookups(
        plan,
        language="ja",
        allowed_kinds=_REAL_WORLD_ALLOWED,
        message="最新のAVのおすすめある？",
    )

    search.assert_not_awaited()
    assert run.web_search_refused is True
    assert run.details[0]["refused"] == "search_policy"
    assert run.details[0]["query"] == "人気 作品 新作 2026"
