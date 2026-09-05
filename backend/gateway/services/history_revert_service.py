"""
履歴の巻き戻し

履歴エントリの削除(画像・会話・パラメータ変更ログの逆適用・直前の状態への復元)と、
分岐時点の SessionStats 再構築。DatabaseSessionStore から切り出した業務ロジックで、
ストアは互換のため同名メソッドからここへ委譲する。

spec 004 (US2): 「再生成」セマンティクスは最新履歴の削除 + 同指示での再アクションで
実現する(専用 API は追加しない)。change_log がある場合は SessionStats も逆適用
(prev_value 直接代入)するため、N 回繰り返しても累積 delta は最終 1 回分のみ。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.base import async_session_factory
from ..databases.models import (
    Conversation as ConversationORM,
)
from ..databases.models import (
    History as HistoryORM,
)
from ..databases.models import (
    Session as SessionORM,
)
from ..databases.models import (
    SessionStats as SessionStatsORM,
)
from ..databases.parameter_change_log_repo import (
    fetch_change_logs_by_history,
    fetch_change_logs_by_session,
)
from ..models import CRITICAL_POINTS, SessionStats
from ..settings.config import settings

if TYPE_CHECKING:
    from .session import DatabaseSessionStore

logger = logging.getLogger(__name__)

# 変身回数にカウントする指示種別(削除時にデクリメントする)
_TRANSFORMATION_INSTRUCTION_TYPES = ("dress_up", "reality_alter")


def stat_clamp(stat_name: str, value: int) -> int:
    """パラメータごとの上下限に丸める。"""
    if stat_name in ("bloom", "shame"):
        return max(0, min(100, value))
    if stat_name == "adaptation":
        return max(-50, min(50, value))
    return value


async def apply_history_revert(
    db_session: AsyncSession,
    *,
    session_id: str,
    history_id: str,
    is_latest: bool,
) -> list[dict]:
    """`history_id` に紐づく change_log を SessionStats に逆適用する.

    Args:
        db_session: 現在のトランザクションで利用する AsyncSession.
        session_id: 対象セッション ID.
        history_id: revert 対象 history.
        is_latest: 削除対象が最新エントリの場合 True (prev_value 直接代入).
            それ以外は ``clamp(current - delta, min, max)`` で近似復元.

    Returns:
        適用済み revert のリスト (``stat_name``/``delta``/``prev_value``/``new_value``).
        change_log が無い場合は空リスト.
    """
    logs = await fetch_change_logs_by_history(db_session, history_id)
    if not logs:
        return []

    stats_row = (
        (
            await db_session.execute(
                select(SessionStatsORM).where(SessionStatsORM.session_id == session_id)
            )
        )
        .scalars()
        .first()
    )
    if stats_row is None:
        return []

    # 同一 stat に複数行が混在する想定は無い (T010 が 1 アクション = 最大 3 行) が、
    # 防御的に最後の値を採用する。
    targets: dict[str, dict] = {}
    for log in logs:
        current = getattr(stats_row, log.stat_name, None)
        if current is None:
            continue
        if is_latest:
            new_value = log.prev_value
        else:
            new_value = stat_clamp(log.stat_name, current - log.delta)
        targets[log.stat_name] = {
            "stat_name": log.stat_name,
            "delta": new_value - current,
            "prev_value": current,
            "new_value": new_value,
        }
        setattr(stats_row, log.stat_name, new_value)

    # bloom が変化した場合、通過済み臨界点リストを再整合する。
    # revert 後の bloom を下回る臨界点はリストから除去する。
    if "bloom" in targets:
        reverted_bloom = targets["bloom"]["new_value"]
        current_points: list[int] = json.loads(stats_row.passed_critical_points)
        updated_points = [p for p in current_points if p <= reverted_bloom]
        stats_row.passed_critical_points = json.dumps(updated_points)

    # SessionStatsORM の変更は同一トランザクションで commit 時に永続化される。
    return list(targets.values())


def _remove_history_files(history_row: HistoryORM) -> None:
    """履歴の画像ファイルと周囲画像ファイルを削除する(失敗は警告のみ)。"""
    if history_row.image_path:
        image_path = Path(history_row.image_path)
        if image_path.exists():
            try:
                os.remove(image_path)
            except OSError as exc:
                logger.warning("Failed to delete image %s: %s", image_path, exc)

    if history_row.surroundings_image_path:
        surr_path = (
            settings.history_images_dir.parent / history_row.surroundings_image_path
        )
        if surr_path.exists():
            try:
                os.remove(surr_path)
            except OSError as exc:
                logger.warning(
                    "Failed to delete surroundings image %s: %s",
                    surr_path,
                    exc,
                )


async def _latest_history_row(
    db_session: AsyncSession, session_id: str
) -> HistoryORM | None:
    stmt = (
        select(HistoryORM)
        .where(HistoryORM.session_id == session_id)
        .order_by(HistoryORM.created_at.desc(), HistoryORM.id.desc())
        .limit(1)
    )
    return (await db_session.execute(stmt)).scalars().first()


async def _remove_history_row(
    db_session: AsyncSession,
    *,
    session_id: str,
    history_row: HistoryORM,
    is_latest: bool,
) -> tuple[list[dict], str, str]:
    """履歴 1 件を関連データごと消し、セッションを直前の履歴へ戻す。

    画像削除 → 関連 conversation 削除 → change_log 逆適用 → history 削除
    (CASCADE で transformation_tags / change_log 行も削除) → current_image_path 復元
    → 変身回数デクリメントの順。commit は呼び出し側が行う。

    Returns:
        (parameter_reverts, restored_image_path, restored_history_id)
    """
    history_id = history_row.id
    deleted_instruction_type = history_row.instruction_type or "dress_up"

    _remove_history_files(history_row)

    await db_session.execute(
        delete(ConversationORM).where(ConversationORM.related_history_id == history_id)
    )

    # spec 004 (T014): change_log があれば SessionStats を逆適用してから history を削除する
    parameter_reverts = await apply_history_revert(
        db_session,
        session_id=session_id,
        history_id=history_id,
        is_latest=is_latest,
    )

    await db_session.execute(delete(HistoryORM).where(HistoryORM.id == history_id))

    # 直前の履歴を取得して current_image_path を復元
    prev = await _latest_history_row(db_session, session_id)
    restored_image_path = prev.image_path if prev else ""
    restored_history_id = prev.id if prev else ""
    if restored_image_path:
        await db_session.execute(
            update(SessionORM)
            .where(SessionORM.id == session_id)
            .values(
                current_image_path=restored_image_path,
                updated_at=datetime.now(),
            )
        )

    # transformation_count のデクリメント (dress_up/reality のみ)
    if deleted_instruction_type in _TRANSFORMATION_INSTRUCTION_TYPES:
        session_row = (
            (
                await db_session.execute(
                    select(SessionORM).where(SessionORM.id == session_id)
                )
            )
            .scalars()
            .first()
        )
        if session_row and session_row.transformation_count > 0:
            await db_session.execute(
                update(SessionORM)
                .where(SessionORM.id == session_id)
                .values(transformation_count=session_row.transformation_count - 1)
            )

    return parameter_reverts, restored_image_path, restored_history_id


async def delete_latest_history(session_id: str) -> dict | None:
    """最新の履歴エントリを削除し、セッションを1つ前の状態に戻す

    Returns:
        削除された履歴情報の辞書、または履歴がない場合None
    """
    async with async_session_factory() as db_session:
        latest = await _latest_history_row(db_session, session_id)
        if latest is None:
            return None

        deleted_id = latest.id
        deleted_instruction = latest.instruction
        deleted_instruction_type = latest.instruction_type or "dress_up"

        (
            parameter_reverts,
            restored_image_path,
            restored_history_id,
        ) = await _remove_history_row(
            db_session,
            session_id=session_id,
            history_row=latest,
            is_latest=True,
        )
        await db_session.commit()

        logger.info(
            "Deleted latest history %s for session %s, restored to %s",
            deleted_id,
            session_id,
            restored_image_path or "(none)",
        )

        response: dict = {
            "deleted_history_id": deleted_id,
            "restored_instruction": deleted_instruction,
            "restored_instruction_type": deleted_instruction_type,
            "current_image_path": restored_image_path,
            "restored_history_id": restored_history_id,
        }
        if parameter_reverts:
            response["parameter_reverts"] = parameter_reverts
        return response


async def delete_history_entry(session_id: str, history_id: str) -> dict | None:
    """指定した history_id の履歴エントリを完全削除する

    History レコード、関連 Conversation レコード、画像ファイルを全て削除する。
    削除後、セッションの current_image_path を直前の履歴に復元する。

    Returns:
        削除情報の辞書、またはエントリが見つからない場合 None
    """
    async with async_session_factory() as db_session:
        # 対象 History がセッションに属するか確認
        history_row = (
            (
                await db_session.execute(
                    select(HistoryORM).where(
                        HistoryORM.id == history_id,
                        HistoryORM.session_id == session_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if history_row is None:
            return None

        # 削除対象が最新エントリなら prev_value 直接代入、それ以外は差分で近似復元
        latest = await _latest_history_row(db_session, session_id)
        is_latest = latest is not None and latest.id == history_id

        (
            parameter_reverts,
            restored_image_path,
            restored_history_id,
        ) = await _remove_history_row(
            db_session,
            session_id=session_id,
            history_row=history_row,
            is_latest=is_latest,
        )
        await db_session.commit()

        logger.info(
            "Deleted history entry %s for session %s, restored to %s",
            history_id,
            session_id,
            restored_image_path or "(none)",
        )

        response: dict = {
            "deleted_history_id": history_id,
            "restored_history_id": restored_history_id,
        }
        if parameter_reverts:
            response["parameter_reverts"] = parameter_reverts
        return response


async def reconstruct_stats_at_history(
    store: DatabaseSessionStore,
    session_id: str,
    history_id: str,
    *,
    difficulty: str = "normal",
    nsfw_mode: bool = False,
) -> SessionStats:
    """parameter_change_log から分岐点時点の stats を再構築する。

    ログが無い場合は難易度初期値にフォールバックする。
    """
    baseline = SessionStats.create_with_difficulty(session_id, difficulty, nsfw_mode)
    source = await store.get_history_by_id(history_id)
    if source is None or source.session_id != session_id:
        return baseline

    history_rows = await store.get_history(session_id)
    allowed_ids: set[str] = set()
    for row in history_rows:
        allowed_ids.add(row.id)
        if row.id == history_id:
            break
    else:
        # 到達できなくても source 自体は含める
        allowed_ids.add(history_id)

    async with async_session_factory() as db_session:
        logs = await fetch_change_logs_by_session(db_session, session_id)

    values = {
        "bloom": baseline.bloom,
        "shame": baseline.shame,
        "adaptation": baseline.adaptation,
    }
    applied = 0
    for log in logs:
        if log.history_id not in allowed_ids:
            continue
        if log.stat_name in values:
            values[log.stat_name] = int(log.new_value)
            applied += 1

    if applied == 0:
        logger.info(
            "No parameter_change_log for session %s up to history %s; "
            "using difficulty defaults",
            session_id,
            history_id,
        )

    bloom = max(0, min(100, values["bloom"]))
    shame = max(0, min(100, values["shame"]))
    adaptation = max(-50, min(50, values["adaptation"]))
    passed = [cp.threshold for cp in CRITICAL_POINTS if bloom >= cp.threshold]

    return SessionStats(
        session_id=session_id,
        bloom=bloom,
        shame=shame,
        adaptation=adaptation,
        passed_critical_points=passed,
        difficulty=difficulty,
        nsfw_mode=nsfw_mode,
    )
