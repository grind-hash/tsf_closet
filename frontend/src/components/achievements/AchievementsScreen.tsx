/**
 * AchievementsScreen - 実績一覧画面
 * 007-chat-interactive-ux
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import MainLayout from "../layout/MainLayout";
import AchievementCard from "./AchievementCard";
import type { Achievement } from "../../types";
import { API_BASE } from "../../utils/api";
import "./AchievementsScreen.css";

interface AchievementsScreenProps {
  sessionId?: string;
}

interface AchievementWithStatus extends Achievement {
  unlocked: boolean;
  unlockedAt?: string;
}

export default function AchievementsScreen({
  sessionId,
}: AchievementsScreenProps) {
  const { t } = useTranslation();
  const [achievements, setAchievements] = useState<AchievementWithStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [stats, setStats] = useState({ total: 0, unlocked: 0 });
  const [totals, setTotals] = useState({
    transformCount: 0,
    crossdressCount: 0,
    realityAlterCount: 0,
    galleryCount: 0,
  });

  // カテゴリフィルターオプション
  const categories = [
    { id: "all", label: t("achievements.filterAll") },
    { id: "transform", label: t("achievements.filterTransform") },
    { id: "crossdress", label: t("achievements.filterCrossdress") },
    { id: "reality", label: t("achievements.filterReality") },
    { id: "collection", label: t("achievements.filterCollection") },
    { id: "self", label: t("achievements.filterSelf") },
  ];

  // 実績を取得
  const fetchAchievements = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const params = new URLSearchParams();
      if (sessionId) {
        params.append("session_id", sessionId);
      }

      const response = await fetch(`${API_BASE}/achievements?${params}`);

      if (!response.ok) {
        throw new Error(t("achievements.fetchError"));
      }

      const data = await response.json();

      setAchievements(
        data.achievements.map((a: Record<string, unknown>) => ({
          id: a.id,
          name: a.name,
          description: a.description,
          category: a.category,
          icon: a.icon,
          conditionType: a.condition_type,
          conditionTarget: a.condition_target,
          conditionValue: a.condition_value,
          isHidden: a.is_hidden,
          hint: a.hint,
          unlocked: a.unlocked,
          unlockedAt: a.unlocked_at,
        })),
      );
      setStats({
        total: data.total,
        unlocked: data.unlocked_count,
      });
      setTotals({
        transformCount: data.transform_count ?? 0,
        crossdressCount: data.crossdress_count ?? 0,
        realityAlterCount: data.reality_alter_count ?? 0,
        galleryCount: data.gallery_count ?? 0,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("achievements.genericError"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, t]);

  useEffect(() => {
    fetchAchievements();
  }, [fetchAchievements]);

  // フィルタリング
  const filteredAchievements = achievements.filter(
    (a) => filter === "all" || a.category === filter,
  );

  // 進捗率
  const progressPercent =
    stats.total > 0 ? Math.round((stats.unlocked / stats.total) * 100) : 0;

  return (
    <MainLayout>
      <div className="achievements-screen">
        {/* ヘッダー */}
        <header className="achievements-screen__header">
          <div className="achievements-screen__title-area">
            <h1 className="achievements-screen__title">
              {t("achievements.title")}
            </h1>
            <div className="achievements-screen__progress">
              <div className="achievements-screen__progress-bar">
                <div
                  className="achievements-screen__progress-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="achievements-screen__progress-text">
                {stats.unlocked} / {stats.total} ({progressPercent}%)
              </span>
            </div>
          </div>

          <div className="achievements-screen__filters">
            {categories.map((cat) => (
              <button
                key={cat.id}
                type="button"
                className={`achievements-screen__filter-btn ${filter === cat.id ? "is-active" : ""}`}
                onClick={() => setFilter(cat.id)}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <div className="achievements-screen__totals">
            <span>
              {t("achievements.transformCount", {
                count: totals.transformCount,
              })}
            </span>
            <span>
              {t("achievements.crossdressCount", {
                count: totals.crossdressCount,
              })}
            </span>
            <span>
              {t("achievements.realityAlterCount", {
                count: totals.realityAlterCount,
              })}
            </span>
            <span>
              {t("achievements.galleryCount", { count: totals.galleryCount })}
            </span>
          </div>
        </header>

        {/* コンテンツ */}
        <div className="achievements-screen__content">
          {error && (
            <div className="achievements-screen__error">
              <p>{error}</p>
              <button type="button" onClick={fetchAchievements}>
                {t("achievements.retry")}
              </button>
            </div>
          )}

          {!error && isLoading && (
            <div className="achievements-screen__loading">
              <span className="achievements-screen__spinner" />
              <p>{t("achievements.loading")}</p>
            </div>
          )}

          {!error && !isLoading && filteredAchievements.length === 0 && (
            <div className="achievements-screen__empty">
              <p>{t("achievements.empty")}</p>
            </div>
          )}

          {!error && !isLoading && filteredAchievements.length > 0 && (
            <div className="achievements-screen__grid">
              {filteredAchievements.map((achievement) => (
                <AchievementCard
                  key={achievement.id}
                  achievement={achievement}
                  unlocked={achievement.unlocked}
                  unlockedAt={achievement.unlockedAt}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
}
