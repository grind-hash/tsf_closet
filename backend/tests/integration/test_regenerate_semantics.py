"""Integration tests for regenerate semantics (spec 004 T018, US2).

「再生成 = 最新履歴削除 + 同じ指示で再アクション」のセマンティクスを検証する。
N 回繰り返しても累積 delta が最終 1 回分のみになることを確認 (SC-002)。
"""

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


async def _seed(factory, *, session_id: str, stats: tuple[int, int, int]) -> None:
    async with factory() as db:
        db.add(User(id="u-regen"))
        db.add(
            SessionORM(
                id=session_id,
                user_id="u-regen",
                current_image_path="img/start.png",
                character_id="c-regen",
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


async def _read_stats(factory, session_id: str) -> tuple[int, int, int]:
    async with factory() as db:
        row = (
            (
                await db.execute(
                    select(SessionStatsORM).where(
                        SessionStatsORM.session_id == session_id
                    )
                )
            )
            .scalars()
            .first()
        )
    return (row.bloom, row.shame, row.adaptation)


async def _apply_action(
    factory, *, session_id: str, history_id: str, deltas: tuple[int, int, int]
) -> None:
    """1 回のアクションをシミュレート: history 行追加 → stats 更新 → change_log 追加."""
    async with factory() as db:
        prev_stats = (
            (
                await db.execute(
                    select(SessionStatsORM).where(
                        SessionStatsORM.session_id == session_id
                    )
                )
            )
            .scalars()
            .first()
        )
        prev_bloom = prev_stats.bloom
        prev_shame = prev_stats.shame
        prev_adapt = prev_stats.adaptation
        new_bloom = max(0, min(100, prev_bloom + deltas[0]))
        new_shame = max(0, min(100, prev_shame + deltas[1]))
        new_adapt = max(-50, min(50, prev_adapt + deltas[2]))

        db.add(
            HistoryORM(
                id=history_id,
                session_id=session_id,
                instruction="regen",
                image_path=f"img/{history_id}.png",
            )
        )
        prev_stats.bloom = new_bloom
        prev_stats.shame = new_shame
        prev_stats.adaptation = new_adapt
        await db.flush()
        await insert_change_logs(
            db,
            session_id=session_id,
            history_id=history_id,
            stat_changes=[
                ("bloom", new_bloom - prev_bloom, prev_bloom, new_bloom),
                ("shame", new_shame - prev_shame, prev_shame, new_shame),
                ("adaptation", new_adapt - prev_adapt, prev_adapt, new_adapt),
            ],
            reason="dress_up",
        )
        await db.commit()


@pytest.mark.asyncio
async def test_delete_and_reaction_yields_single_delta(
    isolated_db, tmp_path: Path, monkeypatch
):
    """1 アクション → 削除 → 同指示で再アクション → 結果は「最後の 1 件分のみ」."""
    store = await _setup_store(tmp_path, monkeypatch)
    factory = isolated_db.async_factory

    sid = "regen-A"
    await _seed(factory, session_id=sid, stats=(10, 50, 0))
    deltas = (5, -3, 1)

    await _apply_action(factory, session_id=sid, history_id="h1", deltas=deltas)
    assert await _read_stats(factory, sid) == (15, 47, 1)

    result = await store.delete_latest_history(sid)
    assert result is not None
    assert await _read_stats(factory, sid) == (10, 50, 0)

    await _apply_action(factory, session_id=sid, history_id="h2", deltas=deltas)
    assert await _read_stats(factory, sid) == (15, 47, 1)


@pytest.mark.asyncio
async def test_five_regen_cycles_remain_single_delta(
    isolated_db, tmp_path: Path, monkeypatch
):
    """SC-002: 5 サイクル繰り返しても最終 stats は 1 回分のみ."""
    store = await _setup_store(tmp_path, monkeypatch)
    factory = isolated_db.async_factory

    sid = "regen-B"
    await _seed(factory, session_id=sid, stats=(10, 50, 0))
    deltas = (5, -3, 1)

    for i in range(5):
        await _apply_action(factory, session_id=sid, history_id=f"h{i}", deltas=deltas)
        result = await store.delete_latest_history(sid)
        assert result is not None

    # 全削除後は初期値
    assert await _read_stats(factory, sid) == (10, 50, 0)

    # 最終 1 回再適用 → 1 件分のみ反映
    await _apply_action(factory, session_id=sid, history_id="final", deltas=deltas)
    assert await _read_stats(factory, sid) == (15, 47, 1)


@pytest.mark.asyncio
async def test_action_delete_reaction_delete_returns_to_initial(
    isolated_db, tmp_path: Path, monkeypatch
):
    """アクション → 削除 → 再アクション → 削除 → 初期値に戻る (二重 revert なし)."""
    store = await _setup_store(tmp_path, monkeypatch)
    factory = isolated_db.async_factory

    sid = "regen-C"
    await _seed(factory, session_id=sid, stats=(20, 40, 5))
    deltas = (3, 2, -1)

    await _apply_action(factory, session_id=sid, history_id="h1", deltas=deltas)
    await store.delete_latest_history(sid)
    await _apply_action(factory, session_id=sid, history_id="h2", deltas=deltas)
    await store.delete_latest_history(sid)

    assert await _read_stats(factory, sid) == (20, 40, 5)
