"""キャラチャットの調べ物(DB 参照)の整形。"""

from __future__ import annotations

from datetime import datetime

import pytest

from gateway.databases.models import Conversation as ConversationORM
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import PlaySummary as PlaySummaryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionStats as SessionStatsORM
from gateway.databases.models import TransformationTag as TransformationTagORM
from gateway.databases.models import User
from gateway.services import character_chat_lookups as lookups
from gateway.services.character_chat_models import CharacterChatPlan
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
    text, details = await lookups.run_lookups(plan, language="ja")
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
    text, details = await lookups.run_lookups(plan, language="ja")
    assert "## 検索結果\n「猫耳」に一致するセッション(新しい順):" in text
    assert details[0]["query"] == "猫耳"
    assert details[0]["session_ids"] == ["s2"]
    assert details[1]["session_id"] == "s1"
    assert details[1]["session_ids"] == ["s1"]
    assert details[2]["session_ids"] == ["s2"]
    for item in details:
        assert f"## {lookups._TITLES[item['kind']]['ja']}\n{item['text']}" in text
