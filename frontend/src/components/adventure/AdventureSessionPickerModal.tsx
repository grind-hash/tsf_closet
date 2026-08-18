import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { type FavoriteItem, fetchFavorites } from "../../apis/favorites";
import { fetchGallerySessions } from "../../apis/gallery";
import { useGallery } from "../../hooks/useGallery";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import type { GallerySession } from "../../types";
import { API_BASE } from "../../utils/api";

export type AdventureSourceOrigin = "session" | "favorite";

/**
 * 開始セッション(+時点)の選択結果。
 * サマリ表示に必要なメタ情報も一緒に返し、親コンポーネントでの再取得を不要にする。
 */
export interface AdventureSourceSelection {
  sessionId: string;
  /** undefined = 現在の状態 */
  historyId?: string;
  characterName: string | null;
  thumbnailUrl: string;
  /** 時点の指示テキストまたはお気に入りラベル。null = 現在の状態 */
  pointLabel: string | null;
  origin: AdventureSourceOrigin;
}

/** セッションの「現在の状態」を選んだときの選択結果を作る */
export function selectionFromSession(
  session: GallerySession,
): AdventureSourceSelection {
  return {
    sessionId: session.session_id,
    historyId: undefined,
    characterName: session.character_name,
    thumbnailUrl: session.thumbnail_url,
    pointLabel: null,
    origin: "session",
  };
}

function mediaUrl(url: string): string {
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

function formatSessionDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(locale.startsWith("en") ? "en-US" : "ja-JP", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

const PAGE_SIZE = 20;
const HISTORY_PAGE_SIZE = 30;

type PickerTab = "sessions" | "favorites";

interface SessionHistoryListProps {
  session: GallerySession;
  /** 無限スクロールの root にするスクロールコンテナ */
  root: Element | null;
  selected: AdventureSourceSelection | null;
  onSelect: (selection: AdventureSourceSelection) => void;
}

/**
 * ドリルダウン表示: セッション内の時点(履歴画像)一覧。
 * key={session.session_id} でマウントし直し、前セッションの状態残留を防ぐ。
 */
function SessionHistoryList({
  session,
  root,
  selected,
  onSelect,
}: SessionHistoryListProps) {
  const { t } = useTranslation();
  const { items, isLoading, error, hasMore, loadMore, refresh } = useGallery({
    sessionId: session.session_id,
    pageSize: HISTORY_PAGE_SIZE,
  });
  const sentinelRef = useInfiniteScroll({
    enabled: hasMore && !isLoading && items.length > 0,
    onLoadMore: () => void loadMore(),
    root,
  });
  const isSameSession = selected?.sessionId === session.session_id;
  const isCurrentSelected = isSameSession && !selected?.historyId;

  return (
    <>
      <div
        className="adventure-session-picker__grid"
        role="group"
        aria-label={t("adventure.sourceState")}
      >
        <button
          type="button"
          className={isCurrentSelected ? "is-selected" : ""}
          data-selected={isCurrentSelected || undefined}
          onClick={() => onSelect(selectionFromSession(session))}
        >
          <span className="adventure-session-picker__thumb">
            <img src={mediaUrl(session.thumbnail_url)} alt="" />
          </span>
          <span className="adventure-session-picker__tile-label">
            {t("adventure.currentState")}
          </span>
        </button>
        {items.map((item) => {
          const isItemSelected =
            isSameSession && selected?.historyId === item.id;
          return (
            <button
              type="button"
              key={item.id}
              className={isItemSelected ? "is-selected" : ""}
              data-selected={isItemSelected || undefined}
              onClick={() =>
                onSelect({
                  sessionId: session.session_id,
                  historyId: item.id,
                  characterName: session.character_name,
                  thumbnailUrl: item.image_url,
                  pointLabel: item.instruction,
                  origin: "session",
                })
              }
            >
              <span className="adventure-session-picker__thumb">
                <img src={mediaUrl(item.image_url)} alt="" />
              </span>
              <span className="adventure-session-picker__tile-label">
                {item.instruction}
              </span>
            </button>
          );
        })}
      </div>
      {error && (
        <p className="adventure-session-picker__status" role="alert">
          {t("gallery.genericError")}
          <button type="button" onClick={() => void refresh()}>
            {t("gallery.retry")}
          </button>
        </p>
      )}
      {isLoading && (
        <p className="adventure-session-picker__status">
          {t("gallery.loading")}
        </p>
      )}
      {hasMore && !isLoading && (
        <button
          type="button"
          className="adventure-session-picker__load-more"
          onClick={() => void loadMore()}
        >
          {t("gallery.loadMore")}
        </button>
      )}
      <div ref={sentinelRef} className="adventure-session-picker__sentinel" />
    </>
  );
}

interface AdventureSessionPickerModalProps {
  title: string;
  selected: AdventureSourceSelection | null;
  onSelect: (selection: AdventureSourceSelection) => void;
  onClose: () => void;
}

/**
 * 開始セッション選択モーダル。
 * セッションタブ: 各セッション最新1枚のカード一覧(検索+無限スクロール)。
 * カードから「現在の状態で選択」で即決定、サムネイルクリックで時点一覧へドリルダウン。
 * お気に入りタブ: 1クリックでセッションと時点を同時決定する。
 */
export default function AdventureSessionPickerModal({
  title,
  selected,
  onSelect,
  onClose,
}: AdventureSessionPickerModalProps) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<PickerTab>(
    selected?.origin === "favorite" ? "favorites" : "sessions",
  );
  const [drilldownSession, setDrilldownSession] =
    useState<GallerySession | null>(null);

  const [sessions, setSessions] = useState<GallerySession[]>([]);
  const [sessionsPage, setSessionsPage] = useState(1);
  const [sessionsHasMore, setSessionsHasMore] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState(false);
  const [sessionsFetchedOnce, setSessionsFetchedOnce] = useState(false);
  // isLoading の state 反映前の二重リクエスト防止
  const sessionsLoadingRef = useRef(false);
  // 検索など連続リクエスト時に古い応答を捨てる
  const sessionsRequestIdRef = useRef(0);

  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [favoritesPage, setFavoritesPage] = useState(1);
  const [favoritesHasMore, setFavoritesHasMore] = useState(false);
  const [favoritesLoading, setFavoritesLoading] = useState(false);
  const [favoritesError, setFavoritesError] = useState(false);
  const [favoritesFetchedOnce, setFavoritesFetchedOnce] = useState(false);
  const favoritesLoadingRef = useRef(false);

  // 無限スクロールの root にするスクロールコンテナ。
  // useRef ではなく useState で保持し、要素確定後に observer を張り直す
  const [contentEl, setContentEl] = useState<HTMLDivElement | null>(null);

  // 入力デバウンス(300ms)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const loadSessions = useCallback(async (pageNum: number, query: string) => {
    const requestId = ++sessionsRequestIdRef.current;
    sessionsLoadingRef.current = true;
    setSessionsLoading(true);
    setSessionsError(false);
    try {
      const data = await fetchGallerySessions(pageNum, PAGE_SIZE, query);
      if (requestId !== sessionsRequestIdRef.current) return;
      setSessions((prev) =>
        pageNum === 1 ? data.sessions : [...prev, ...data.sessions],
      );
      setSessionsPage(pageNum);
      setSessionsHasMore(data.has_more);
    } catch {
      if (requestId !== sessionsRequestIdRef.current) return;
      setSessionsError(true);
    } finally {
      if (requestId === sessionsRequestIdRef.current) {
        sessionsLoadingRef.current = false;
        setSessionsLoading(false);
        setSessionsFetchedOnce(true);
      }
    }
  }, []);

  const loadFavorites = useCallback(async (pageNum: number) => {
    if (favoritesLoadingRef.current) return;
    favoritesLoadingRef.current = true;
    setFavoritesLoading(true);
    setFavoritesError(false);
    try {
      const data = await fetchFavorites(pageNum, PAGE_SIZE);
      setFavorites((prev) =>
        pageNum === 1 ? data.items : [...prev, ...data.items],
      );
      setFavoritesPage(pageNum);
      setFavoritesHasMore(data.has_more);
    } catch {
      setFavoritesError(true);
    } finally {
      favoritesLoadingRef.current = false;
      setFavoritesLoading(false);
      setFavoritesFetchedOnce(true);
    }
  }, []);

  // 初回と検索語変更時に1ページ目から取り直す。
  // お気に入り由来のキャラ名解決にも使うため、タブに関わらず読み込む
  useEffect(() => {
    setSessions([]);
    void loadSessions(1, searchQuery);
  }, [searchQuery, loadSessions]);

  // お気に入りはタブ初回アクティブ時に遅延取得する
  useEffect(() => {
    if (tab !== "favorites" || favoritesFetchedOnce) return;
    void loadFavorites(1);
  }, [tab, favoritesFetchedOnce, loadFavorites]);

  // Escape で閉じる
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  // オープン時の初期フォーカス: 選択中カードがあればそこへ、
  // 無ければ検索欄または先頭のボタンへ倒す
  const initialFocusDoneRef = useRef(false);
  useEffect(() => {
    if (initialFocusDoneRef.current || !contentEl) return;
    const fetchedOnce =
      tab === "sessions" ? sessionsFetchedOnce : favoritesFetchedOnce;
    const loading = tab === "sessions" ? sessionsLoading : favoritesLoading;
    if (!fetchedOnce || loading) return;
    initialFocusDoneRef.current = true;
    const target =
      contentEl.querySelector<HTMLElement>('[data-selected="true"]') ??
      searchInputRef.current ??
      contentEl.querySelector<HTMLElement>("button");
    target?.focus();
  }, [
    contentEl,
    tab,
    sessionsFetchedOnce,
    favoritesFetchedOnce,
    sessionsLoading,
    favoritesLoading,
  ]);

  const handleLoadMoreSessions = useCallback(() => {
    if (sessionsLoadingRef.current || !sessionsHasMore) return;
    void loadSessions(sessionsPage + 1, searchQuery);
  }, [sessionsHasMore, sessionsPage, searchQuery, loadSessions]);

  const handleLoadMoreFavorites = useCallback(() => {
    if (favoritesLoadingRef.current || !favoritesHasMore) return;
    void loadFavorites(favoritesPage + 1);
  }, [favoritesHasMore, favoritesPage, loadFavorites]);

  const sessionsSentinelRef = useInfiniteScroll({
    enabled:
      !drilldownSession &&
      tab === "sessions" &&
      sessionsHasMore &&
      !sessionsLoading &&
      sessions.length > 0,
    onLoadMore: handleLoadMoreSessions,
    root: contentEl,
  });

  const favoritesSentinelRef = useInfiniteScroll({
    enabled:
      !drilldownSession &&
      tab === "favorites" &&
      favoritesHasMore &&
      !favoritesLoading &&
      favorites.length > 0,
    onLoadMore: handleLoadMoreFavorites,
    root: contentEl,
  });

  // FavoriteItem はキャラ名を持たないため、読み込み済みセッションから可能な範囲で解決する
  const characterNameFor = useCallback(
    (sessionId: string): string | null =>
      sessions.find((session) => session.session_id === sessionId)
        ?.character_name ?? null,
    [sessions],
  );

  const renderSessionsTab = () => {
    if (sessionsError) {
      return (
        <p className="adventure-session-picker__status" role="alert">
          {t("gallery.genericError")}
          <button
            type="button"
            onClick={() => void loadSessions(1, searchQuery)}
          >
            {t("gallery.retry")}
          </button>
        </p>
      );
    }
    if (sessions.length === 0) {
      if (sessionsLoading || !sessionsFetchedOnce) {
        return (
          <p className="adventure-session-picker__status">
            {t("gallery.loading")}
          </p>
        );
      }
      return (
        <div className="adventure-session-picker__empty">
          <p>
            {searchQuery
              ? t("gallery.searchNoResults", { query: searchQuery })
              : t("gallery.noSessions")}
          </p>
          <small>
            {searchQuery
              ? t("gallery.searchNoResultsHint")
              : t("gallery.noSessionsHint")}
          </small>
        </div>
      );
    }
    return (
      <>
        <div className="adventure-session-picker__cards">
          {sessions.map((session) => {
            const name =
              session.character_name ?? t("adventure.unnamedCharacter");
            const isSelected = selected?.sessionId === session.session_id;
            return (
              <article
                key={session.session_id}
                className={`adventure-session-picker__card${
                  isSelected ? " is-selected" : ""
                }`}
              >
                <button
                  type="button"
                  className="adventure-session-picker__card-thumb"
                  data-selected={isSelected || undefined}
                  aria-label={t("adventure.sourcePicker.openHistory", { name })}
                  onClick={() => setDrilldownSession(session)}
                >
                  <img src={mediaUrl(session.thumbnail_url)} alt="" />
                </button>
                <div className="adventure-session-picker__card-info">
                  <strong>{name}</strong>
                  <span className="adventure-session-picker__card-meta">
                    {session.item_count}
                    {t("gallery.itemsUnit")}・
                    {formatSessionDate(session.first_timestamp, i18n.language)}
                  </span>
                  {session.match_snippet ? (
                    <span className="adventure-session-picker__card-preview">
                      {session.match_snippet}
                    </span>
                  ) : (
                    session.last_instruction && (
                      <span className="adventure-session-picker__card-preview">
                        {session.last_instruction}
                      </span>
                    )
                  )}
                </div>
                <button
                  type="button"
                  className="adventure-session-picker__card-select"
                  onClick={() => onSelect(selectionFromSession(session))}
                >
                  {t("adventure.sourcePicker.selectCurrent")}
                </button>
              </article>
            );
          })}
        </div>
        {sessionsLoading && (
          <p className="adventure-session-picker__status">
            {t("gallery.loading")}
          </p>
        )}
        {sessionsHasMore && !sessionsLoading && (
          <button
            type="button"
            className="adventure-session-picker__load-more"
            onClick={handleLoadMoreSessions}
          >
            {t("gallery.loadMore")}
          </button>
        )}
        <div
          ref={sessionsSentinelRef}
          className="adventure-session-picker__sentinel"
        />
      </>
    );
  };

  const renderFavoritesTab = () => {
    if (favoritesError) {
      return (
        <p className="adventure-session-picker__status" role="alert">
          {t("gallery.genericError")}
          <button type="button" onClick={() => void loadFavorites(1)}>
            {t("gallery.retry")}
          </button>
        </p>
      );
    }
    if (favorites.length === 0) {
      if (favoritesLoading || !favoritesFetchedOnce) {
        return (
          <p className="adventure-session-picker__status">
            {t("gallery.loading")}
          </p>
        );
      }
      return (
        <div className="adventure-session-picker__empty">
          <p>{t("favorites.empty")}</p>
          <small>{t("favorites.emptyHint")}</small>
        </div>
      );
    }
    return (
      <>
        <div
          className="adventure-session-picker__grid"
          role="group"
          aria-label={t("gallery.tabFavorites")}
        >
          {favorites.map((fav) => {
            const isSelected =
              selected?.origin === "favorite" &&
              selected.sessionId === fav.session_id &&
              selected.historyId === fav.history_id;
            return (
              <button
                type="button"
                key={fav.id}
                className={isSelected ? "is-selected" : ""}
                data-selected={isSelected || undefined}
                onClick={() =>
                  onSelect({
                    sessionId: fav.session_id,
                    historyId: fav.history_id,
                    characterName: characterNameFor(fav.session_id),
                    thumbnailUrl: fav.image_url,
                    pointLabel: fav.label ?? fav.instruction,
                    origin: "favorite",
                  })
                }
              >
                <span className="adventure-session-picker__thumb">
                  <img src={mediaUrl(fav.image_url)} alt="" />
                </span>
                <span className="adventure-session-picker__tile-label">
                  {fav.label ?? fav.instruction}
                </span>
              </button>
            );
          })}
        </div>
        {favoritesLoading && (
          <p className="adventure-session-picker__status">
            {t("gallery.loading")}
          </p>
        )}
        {favoritesHasMore && !favoritesLoading && (
          <button
            type="button"
            className="adventure-session-picker__load-more"
            onClick={handleLoadMoreFavorites}
          >
            {t("gallery.loadMore")}
          </button>
        )}
        <div
          ref={favoritesSentinelRef}
          className="adventure-session-picker__sentinel"
        />
      </>
    );
  };

  return (
    <div
      className="adventure-session-picker"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className="adventure-session-picker__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adventure-session-picker-title"
      >
        <header>
          <h2 id="adventure-session-picker-title">{title}</h2>
          <button
            type="button"
            className="adventure-scenario-modal__close"
            aria-label={t("adventure.sourcePicker.close")}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        {drilldownSession ? (
          <div className="adventure-session-picker__drill-header">
            <button type="button" onClick={() => setDrilldownSession(null)}>
              {t("gallery.backToSessions")}
            </button>
            <strong>
              {drilldownSession.character_name ??
                t("adventure.unnamedCharacter")}
            </strong>
          </div>
        ) : (
          <>
            <div className="adventure-scenario-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "sessions"}
                className={tab === "sessions" ? "is-active" : ""}
                onClick={() => setTab("sessions")}
              >
                {t("gallery.tabSessions")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "favorites"}
                className={tab === "favorites" ? "is-active" : ""}
                onClick={() => setTab("favorites")}
              >
                {t("gallery.tabFavorites")}
              </button>
            </div>
            {tab === "sessions" && (
              <div className="adventure-session-picker__search">
                <input
                  ref={searchInputRef}
                  type="search"
                  value={searchInput}
                  placeholder={t("gallery.searchPlaceholder")}
                  aria-label={t("gallery.searchAria")}
                  onChange={(event) => setSearchInput(event.target.value)}
                />
                {searchInput && (
                  <button
                    type="button"
                    aria-label={t("gallery.searchClear")}
                    onClick={() => {
                      setSearchInput("");
                      setSearchQuery("");
                    }}
                  >
                    ×
                  </button>
                )}
              </div>
            )}
          </>
        )}
        <div className="adventure-session-picker__body" ref={setContentEl}>
          {drilldownSession ? (
            <SessionHistoryList
              key={drilldownSession.session_id}
              session={drilldownSession}
              root={contentEl}
              selected={selected}
              onSelect={onSelect}
            />
          ) : tab === "sessions" ? (
            renderSessionsTab()
          ) : (
            renderFavoritesTab()
          )}
        </div>
      </section>
    </div>
  );
}
