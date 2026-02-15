/**
 * AchievementToast - 実績解除トースト通知
 * 007-chat-interactive-ux
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Achievement } from "../../types";
import "./AchievementToast.css";

interface AchievementToastProps {
  achievement: Achievement;
  onClose: () => void;
  duration?: number;
}

export default function AchievementToast({
  achievement,
  onClose,
  duration = 5000,
}: AchievementToastProps) {
  const { t } = useTranslation();
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsExiting(true);
    }, duration - 300);

    const closeTimer = setTimeout(() => {
      onClose();
    }, duration);

    return () => {
      clearTimeout(timer);
      clearTimeout(closeTimer);
    };
  }, [duration, onClose]);

  const handleClick = () => {
    setIsExiting(true);
    setTimeout(onClose, 300);
  };

  return (
    <div
      className={`achievement-toast ${isExiting ? "is-exiting" : ""}`}
      onClick={handleClick}
      role="status"
      aria-live="polite"
    >
      <div className="achievement-toast__icon">{achievement.icon}</div>

      <div className="achievement-toast__content">
        <span className="achievement-toast__label">
          {t("achievementToast.unlocked")}
        </span>
        <h4 className="achievement-toast__name">{achievement.name}</h4>
        <p className="achievement-toast__description">
          {achievement.description}
        </p>
      </div>

      <button
        type="button"
        className="achievement-toast__close"
        onClick={(e) => {
          e.stopPropagation();
          handleClick();
        }}
        aria-label={t("common.close")}
      >
        ✕
      </button>
    </div>
  );
}
