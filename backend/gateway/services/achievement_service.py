from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from ..databases.base import sync_session_factory
from ..databases.models import (
    AchievementCount,
    History,
    Session,
    SessionStats,
    UserAchievement,
)

GLOBAL_USER_ID = "global_user"


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
                "bloom": latest_stats.bloom if latest_stats else 0,
                "shame": latest_stats.shame if latest_stats else 50,
                "adaptation": latest_stats.adaptation if latest_stats else 0,
                "has_gender_change": (counts.gender_change_count if counts else 0) > 0,
            }

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
