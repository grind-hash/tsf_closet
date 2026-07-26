/**
 * GalleryScreen - ギャラリー画面
 * 007-chat-interactive-ux
 *
 * セッション毎表示モード + アイテム詳細表示
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { deleteGalleryItem, fetchGallerySessions } from "../../apis/gallery";
import { useGame } from "../../contexts/GameContext";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import type { GalleryItem, GallerySession } from "../../types";
import { API_BASE } from "../../utils/api";
import MainLayout from "../layout/MainLayout";
import GalleryCard from "./GalleryCard";
import PlaySummaryModal from "./PlaySummaryModal";
import "./GalleryScreen.css";

interface GalleryScreenProps {
  onSelectItem?: (item: GalleryItem) => void;
}

export default function GalleryScreen({ onSelectItem }: GalleryScreenProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { restoreSessionById } = useGame();

  // URLベースで表示モードを判定: /gallery/:sessionId → items, /gallery → sessions
  const urlSessionId = useMemo(() => {
    const match = location.pathname.match(/^\/gallery\/(.+)$/);
    return match ? match[1] : null;
  }, [location.pathname]);

  const displayMode = urlSessionId ? "items" : "sessions";

  const [selectedSession, setSelectedSession] = useState<GallerySession | null>(
    null,
  );

  // セッション一覧
  const [sessions, setSessions] = useState<GallerySession[]>([]);
  const [sessionsPage, setSessionsPage] = useState(1);
  const [sessionsHasMore, setSessionsHasMore] = useState(false);
  const [sessionsTotal, setSessionsTotal] = useState(0);

  // アイテム一覧
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [itemsPage, setItemsPage] = useState(1);
  const [itemsHasMore, setItemsHasMore] = useState(false);
  const [itemsTotal, setItemsTotal] = useState(0);

  // 共通状態
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<GallerySession | null>(
    null,
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteItemConfirm, setDeleteItemConfirm] =
    useState<GalleryItem | null>(null);

  // Play Summary modal
  const [summarySessionId, setSummarySessionId] = useState<string | null>(null);

  // フリーワード検索（入力値とデバウンス後の実クエリを分離）
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // スクロールコンテナ（IntersectionObserver の root）
  const [contentEl, setContentEl] = useState<HTMLDivElement | null>(null);
  // isLoading の state 更新前の二重リクエスト防止
  const loadingRef = useRef(false);
  // 検索など連続リクエスト時に古い応答を捨てる
  const sessionsRequestIdRef = useRef(0);

  const pageSize = 20;

  // 入力デバウンス（300ms）
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  // セッション一覧を取得
  const fetchSessions = useCallback(
    async (pageNum: number, query: string = searchQuery) => {
      const requestId = ++sessionsRequestIdRef.current;
      try {
        loadingRef.current = true;
        setIsLoading(true);
        setError(null);

        const data = await fetchGallerySessions(pageNum, pageSize, query);

        // より新しい検索要求が走っている場合は結果を捨てる
        if (requestId !== sessionsRequestIdRef.current) {
          return;
        }

        setSessions((prev) =>
          pageNum === 1 ? data.sessions : [...prev, ...data.sessions],
        );
        setSessionsHasMore(data.has_more);
        setSessionsTotal(data.total);
      } catch (err) {
        if (requestId !== sessionsRequestIdRef.current) {
          return;
        }
        setError(
          err instanceof Error ? err.message : t("gallery.genericError"),
        );
      } finally {
        if (requestId === sessionsRequestIdRef.current) {
          loadingRef.current = false;
          setIsLoading(false);
        }
      }
    },
    [t, searchQuery],
  );

  // アイテム一覧を取得（特定セッション）
  const fetchItems = useCallback(
    async (sessionId: string, pageNum: number) => {
      try {
        loadingRef.current = true;
        setIsLoading(true);
        setError(null);

        const response = await fetch(
          `${API_BASE}/gallery?session_id=${sessionId}&page=${pageNum}&page_size=${pageSize}`,
        );

        if (!response.ok) {
          throw new Error(t("gallery.fetchGalleryError"));
        }

        const data = await response.json();

        setItems((prev) =>
          pageNum === 1 ? data.items : [...prev, ...data.items],
        );
        setItemsHasMore(data.has_more);
        setItemsTotal(data.total);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t("gallery.genericError"),
        );
      } finally {
        loadingRef.current = false;
        setIsLoading(false);
      }
    },
    [t],
  );

  // 初回・検索語変更時の読み込み（ページをリセット）
  useEffect(() => {
    setSessionsPage(1);
    setSessions([]);
    void fetchSessions(1, searchQuery);
  }, [fetchSessions, searchQuery]);

  // URLのセッションIDが変わったらアイテム読み込み
  useEffect(() => {
    if (urlSessionId) {
      // sessionsから一致するものを探す
      const found = sessions.find((s) => s.session_id === urlSessionId);
      if (found) {
        setSelectedSession(found);
      } else {
        // sessionsが未取得の場合もアイテムは読み込む
        setSelectedSession(null);
      }
      setItemsPage(1);
      setItems([]);
      fetchItems(urlSessionId, 1);
    } else {
      setSelectedSession(null);
      setItems([]);
      setItemsPage(1);
    }
  }, [urlSessionId, sessions, fetchItems]);

  // セッション追加読み込み
  const handleLoadMoreSessions = useCallback(() => {
    if (loadingRef.current || isLoading || !sessionsHasMore) {
      return;
    }
    const nextPage = sessionsPage + 1;
    setSessionsPage(nextPage);
    void fetchSessions(nextPage, searchQuery);
  }, [isLoading, sessionsHasMore, sessionsPage, fetchSessions, searchQuery]);

  const handleClearSearch = useCallback(() => {
    setSearchInput("");
    setSearchQuery("");
  }, []);

  // アイテム追加読み込み（URL の sessionId を優先）
  const handleLoadMoreItems = useCallback(() => {
    const sessionId = urlSessionId ?? selectedSession?.session_id;
    if (loadingRef.current || isLoading || !itemsHasMore || !sessionId) {
      return;
    }
    const nextPage = itemsPage + 1;
    setItemsPage(nextPage);
    void fetchItems(sessionId, nextPage);
  }, [
    isLoading,
    itemsHasMore,
    itemsPage,
    urlSessionId,
    selectedSession,
    fetchItems,
  ]);

  // 無限スクロール（もっと見るボタンと併用）
  const sessionsSentinelRef = useInfiniteScroll({
    enabled:
      displayMode === "sessions" &&
      sessionsHasMore &&
      !isLoading &&
      sessions.length > 0,
    onLoadMore: handleLoadMoreSessions,
    root: contentEl,
  });

  const itemsSentinelRef = useInfiniteScroll({
    enabled:
      displayMode === "items" && itemsHasMore && !isLoading && items.length > 0,
    onLoadMore: handleLoadMoreItems,
    root: contentEl,
  });

  // セッションを選択してアイテム表示（URL遷移）
  const handleSessionClick = (session: GallerySession) => {
    navigate(`/gallery/${session.session_id}`);
  };

  // セッション一覧に戻る（URL遷移）
  const handleBackToSessions = () => {
    navigate("/gallery");
  };

  // セッション削除
  const handleDeleteSession = async () => {
    if (!deleteConfirm) return;

    try {
      setIsDeleting(true);
      const response = await fetch(
        `${API_BASE}/gallery/sessions/${deleteConfirm.session_id}`,
        { method: "DELETE" },
      );

      if (!response.ok) {
        throw new Error(t("gallery.deleteSessionError"));
      }

      // リストから削除
      setSessions((prev) =>
        prev.filter((s) => s.session_id !== deleteConfirm.session_id),
      );
      setSessionsTotal((prev) => prev - 1);
      setDeleteConfirm(null);

      // 削除したセッションを表示中だった場合は一覧に戻る
      if (selectedSession?.session_id === deleteConfirm.session_id) {
        handleBackToSessions();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("gallery.deleteFailed"));
    } finally {
      setIsDeleting(false);
    }
  };

  // アイテム個別削除
  const handleDeleteItem = async () => {
    if (!deleteItemConfirm) return;

    try {
      setIsDeleting(true);
      await deleteGalleryItem(deleteItemConfirm.id);

      // リストから削除
      setItems((prev) => prev.filter((i) => i.id !== deleteItemConfirm.id));
      setItemsTotal((prev) => prev - 1);

      // セッション一覧側のカウントも更新
      if (selectedSession) {
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === selectedSession.session_id
              ? { ...s, item_count: Math.max(0, s.item_count - 1) }
              : s,
          ),
        );
      }

      setDeleteItemConfirm(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("gallery.deleteItemError"),
      );
    } finally {
      setIsDeleting(false);
    }
  };

  // アイテム選択 - セッション復元してゲーム画面に遷移
  const handleItemClick = useCallback(
    async (item: GalleryItem) => {
      // カスタムハンドラがあれば優先
      if (onSelectItem) {
        onSelectItem(item);
        return;
      }

      // デフォルト: セッション復元してゲーム画面に遷移
      try {
        const restored = await restoreSessionById(item.session_id);
        if (!restored) {
          console.error("セッション復元に失敗しました");
          return;
        }

        // ゲーム画面に遷移（セッションID + historyId付き）
        navigate(`/play/${item.session_id}?historyId=${item.id}`);
      } catch (err) {
        console.error("セッション復元エラー:", err);
      }
    },
    [onSelectItem, navigate, restoreSessionById],
  );

  // セッションをゲームで再開
  const handleResumeSession = async (session: GallerySession) => {
    try {
      const restored = await restoreSessionById(session.session_id);
      if (!restored) {
        console.error("セッション復元に失敗しました");
        return;
      }

      navigate(`/play/${session.session_id}`);
    } catch (err) {
      console.error("セッション復元エラー:", err);
    }
  };

  // 日付フォーマット
  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString(
        i18n.language === "en" ? "en-US" : "ja-JP",
        {
          year: "numeric",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        },
      );
    } catch {
      return isoString;
    }
  };

  return (
    <MainLayout>
      <div className="gallery-screen">
        {/* ヘッダー */}
        <header className="gallery-screen__header">
          <div className="gallery-screen__header-left">
            {displayMode === "items" && (
              <button
                type="button"
                className="gallery-screen__back-btn"
                onClick={handleBackToSessions}
                aria-label={t("gallery.backToSessions")}
              >
                ← {t("gallery.back")}
              </button>
            )}
            <h1 className="gallery-screen__title">
              {displayMode === "sessions"
                ? t("gallery.title")
                : selectedSession?.character_name || t("gallery.sessionDetail")}
            </h1>
          </div>
          <div className="gallery-screen__controls">
            <span className="gallery-screen__count">
              {displayMode === "sessions"
                ? `${sessionsTotal} ${t("gallery.sessionsSuffix")}`
                : `${itemsTotal} ${t("gallery.itemsSuffix")}`}
            </span>
          </div>
        </header>

        {/* セッション一覧時のみフリーワード検索 */}
        {displayMode === "sessions" && (
          <div className="gallery-screen__search">
            <label
              className="gallery-screen__search-label"
              htmlFor="gallery-search"
            >
              <span className="gallery-screen__search-icon" aria-hidden="true">
                🔍
              </span>
              <input
                id="gallery-search"
                type="search"
                className="gallery-screen__search-input"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t("gallery.searchPlaceholder")}
                aria-label={t("gallery.searchAria")}
                autoComplete="off"
                spellCheck={false}
              />
            </label>
            {searchInput && (
              <button
                type="button"
                className="gallery-screen__search-clear"
                onClick={handleClearSearch}
                aria-label={t("gallery.searchClear")}
              >
                ×
              </button>
            )}
          </div>
        )}

        {/* コンテンツ（スクロールコンテナ = 無限スクロールの root） */}
        <div ref={setContentEl} className="gallery-screen__content">
          {error && (
            <div className="gallery-screen__error">
              <p>{error}</p>
              <button
                type="button"
                onClick={() =>
                  displayMode === "sessions"
                    ? fetchSessions(1, searchQuery)
                    : selectedSession &&
                      fetchItems(selectedSession.session_id, 1)
                }
              >
                {t("gallery.retry")}
              </button>
            </div>
          )}

          {/* セッション一覧 */}
          {displayMode === "sessions" && !error && (
            <>
              {sessions.length === 0 && !isLoading && (
                <div className="gallery-screen__empty">
                  {searchQuery ? (
                    <>
                      <p>
                        {t("gallery.searchNoResults", { query: searchQuery })}
                      </p>
                      <p>{t("gallery.searchNoResultsHint")}</p>
                    </>
                  ) : (
                    <>
                      <p>{t("gallery.noSessions")}</p>
                      <p>{t("gallery.noSessionsHint")}</p>
                    </>
                  )}
                </div>
              )}

              {sessions.length > 0 && (
                <>
                  <div className="gallery-screen__sessions">
                    {sessions.map((session) => (
                      <div
                        key={session.session_id}
                        className="gallery-screen__session-card"
                      >
                        <button
                          type="button"
                          className="gallery-screen__session-thumb"
                          onClick={() => handleSessionClick(session)}
                        >
                          {session.thumbnail_url ? (
                            <img
                              src={`${API_BASE}${session.thumbnail_url}`}
                              alt={
                                session.character_name ||
                                t("gallery.sessionAlt")
                              }
                              loading="lazy"
                            />
                          ) : (
                            <div className="gallery-screen__session-no-image">
                              {t("gallery.noImage")}
                            </div>
                          )}
                        </button>
                        <div className="gallery-screen__session-info">
                          <h3 className="gallery-screen__session-name">
                            {session.character_name ||
                              t("gallery.unknownCharacter")}
                            {session.self_mode && (
                              <span className="gallery-screen__self-mode-chip">
                                {t("gallery.selfModeChip")}
                              </span>
                            )}
                          </h3>
                          <p className="gallery-screen__session-meta">
                            {session.item_count} {t("gallery.itemsUnit")} ・{" "}
                            {formatDate(session.last_timestamp)}
                          </p>
                          {session.match_snippet && (
                            <p
                              className="gallery-screen__session-snippet"
                              title={session.match_snippet}
                            >
                              {session.match_snippet}
                            </p>
                          )}
                          <div className="gallery-screen__session-actions">
                            <button
                              type="button"
                              className="gallery-screen__session-resume"
                              onClick={() => handleResumeSession(session)}
                              title={t("gallery.resumeSessionTitle")}
                            >
                              ▶ {t("gallery.resume")}
                            </button>
                            <button
                              type="button"
                              className={`gallery-screen__session-summary${
                                session.has_summary
                                  ? " gallery-screen__session-summary--done"
                                  : ""
                              }`}
                              onClick={() =>
                                setSummarySessionId(session.session_id)
                              }
                              title={t("gallery.summaryButtonTitle")}
                            >
                              {session.has_summary ? "✅" : "📜"}{" "}
                              {t("gallery.summaryButton")}
                            </button>
                            <button
                              type="button"
                              className="gallery-screen__session-delete"
                              onClick={() => setDeleteConfirm(session)}
                              title={t("gallery.deleteSessionTitle")}
                            >
                              🗑
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {sessionsHasMore && (
                    <div className="gallery-screen__load-more">
                      <div
                        ref={sessionsSentinelRef}
                        className="gallery-screen__scroll-sentinel"
                        aria-hidden="true"
                      />
                      <button
                        type="button"
                        className="gallery-screen__load-more-btn"
                        onClick={handleLoadMoreSessions}
                        disabled={isLoading}
                      >
                        {isLoading
                          ? t("gallery.loading")
                          : t("gallery.loadMore")}
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {/* アイテム一覧（セッション詳細） */}
          {displayMode === "items" && !error && (
            <>
              {items.length === 0 && !isLoading && (
                <div className="gallery-screen__empty">
                  <p>{t("gallery.noImagesInSession")}</p>
                </div>
              )}

              {items.length > 0 && (
                <>
                  <div className="gallery-screen__cards">
                    {items.map((item) => (
                      <GalleryCard
                        key={item.id}
                        item={item}
                        onClick={() => handleItemClick(item)}
                        onDelete={(i) => setDeleteItemConfirm(i)}
                      />
                    ))}
                  </div>

                  {itemsHasMore && (
                    <div className="gallery-screen__load-more">
                      <div
                        ref={itemsSentinelRef}
                        className="gallery-screen__scroll-sentinel"
                        aria-hidden="true"
                      />
                      <button
                        type="button"
                        className="gallery-screen__load-more-btn"
                        onClick={handleLoadMoreItems}
                        disabled={isLoading}
                      >
                        {isLoading
                          ? t("gallery.loading")
                          : t("gallery.loadMore")}
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {isLoading &&
            ((displayMode === "sessions" && sessions.length === 0) ||
              (displayMode === "items" && items.length === 0)) && (
              <div className="gallery-screen__loading">
                <span className="gallery-screen__spinner" />
                <p>{t("gallery.loading")}</p>
              </div>
            )}
        </div>

        {/* 削除確認モーダル */}
        {deleteConfirm && (
          <div
            className="gallery-screen__delete-modal-overlay"
            onClick={() => !isDeleting && setDeleteConfirm(null)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && !isDeleting) setDeleteConfirm(null);
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
          >
            <div
              className="gallery-screen__delete-modal"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={() => {}}
              role="document"
            >
              <h2 id="delete-modal-title">{t("gallery.deleteModalTitle")}</h2>
              <p>
                {t("gallery.deleteConfirm", {
                  name:
                    deleteConfirm.character_name ||
                    t("gallery.deleteTargetDefault"),
                })}
              </p>
              <p className="gallery-screen__delete-modal-warning">
                {t("gallery.deleteWarning", {
                  count: deleteConfirm.item_count,
                })}
              </p>
              <div className="gallery-screen__delete-modal-actions">
                <button
                  type="button"
                  onClick={handleDeleteSession}
                  disabled={isDeleting}
                  className="gallery-screen__delete-modal-confirm"
                >
                  {isDeleting
                    ? t("gallery.deleting")
                    : t("gallery.deleteAction")}
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteConfirm(null)}
                  disabled={isDeleting}
                  className="gallery-screen__delete-modal-cancel"
                >
                  {t("gallery.cancel")}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* アイテム個別削除確認モーダル */}
        {deleteItemConfirm && (
          <div
            className="gallery-screen__delete-modal-overlay"
            onClick={() => !isDeleting && setDeleteItemConfirm(null)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && !isDeleting) setDeleteItemConfirm(null);
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-item-modal-title"
          >
            <div
              className="gallery-screen__delete-modal"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={() => {}}
              role="document"
            >
              <h2 id="delete-item-modal-title">
                {t("gallery.deleteItemTitle")}
              </h2>
              <p>{t("gallery.deleteItemConfirm")}</p>
              <p className="gallery-screen__delete-modal-warning">
                {t("gallery.deleteItemWarning")}
              </p>
              <div className="gallery-screen__delete-modal-actions">
                <button
                  type="button"
                  onClick={handleDeleteItem}
                  disabled={isDeleting}
                  className="gallery-screen__delete-modal-confirm"
                >
                  {isDeleting
                    ? t("gallery.deleting")
                    : t("gallery.deleteItemAction")}
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteItemConfirm(null)}
                  disabled={isDeleting}
                  className="gallery-screen__delete-modal-cancel"
                >
                  {t("gallery.cancel")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Play Summary Modal */}
      <PlaySummaryModal
        sessionId={summarySessionId || ""}
        isOpen={summarySessionId !== null}
        onClose={() => setSummarySessionId(null)}
        onSummaryGenerated={(sid) => {
          setSessions((prev) =>
            prev.map((s) =>
              s.session_id === sid ? { ...s, has_summary: true } : s,
            ),
          );
        }}
      />
    </MainLayout>
  );
}
