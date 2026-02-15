/**
 * NotificationContext - 通知の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from "react";
import type { Achievement } from "../types";

// 通知タイプ
export type NotificationType =
  | "achievement"
  | "info"
  | "success"
  | "warning"
  | "error";

// 通知データ
export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message?: string;
  achievement?: Achievement;
  duration?: number; // ミリ秒、0で自動消去なし
  createdAt: number;
}

// 通知状態
interface NotificationState {
  notifications: Notification[];
  maxNotifications: number;
}

// アクション型
type NotificationAction =
  | {
      type: "ADD_NOTIFICATION";
      payload: Omit<Notification, "id" | "createdAt">;
    }
  | { type: "REMOVE_NOTIFICATION"; payload: string }
  | { type: "CLEAR_ALL_NOTIFICATIONS" }
  | { type: "SET_MAX_NOTIFICATIONS"; payload: number };

// デフォルト状態
const defaultState: NotificationState = {
  notifications: [],
  maxNotifications: 5,
};

// ID生成
let notificationIdCounter = 0;
const generateId = (): string => {
  notificationIdCounter += 1;
  return `notification-${Date.now()}-${notificationIdCounter}`;
};

// Reducer
function notificationReducer(
  state: NotificationState,
  action: NotificationAction,
): NotificationState {
  switch (action.type) {
    case "ADD_NOTIFICATION": {
      const newNotification: Notification = {
        ...action.payload,
        id: generateId(),
        createdAt: Date.now(),
      };
      const notifications = [newNotification, ...state.notifications].slice(
        0,
        state.maxNotifications,
      );
      return { ...state, notifications };
    }
    case "REMOVE_NOTIFICATION":
      return {
        ...state,
        notifications: state.notifications.filter(
          (n) => n.id !== action.payload,
        ),
      };
    case "CLEAR_ALL_NOTIFICATIONS":
      return { ...state, notifications: [] };
    case "SET_MAX_NOTIFICATIONS":
      return { ...state, maxNotifications: action.payload };
    default:
      return state;
  }
}

// Context型定義
interface NotificationContextType {
  notifications: Notification[];
  showNotification: (
    type: NotificationType,
    title: string,
    message?: string,
    duration?: number,
  ) => void;
  showAchievementNotification: (achievement: Achievement) => void;
  removeNotification: (id: string) => void;
  clearAll: () => void;
}

// Context作成
const NotificationContext = createContext<NotificationContextType | null>(null);

// Provider コンポーネント
export function NotificationProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(notificationReducer, defaultState);

  // 汎用通知表示
  const showNotification = useCallback(
    (
      type: NotificationType,
      title: string,
      message?: string,
      duration = 5000,
    ) => {
      dispatch({
        type: "ADD_NOTIFICATION",
        payload: { type, title, message, duration },
      });
    },
    [],
  );

  // 実績通知表示
  const showAchievementNotification = useCallback(
    (achievement: Achievement) => {
      dispatch({
        type: "ADD_NOTIFICATION",
        payload: {
          type: "achievement",
          title: "実績解除！",
          message: achievement.name,
          achievement,
          duration: 7000,
        },
      });
    },
    [],
  );

  // 通知削除
  const removeNotification = useCallback((id: string) => {
    dispatch({ type: "REMOVE_NOTIFICATION", payload: id });
  }, []);

  // 全削除
  const clearAll = useCallback(() => {
    dispatch({ type: "CLEAR_ALL_NOTIFICATIONS" });
  }, []);

  const value: NotificationContextType = {
    notifications: state.notifications,
    showNotification,
    showAchievementNotification,
    removeNotification,
    clearAll,
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

// Custom Hook
// eslint-disable-next-line react-refresh/only-export-components
export function useNotification(): NotificationContextType {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error(
      "useNotification must be used within a NotificationProvider",
    );
  }
  return context;
}
