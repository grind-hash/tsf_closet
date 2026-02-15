/**
 * NotificationContainer - 通知トーストを表示するコンテナ
 * 007-chat-interactive-ux
 */

import { useNotification } from "../../contexts/NotificationContext";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import AchievementToast from "../achievements/AchievementToast";
import "./NotificationContainer.css";

export default function NotificationContainer() {
  const { t } = useTranslation();
  const { notifications, removeNotification } = useNotification();
  const { state: settings } = useSettings();

  // 実績通知が無効の場合は実績タイプの通知をフィルタリング
  const visibleNotifications = notifications.filter((notification) => {
    if (notification.type === "achievement") {
      return settings.showAchievementNotifications;
    }
    return true;
  });

  if (visibleNotifications.length === 0) {
    return null;
  }

  return (
    <div className="notification-container" aria-live="polite">
      {visibleNotifications.map((notification) => {
        if (notification.type === "achievement" && notification.achievement) {
          return (
            <AchievementToast
              key={notification.id}
              achievement={notification.achievement}
              onClose={() => removeNotification(notification.id)}
              duration={notification.duration}
            />
          );
        }

        // 汎用通知（info, success, warning, error）
        return (
          <div
            key={notification.id}
            className={`notification-toast notification-toast--${notification.type}`}
            role="alert"
          >
            <div className="notification-toast__content">
              <strong className="notification-toast__title">
                {notification.title}
              </strong>
              {notification.message && (
                <p className="notification-toast__message">
                  {notification.message}
                </p>
              )}
            </div>
            <button
              type="button"
              className="notification-toast__close"
              onClick={() => removeNotification(notification.id)}
              aria-label={t("common.close")}
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
