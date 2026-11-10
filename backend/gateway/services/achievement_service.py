from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from ..consts.hakoniwa import HAKONIWA_RULE_MAP
from ..databases.base import sync_session_factory
from ..databases.models import (
    AchievementCount,
    HakoniwaWorld,
    History,
    SalonRun,
    Session,
    SessionRequest,
    SessionStats,
    UserAchievement,
)
from . import hakoniwa_play

GLOBAL_USER_ID = "global_user"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class AchievementService:
    def get_newly_unlocked(
        self,
        achievements: list[Any],
        stats: Any,
        already_unlocked: set[str],
        checker: Callable[[Any, Any], bool],
    ) -> list[Any]:
        newly_unlocked: list[Any] = []
        for achievement in achievements:
            if achievement.id in already_unlocked:
                continue
            if checker(achievement, stats):
                newly_unlocked.append(achievement)
        return newly_unlocked

    def get_achievement_counts(self) -> tuple[int, int, int]:
        with sync_session_factory() as session:
            row = session.get(AchievementCount, "global")
            if row is None:
                return (0, 0, 0)

            return (
                row.crossdress_count,
                row.gender_change_count,
                row.reality_alter_count,
            )

    def update_achievement_counts(self, categories: list[str]) -> None:
        if not categories:
            return

        with sync_session_factory() as session:
            row = session.get(AchievementCount, "global")
            if row is None:
                row = AchievementCount(
                    id="global",
                    crossdress_count=0,
                    gender_change_count=0,
                    reality_alter_count=0,
                    updated_at=datetime.now().isoformat(),
                )
                session.add(row)

            if "CROSS_DRESS" in categories:
                row.crossdress_count += 1
            if "GENDER_CHANGE" in categories:
                row.gender_change_count += 1
            if "REALITY_ALTER" in categories:
                row.reality_alter_count += 1
            row.updated_at = datetime.now().isoformat()

            session.commit()

    def get_global_stats(self) -> dict:
        with sync_session_factory() as session:
            total_transforms = session.scalar(
                select(func.coalesce(func.sum(Session.transformation_count), 0))
            )
            gallery_count = session.scalar(select(func.count(History.id)))

            # Self-mode transformation count
            self_transform_count = session.scalar(
                select(func.coalesce(func.sum(Session.transformation_count), 0)).where(
                    Session.self_mode.is_(True)
                )
            )

            # Self-mode reality_alter count
            self_reality_alter_count = session.scalar(
                select(func.count(History.id))
                .join(Session, Session.id == History.session_id)
                .where(
                    Session.self_mode.is_(True),
                    History.instruction_type == "reality_alter",
                )
            )

            # Self-mode action count
            self_action_count = session.scalar(
                select(func.count(History.id))
                .join(Session, Session.id == History.session_id)
                .where(
                    Session.self_mode.is_(True),
                    History.instruction_type == "action",
                )
            )

            # 依頼モードで達成した依頼の件数
            request_fulfilled_count = session.scalar(
                select(func.count(SessionRequest.session_id)).where(
                    SessionRequest.status == "fulfilled"
                )
            )

            salon_stats = self._salon_season_stats(session)
            hakoniwa_stats = self._hakoniwa_stats(session)

            latest_stats = session.execute(
                select(SessionStats)
                .join(Session, Session.id == SessionStats.session_id)
                .where(Session.is_active.is_(True))
                .order_by(desc(Session.updated_at))
                .limit(1)
            ).scalar_one_or_none()

            counts = session.get(AchievementCount, "global")

            return {
                "transform_count": int(total_transforms or 0),
                "crossdress_count": counts.crossdress_count if counts else 0,
                "reality_alter_count": counts.reality_alter_count if counts else 0,
                "gallery_count": int(gallery_count or 0),
                "self_transform_count": int(self_transform_count or 0),
                "self_reality_alter_count": int(self_reality_alter_count or 0),
                "self_action_count": int(self_action_count or 0),
                "request_fulfilled_count": int(request_fulfilled_count or 0),
                **salon_stats,
                **hakoniwa_stats,
                "bloom": latest_stats.bloom if latest_stats else 0,
                "shame": latest_stats.shame if latest_stats else 50,
                "adaptation": latest_stats.adaptation if latest_stats else 0,
                "has_gender_change": (counts.gender_change_count if counts else 0) > 0,
            }

    @staticmethod
    def _salon_season_stats(session: Any) -> dict[str, int]:
        """決算まで終えた(倒産していない)期の件数・成功・黒字の最大値。

        サロンは決算のあと次の期へ続けられるので、すべてのサロンの期ごとの結果
        (state_json の seasons。以前のサロンは result)を数える。黒字は期ごとの値。
        """
        rows = session.execute(select(SalonRun.state_json)).scalars()
        completed_count = success_count = hard_success_count = 0
        best_profit = 0
        for state_json in rows:
            try:
                state = json.loads(state_json or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(state, dict):
                continue
            seasons = state.get("seasons")
            if not isinstance(seasons, list):
                result = state.get("result")
                seasons = [result] if isinstance(result, dict) else []
            for result in seasons:
                if not isinstance(result, dict) or result.get("outcome") not in (
                    "success",
                    "partial",
                ):
                    continue
                completed_count += 1
                if result.get("outcome") == "success":
                    success_count += 1
                    if state.get("difficulty") == "hard":
                        hard_success_count += 1
                best_profit = max(best_profit, int(result.get("profit") or 0))
        return {
            "salon_completed_count": completed_count,
            "salon_success_count": success_count,
            "salon_hard_success_count": hard_success_count,
            "salon_best_profit": best_profit,
        }

    @staticmethod
    def _hakoniwa_stats(session: Any) -> dict[str, Any]:
        """AI箱庭の観察記録の判定に使う数を、すべての世界の状態から集計する。

        出来事・変身・お気に入りは世界の合計、日数・好感度・違和感は世界ごとの最大。
        有効にした掟・ドレス姿・入れ替わり・違和感の到達点は、世界の observations
        (保存のたびに積む観測の事実)から読む。
        """
        stats: dict[str, Any] = {
            "hakoniwa_max_day": 0,
            "hakoniwa_event_count": 0,
            "hakoniwa_transform_count": 0,
            "hakoniwa_confrontation_count": 0,
            "hakoniwa_favorite_count": 0,
            "hakoniwa_world_count": 0,
            "hakoniwa_max_affinity": 0,
            "hakoniwa_max_dissonance": 0,
            "hakoniwa_all_rules": False,
            "hakoniwa_custom_rule": False,
            "hakoniwa_dress_all": False,
            "hakoniwa_swap": False,
        }
        rules_seen: set[str] = set()
        for state_json in session.execute(select(HakoniwaWorld.state_json)).scalars():
            try:
                state = json.loads(state_json or "{}")
            except (TypeError, ValueError):
                continue
            if not isinstance(state, dict):
                continue
            stats["hakoniwa_world_count"] += 1
            events = [e for e in state.get("events") or [] if isinstance(e, dict)]
            residents = [r for r in state.get("residents") or [] if isinstance(r, dict)]
            # 観測の記録が無い(観察記録より前に保存した)世界も、いまの状態から拾う
            try:
                observed = hakoniwa_play.observe(state)["observations"]
            except Exception:
                observed = state.get("observations") or {}
            stats["hakoniwa_max_day"] = max(
                stats["hakoniwa_max_day"], _as_int(state.get("day"))
            )
            stats["hakoniwa_event_count"] += len(events)
            stats["hakoniwa_transform_count"] += sum(
                1
                for event in events
                if event.get("kind") == "transform" and event.get("change_text")
            )
            stats["hakoniwa_confrontation_count"] += sum(
                1 for event in events if event.get("kind") == "confrontation"
            )
            stats["hakoniwa_favorite_count"] += sum(
                1 for event in events if event.get("favorite")
            )
            for resident in residents:
                for value in (resident.get("affinities") or {}).values():
                    stats["hakoniwa_max_affinity"] = max(
                        stats["hakoniwa_max_affinity"], _as_int(value)
                    )
            stats["hakoniwa_max_dissonance"] = max(
                stats["hakoniwa_max_dissonance"],
                _as_int(observed.get("dissonance_max")),
                _as_int(state.get("dissonance")),
            )
            rules_seen |= {str(item) for item in observed.get("rules_seen") or []}
            stats["hakoniwa_custom_rule"] = stats["hakoniwa_custom_rule"] or bool(
                state.get("custom_rules")
            )
            dress_seen = {str(item) for item in observed.get("dress_seen") or []}
            if residents and all(r.get("id") in dress_seen for r in residents):
                stats["hakoniwa_dress_all"] = True
            stats["hakoniwa_swap"] = stats["hakoniwa_swap"] or bool(
                observed.get("swap_seen")
            )
        stats["hakoniwa_all_rules"] = set(HAKONIWA_RULE_MAP) <= rules_seen
        return stats

    def save_user_achievement(self, achievement_id: str) -> None:
        with sync_session_factory() as session:
            exists = session.execute(
                select(UserAchievement.id).where(
                    UserAchievement.achievement_id == achievement_id
                )
            ).scalar_one_or_none()
            if exists is not None:
                return

            now = datetime.now().isoformat()
            # session_id is intentionally NULL: achievements are managed globally
            # and "global_user" is not a real sessions row, which would violate the
            # user_achievements.session_id foreign key when PRAGMA foreign_keys=ON.
            session.add(
                UserAchievement(
                    id=str(uuid.uuid4()),
                    session_id=None,
                    achievement_id=achievement_id,
                    achieved_at=now,
                    progress=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

    def get_user_achievements(self) -> list[tuple[str, str | None]]:
        with sync_session_factory() as session:
            rows = session.execute(
                select(UserAchievement.achievement_id, UserAchievement.achieved_at)
            ).all()
            return [(row[0], row[1]) for row in rows]


achievement_service = AchievementService()
