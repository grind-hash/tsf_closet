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
    text = await lookups.render_recent_sessions(5, "ja")
    assert "セッション総数: 2" in text
    assert "[s1] 2026-09-01 水瀬ユウヤ、変身2回、称号「メイドの一日」" in text
    assert "最後の指示: 猫耳を生やす" in text


@pytest.mark.asyncio
async def test_session_detail_and_search(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    detail = await lookups.render_session_detail("s1", 5, "ja")
    assert "水瀬ユウヤ" in detail
    assert "揺らぎ・葛藤" in detail
    assert "要約: 給仕をした" in detail
    assert "[着替え] メイド服に着替える" in detail
    assert await lookups.render_session_detail("nope", 5, "ja") == "(記録はありません)"

    found = await lookups.render_search_sessions("猫耳", 5, "ja")
    assert "[s2]" in found
    assert "猫耳は似合う？" in found
    assert "一致する記録はありません" in await lookups.render_search_sessions(
        "存在しない", 5, "ja"
    )
    assert await lookups.render_search_sessions("", 5, "ja") == "(取得できませんでした)"


@pytest.mark.asyncio
async def test_tendencies_counts(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    text = await lookups.render_tendencies("ja")
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
    text, kinds = await lookups.run_lookups(plan, language="ja")
    assert kinds == ["recent_adventures", "tendencies"]
    assert "## 最近のTSFシナリオ\n(取得できませんでした)" in text
    assert "## 傾向・統計" in text
