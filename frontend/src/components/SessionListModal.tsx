/**
 * SessionListModal - displays past session history for browsing
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SessionSummary } from "../types";
import "./SessionListModal.css";

interface SessionListModalProps {
  onClose: () => void;
  onSelectSession: (sessionId: string) => void;
}

export default function SessionListModal({
  onClose,
  onSelectSession,
}: SessionListModalProps) {
  const { t, i18n } = useTranslation();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 12;

  // offset 変更で再取得する。fetchSessions は同コンポーネント内の関数なので依存に含めない
  // biome-ignore lint/correctness/useExhaustiveDependencies: offset 駆動の一覧再取得
  useEffect(() => {
    fetchSessions();
  }, [offset]);

  const fetchSessions = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/game/sessions?limit=${limit}&offset=${offset}`,
      );
      if (!response.ok) throw new Error(t("sessionList.fetchError"));
      const data = await response.json();

      // スネークケース→キャメルケース変換
      const mappedSessions: SessionSummary[] = data.sessions.map(
        (s: {
          session_id: string;
          character_id: string;
          character_name: string;
          thumbnail_url: string;
          transformation_count: number;
          is_active: boolean;
          created_at: string;
          updated_at: string;
          last_instruction: string;
        }) => ({
          sessionId: s.session_id,
          characterId: s.character_id,
          characterName: s.character_name,
          thumbnailUrl: s.thumbnail_url,
          transformationCount: s.transformation_count,
          isActive: s.is_active,
          createdAt: s.created_at,
          updatedAt: s.updated_at,
          lastInstruction: s.last_instruction,
        }),
      );

      setSessions(mappedSessions);
      setTotalCount(data.total_count);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("sessionList.genericError"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString(i18n.language === "en" ? "en-US" : "ja-JP", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const totalPages = Math.ceil(totalCount / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="session-list-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>{t("sessionList.title")}</h2>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </header>

        <div className="modal-content">
          {isLoading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>{t("common.loading")}</p>
            </div>
          ) : error ? (
            <div className="error-state">
              <p>⚠️ {error}</p>
              <button className="btn btn-secondary" onClick={fetchSessions}>
                {t("common.retry")}
              </button>
            </div>
          ) : sessions.length === 0 ? (
            <div className="empty-state">
              <p>{t("sessionList.empty")}</p>
              <p className="hint">{t("sessionList.emptyHint")}</p>
            </div>
          ) : (
            <>
              <div className="session-grid">
                {sessions.map((session) => (
                  <div
                    key={session.sessionId}
                    className={`session-card ${session.isActive ? "active" : ""}`}
                    onClick={() => onSelectSession(session.sessionId)}
                  >
                    <div className="session-thumbnail">
                      {session.thumbnailUrl ? (
                        <img
                          src={session.thumbnailUrl}
                          alt={t("sessionList.sessionAlt")}
                        />
                      ) : (
                        <div className="no-thumbnail">📷</div>
                      )}
                      {session.isActive && (
                        <span className="active-badge">
                          {t("sessionList.currentSession")}
                        </span>
                      )}
                    </div>
                    <div className="session-info">
                      <div className="session-character">
                        {session.characterName || t("sessionList.customImage")}
                      </div>
                      <div className="session-meta">
                        <span className="transform-count">
                          {t("sessionList.transformCount", {
                            count: session.transformationCount,
                          })}
                        </span>
                        <span className="session-date">
                          {formatDate(session.updatedAt)}
                        </span>
                      </div>
                      {session.lastInstruction && (
                        <div className="last-instruction">
                          「{session.lastInstruction.slice(0, 30)}
                          {session.lastInstruction.length > 30 ? "..." : ""}」
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {totalPages > 1 && (
                <div className="pagination">
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={currentPage === 1}
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                  >
                    {t("sessionList.prev")}
                  </button>
                  <span className="page-info">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + limit)}
                  >
                    {t("sessionList.next")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
