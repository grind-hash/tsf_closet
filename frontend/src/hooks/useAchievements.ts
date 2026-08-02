/**
 * useAchievements - 実績フック
 * 007-chat-interactive-ux
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchAchievementDetail,
  fetchAchievementsList,
} from "../apis/achievements";
import type { Achievement } from "../types";

interface AchievementWithStatus extends Achievement {
  unlocked: boolean;
  unlockedAt?: string;
}

interface UseAchievementsOptions {
  sessionId?: string;
  autoFetch?: boolean;
}

interface UseAchievementsReturn {
  achievements: AchievementWithStatus[];
  isLoading: boolean;
  error: string | null;
  stats: { total: number; unlocked: number };
  refresh: () => Promise<void>;
  getAchievement: (id: string) => Promise<AchievementWithStatus | null>;
}

export function useAchievements(
  options: UseAchievementsOptions = {},
): UseAchievementsReturn {
  const { sessionId, autoFetch = true } = options;

  const [achievements, setAchievements] = useState<AchievementWithStatus[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({ total: 0, unlocked: 0 });

  // 実績一覧を取得
  const fetchAchievements = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await fetchAchievementsList(sessionId);

      setAchievements(response.achievements);
      setStats({
        total: response.total,
        unlocked: response.unlocked_count,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  // リフレッシュ
  const refresh = useCallback(async () => {
    await fetchAchievements();
  }, [fetchAchievements]);

  // 個別実績を取得
  const getAchievement = useCallback(
    async (id: string): Promise<AchievementWithStatus | null> => {
      try {
        const response = await fetchAchievementDetail(id, sessionId);
        return response;
      } catch (err) {
        console.error("Failed to fetch achievement:", err);
        return null;
      }
    },
    [sessionId],
  );

  // 初回自動取得
  useEffect(() => {
    if (autoFetch) {
      fetchAchievements();
    }
  }, [autoFetch, fetchAchievements]);

  return {
    achievements,
    isLoading,
    error,
    stats,
    refresh,
    getAchievement,
  };
}
