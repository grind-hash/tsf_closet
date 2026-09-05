"""Integration tests for history-revert via SessionStore (spec 004 T012)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from gateway.databases.models import (
    History as HistoryORM,
)
from gateway.databases.models import (
    Session as SessionORM,
)
from gateway.databases.models import (
    SessionStats as SessionStatsORM,
)
from gateway.databases.models import (
    User,
)
from gateway.databases.parameter_change_log_repo import insert_change_logs
from gateway.services.session import DatabaseSessionStore


async def _setup_store(tmp_path: Path, monkeypatch) -> DatabaseSessionStore:
    # DB は isolated_db fixture が差し替え済み。ここでは画像ディレクトリだけ用意する
    module = sys.modules["gateway.services.session"]

    history_images_dir = tmp_path / "history_images"
    history_images_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(module.settings, "history_images_dir", history_images_dir)

    return DatabaseSessionStore(history_images_dir=history_images_dir)


async def _seed_session_with_history(
    factory_module,
    *,
    session_id: str,
    history_specs: list[tuple[str, int]],
    stats: tuple[int, int, int],
) -> None:
    """Seed user, session, history rows and session_stats.

    history_specs: list of (history_id, ordinal) pairs.
    stats: (bloom, shame, adaptation) initial cumulative values.
    """
    factory = factory_module.async_session_factory
    async with factory() as db:
        db.add(User(id="user-x"))
        db.add(
            SessionORM(
                id=session_id,
                user_id="user-x",
                current_image_path="img/last.png",
                character_id="char-x",
            )
        )
        for hid, ordinal in history_specs:
            db.add(
                HistoryORM(
                    id=hid,
                    session_id=session_id,
                    instruction=f"step {ordinal}",
                    image_path=f"img/{hid}.png",
                )
            )
        db.add(
            SessionStatsORM(
                session_id=session_id,
                bloom=stats[0],
                shame=stats[1],
                adaptation=stats[2],
                passed_critical_points=json.dumps([]),
                difficulty="normal",
                nsfw_mode=0,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_intermediate_history_delete_reverts_via_clamped_diff(
    isolated_db, tmp_path: Path, monkeypatch
):
    """SC-001: 中央 history 削除で stats が 2 件分の累積に一致する."""
    store = await _setup_store(tmp_path, monkeypatch)
    module = sys.modules["gateway.services.session"]
    factory = isolated_db.async_factory

    sid = "sess-A"
    # h1: +5 bloom, -3 shame, +1 adapt -> (15, 47, 1)
    # h2: +3 bloom, -2 shame, 0 adapt   -> (18, 45, 1)
    # h3: +2 bloom, +1 shame, +2 adapt  -> (20, 46, 3)
    await _seed_session_with_history(
        module,
        session_id=sid,
        history_specs=[("h1", 1), ("h2", 2), ("h3", 3)],
        stats=(20, 46, 3),
    )
    async with factory() as db:
        await insert_change_logs(
            db,
            session_id=sid,
            history_id="h1",
            stat_changes=[
                ("bloom", 5, 10, 15),
                ("shame", -3, 50, 47),
                ("adaptation", 1, 0, 1),
            ],
            reason="action",
        )
        await insert_change_logs(
            db,
            session_id=sid,
            history_id="h2",
            stat_changes=[
                ("bloom", 3, 15, 18),
                ("shame", -2, 47, 45),
            ],
            reason="action",
        )
        await insert_change_logs(
            db,
            session_id=sid,
            history_id="h3",
            stat_changes=[
                ("bloom", 2, 18, 20),
                ("shame", 1, 45, 46),
                ("adaptation", 2, 1, 3),
            ],
            reason="action",
        )
        await db.commit()

    result = await store.delete_history_entry(session_id=sid, history_id="h2")
    assert result is not None
    assert result["deleted_history_id"] == "h2"
    assert "parameter_reverts" in result
    revert_map = {r["stat_name"]: r for r in result["parameter_reverts"]}
    assert revert_map["bloom"]["new_value"] == 17  # 20 - 3
    assert revert_map["shame"]["new_value"] == 48  # 46 - (-2)

    async with factory() as db:
        row = (
            (
                await db.execute(
                    select(SessionStatsORM).where(SessionStatsORM.session_id == sid)
                )
            )
            .scalars()
            .first()
        )
    # 2 件分累積: 初期(10,50,0) + h1(+5,-3,+1) + h3(+2,+1,+2) = (17, 48, 3)
    assert row.bloom == 17
    assert row.shame == 48
    assert row.adaptation == 3


@pytest.mark.asyncio
async def test_latest_history_delete_restores_prev_value_directly(
    isolated_db, tmp_path: Path, monkeypatch
):
    """最新 history 削除で stats が delta 分巻き戻る (prev_value 直接代入)."""
    store = await _setup_store(tmp_path, monkeypatch)
    module = sys.modules["gateway.services.session"]
    factory = isolated_db.async_factory

    sid = "sess-B"
    await _seed_session_with_history(
        module,
        session_id=sid,
        history_specs=[("h1", 1)],
        stats=(15, 47, 1),
    )
    async with factory() as db:
        await insert_change_logs(
            db,
            session_id=sid,
            history_id="h1",
            stat_changes=[
                ("bloom", 5, 10, 15),
                ("shame", -3, 50, 47),
                ("adaptation", 1, 0, 1),
            ],
            reason="dress_up",
        )
        await db.commit()

    result = await store.delete_latest_history(sid)
    assert result is not None
    assert "parameter_reverts" in result
    revert_map = {r["stat_name"]: r for r in result["parameter_reverts"]}
    assert revert_map["bloom"]["new_value"] == 10
    assert revert_map["shame"]["new_value"] == 50
    assert revert_map["adaptation"]["new_value"] == 0

    async with factory() as db:
        row = (
            (
                await db.execute(
                    select(SessionStatsORM).where(SessionStatsORM.session_id == sid)
                )
            )
            .scalars()
            .first()
        )
    assert (row.bloom, row.shame, row.adaptation) == (10, 50, 0)


@pytest.mark.asyncio
async def test_history_delete_without_change_log_does_not_break(
    isolated_db, tmp_path: Path, monkeypatch
):
    """change_log が無い既存 history を削除しても 500 にならず stats 据置 (FR-004)."""
    store = await _setup_store(tmp_path, monkeypatch)
    module = sys.modules["gateway.services.session"]
    factory = isolated_db.async_factory

    sid = "sess-C"
    await _seed_session_with_history(
        module,
        session_id=sid,
        history_specs=[("h_old", 1)],
        stats=(40, 30, 5),
    )

    result = await store.delete_history_entry(session_id=sid, history_id="h_old")
    assert result is not None
    assert "parameter_reverts" not in result  # FR-012 後方互換: 空ならキー省略

    async with factory() as db:
        row = (
            (
                await db.execute(
                    select(SessionStatsORM).where(SessionStatsORM.session_id == sid)
                )
            )
            .scalars()
            .first()
        )
    assert (row.bloom, row.shame, row.adaptation) == (40, 30, 5)
