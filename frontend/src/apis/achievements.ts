/**
 * Achievements API functions
 * 007-chat-interactive-ux
 */

import type { Achievement } from "../types";
import { API_BASE } from "../utils/api";

// 実績＋ステータス型
interface AchievementWithStatus extends Achievement {
  unlocked: boolean;
  unlockedAt?: string;
}

// レスポンス型
interface AchievementsListResponse {
  achievements: AchievementWithStatus[];
  total: number;
  unlocked_count: number;
}

/**
 * 実績一覧を取得
 */
export async function fetchAchievementsList(
  sessionId?: string,
): Promise<AchievementsListResponse> {
  const params = new URLSearchParams();
  if (sessionId) {
    params.append("session_id", sessionId);
  }

  const response = await fetch(`${API_BASE}/achievements?${params}`);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "実績の取得に失敗しました");
  }

  const data = await response.json();

  return {
    achievements: data.achievements.map(convertAchievement),
    total: data.total,
    unlocked_count: data.unlocked_count,
  };
}

/**
 * 実績詳細を取得
 */
export async function fetchAchievementDetail(
  achievementId: string,
  sessionId?: string,
): Promise<AchievementWithStatus> {
  const params = new URLSearchParams();
  if (sessionId) {
    params.append("session_id", sessionId);
  }

  const response = await fetch(
    `${API_BASE}/achievements/${achievementId}?${params}`,
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("実績が見つかりません");
    }
    const error = await response.text();
    throw new Error(error || "実績の取得に失敗しました");
  }

  const data = await response.json();
  return convertAchievement(data);
}

/**
 * APIレスポンスをフロントエンド型に変換
 */
function convertAchievement(
  item: Record<string, unknown>,
): AchievementWithStatus {
  return {
    id: String(item.id),
    name: String(item.name),
    description: String(item.description),
    category: String(item.category),
    icon: String(item.icon),
    condition_type: String(item.condition_type),
    condition_target: String(item.condition_target),
    condition_value: Number(item.condition_value),
    is_hidden: Boolean(item.is_hidden),
    unlocked: Boolean(item.unlocked),
    unlockedAt: item.unlocked_at ? String(item.unlocked_at) : undefined,
  };
}
