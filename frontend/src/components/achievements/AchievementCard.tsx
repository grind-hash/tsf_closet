/**
 * AchievementCard - 実績カードコンポーネント
 * 007-chat-interactive-ux
 */

import type { Achievement } from "../../types";
import { useTranslation } from "react-i18next";
import "./AchievementCard.css";

interface AchievementCardProps {
  achievement: Achievement;
  unlocked: boolean;
  unlockedAt?: string;
}

export default function AchievementCard({
  achievement,
  unlocked,
  unlockedAt,
}: AchievementCardProps) {
  const { t, i18n } = useTranslation();
  // 日時をフォーマット
  const formatDate = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleDateString(
        i18n.language === "en" ? "en-US" : "ja-JP",
        {
          year: "numeric",
          month: "short",
          day: "numeric",
        },
      );
    } catch {
      return "";
    }
  };

  return (
    <div
      className={`achievement-card ${unlocked ? "is-unlocked" : "is-locked"}`}
    >
      <div className="achievement-card__icon">
        {unlocked ? achievement.icon : "🔒"}
      </div>

      <div className="achievement-card__content">
        <h3 className="achievement-card__name">
          {unlocked ? achievement.name : t("achievements.lockedName")}
        </h3>
        <p className="achievement-card__description">
          {unlocked
            ? achievement.description
            : t("achievements.lockedDescription")}
        </p>

        {!unlocked && achievement.hint && (
          <p className="achievement-card__hint">💡 {achievement.hint}</p>
        )}

        {unlocked && unlockedAt && (
          <span className="achievement-card__date">
            {t("achievements.achievedAt", { date: formatDate(unlockedAt) })}
          </span>
        )}
      </div>

      {unlocked && (
        <div className="achievement-card__badge">
          <span>✓</span>
        </div>
      )}
    </div>
  );
}
