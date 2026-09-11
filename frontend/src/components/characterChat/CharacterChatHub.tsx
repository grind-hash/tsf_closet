import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type {
  CharacterChatKind,
  CharacterChatThread,
} from "../../apis/characterChat";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useCharacterChatPortraitPreference } from "../../hooks/useCharacterChatPortraitPreference";
import { usePersistedState } from "../../hooks/usePersistedState";
import type { TranslationKey } from "../../i18n";
import { ROUTES } from "../../routes";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";

/** 「会話の続き」一覧の絞り込み。"all" 以外はスレッドの kind と一致する */
export type CharacterChatThreadFilter = "all" | CharacterChatKind;

export const CHARACTER_CHAT_THREAD_FILTER_KEY = "character_chat_thread_filter";

const THREAD_FILTERS: readonly CharacterChatThreadFilter[] = [
  "all",
  "base",
  "session",
  "adventure",
];

const KIND_LABEL_KEY: Record<CharacterChatKind, TranslationKey> = {
  base: "characterChat.hub.kindBase",
  session: "characterChat.hub.kindSession",
  adventure: "characterChat.hub.kindAdventure",
};

function isThreadFilter(value: string): value is CharacterChatThreadFilter {
  return (THREAD_FILTERS as readonly string[]).includes(value);
}

/**
 * キャラチャットの入口。案内役キャラ(セレナ)のカード、「セッションから作る」、
 * 既存スレッドの一覧(種類で絞り込み可能)を並べる。
 */
export default function CharacterChatHub() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const {
    threads,
    threadsLoading,
    threadLoading,
    error,
    clearError,
    refreshThreads,
    openBase,
    createFromSource,
    deleteThread,
  } = useCharacterChat();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [generatePortrait, setGeneratePortrait] =
    useCharacterChatPortraitPreference();
  const [deleteTarget, setDeleteTarget] = useState<CharacterChatThread | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);
  const [filter, setFilter] = usePersistedState<CharacterChatThreadFilter>(
    CHARACTER_CHAT_THREAD_FILTER_KEY,
    "all",
    {
      serialize: (value) => value,
      deserialize: (raw) => (isThreadFilter(raw) ? raw : "all"),
    },
  );
  const filtersRef = useRef<HTMLDivElement>(null);
  const focusedOnceRef = useRef(false);

  useEffect(() => {
    void refreshThreads();
  }, [refreshThreads]);

  const baseThread = threads.find((thread) => thread.kind === "base") ?? null;

  // 案内役を先頭に、残りはサーバーの並び(更新順)のまま
  const orderedThreads = useMemo(
    () => [
      ...threads.filter((thread) => thread.kind === "base"),
      ...threads.filter((thread) => thread.kind !== "base"),
    ],
    [threads],
  );

  const counts = useMemo(() => {
    const result: Record<CharacterChatThreadFilter, number> = {
      all: threads.length,
      base: 0,
      session: 0,
      adventure: 0,
    };
    for (const thread of threads) {
      result[thread.kind] += 1;
    }
    return result;
  }, [threads]);

  const filteredThreads = useMemo(
    () =>
      filter === "all"
        ? orderedThreads
        : orderedThreads.filter((thread) => thread.kind === filter),
    [orderedThreads, filter],
  );

  // 一覧が出た時点で、復元した選択中チップへフォーカスを移す(初回のみ)
  useEffect(() => {
    if (focusedOnceRef.current || threads.length === 0) return;
    const active = filtersRef.current?.querySelector<HTMLButtonElement>(
      'button[aria-pressed="true"]',
    );
    if (!active) return;
    focusedOnceRef.current = true;
    active.focus({ preventScroll: true });
  }, [threads.length]);

  const handleOpenBase = async () => {
    const id = await openBase();
    if (id) navigate(`${ROUTES.CHARACTER_CHAT}/${id}`);
  };

  const handleSelectSource = async (selection: AdventureSourceSelection) => {
    setPickerOpen(false);
    const id = await createFromSource(selection, { generatePortrait });
    if (id) navigate(`${ROUTES.CHARACTER_CHAT}/${id}`);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    const ok = await deleteThread(deleteTarget.id);
    setDeleting(false);
    if (ok) setDeleteTarget(null);
  };

  const formatDate = (value: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(i18n.language, {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <MainLayout>
      <div className="character-chat">
        <header className="character-chat__header">
          <h1>{t("characterChat.title")}</h1>
          <p className="character-chat__intro">
            {t("characterChat.hub.intro")}
          </p>
        </header>

        {error && (
          <div className="character-chat__error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={clearError}>
              ✕
            </button>
          </div>
        )}

        <div className="character-chat__hub-grid">
          <section className="character-chat__card character-chat__card--base">
            <h2>{t("characterChat.hub.baseSection")}</h2>
            <div className="character-chat__base">
              <div className="character-chat__base-portrait">
                {baseThread?.portrait_url ? (
                  <img src={baseThread.portrait_url} alt="" />
                ) : (
                  <span className="character-chat__placeholder" aria-hidden>
                    💬
                  </span>
                )}
              </div>
              <div className="character-chat__base-body">
                <p>{t("characterChat.hub.baseIntro")}</p>
                <button
                  type="button"
                  className="character-chat__primary"
                  disabled={threadLoading}
                  onClick={handleOpenBase}
                >
                  {threadLoading
                    ? t("characterChat.hub.creating")
                    : t("characterChat.hub.openBase")}
                </button>
              </div>
            </div>
          </section>

          <section className="character-chat__card">
            <h2>{t("characterChat.hub.createSection")}</h2>
            <p>{t("characterChat.hub.createIntro")}</p>
            <button
              type="button"
              className="character-chat__secondary"
              disabled={threadLoading}
              onClick={() => setPickerOpen(true)}
            >
              {t("characterChat.hub.createButton")}
            </button>
            <label className="character-chat__switch-row character-chat__switch-row--card">
              <span className="character-chat__switch-info">
                <strong>{t("characterChat.hub.generatePortraitToggle")}</strong>
                <small>
                  {t("characterChat.hub.generatePortraitToggleHint")}
                </small>
              </span>
              <input
                type="checkbox"
                className="character-chat__switch-input"
                checked={generatePortrait}
                onChange={(event) => setGeneratePortrait(event.target.checked)}
              />
              <span className="character-chat__switch" />
            </label>
          </section>
        </div>

        <section className="character-chat__card">
          <h2>{t("characterChat.hub.threadsSection")}</h2>
          {threadsLoading && threads.length === 0 ? (
            <div className="character-chat__progress" role="status">
              <span />
              {t("characterChat.hub.loading")}
            </div>
          ) : threads.length === 0 ? (
            <p className="character-chat__empty">
              {t("characterChat.hub.threadsEmpty")}
            </p>
          ) : (
            <>
              <div
                ref={filtersRef}
                className="character-chat__thread-filters"
                role="group"
                aria-label={t("characterChat.hub.filterLabel")}
              >
                {THREAD_FILTERS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className={`character-chat__thread-filter-chip${filter === key ? " is-active" : ""}`}
                    aria-pressed={filter === key}
                    onClick={() => setFilter(key)}
                  >
                    <span>{t(`characterChat.hub.filter.${key}`)}</span>
                    <span className="character-chat__thread-filter-count">
                      {counts[key]}
                    </span>
                  </button>
                ))}
              </div>
              {filteredThreads.length === 0 ? (
                <p className="character-chat__empty">
                  {t("characterChat.hub.filterEmpty")}
                </p>
              ) : (
                <ul className="character-chat__thread-list">
                  {filteredThreads.map((thread) => (
                    <li key={thread.id} className="character-chat__thread-row">
                      <button
                        type="button"
                        className="character-chat__thread-open"
                        onClick={() =>
                          navigate(`${ROUTES.CHARACTER_CHAT}/${thread.id}`)
                        }
                      >
                        <span className="character-chat__thread-thumb">
                          {thread.portrait_url ? (
                            <img src={thread.portrait_url} alt="" />
                          ) : (
                            <span aria-hidden>💬</span>
                          )}
                        </span>
                        <span className="character-chat__thread-text">
                          <strong>{thread.name}</strong>
                          <span className="character-chat__thread-last">
                            {thread.last_message?.content ||
                              t("characterChat.hub.lastMessageEmpty")}
                          </span>
                          <span className="character-chat__thread-meta">
                            {formatDate(thread.updated_at)} ·{" "}
                            {t("characterChat.hub.messageCount", {
                              count: thread.message_count,
                            })}
                          </span>
                        </span>
                      </button>
                      <span
                        className={`character-chat__chip character-chat__chip--${thread.kind}`}
                      >
                        {t(KIND_LABEL_KEY[thread.kind])}
                      </span>
                      <button
                        type="button"
                        className="character-chat__delete"
                        aria-label={t("characterChat.hub.delete")}
                        title={t("characterChat.hub.delete")}
                        onClick={() => setDeleteTarget(thread)}
                      >
                        <svg
                          viewBox="0 0 24 24"
                          width="18"
                          height="18"
                          aria-hidden="true"
                        >
                          <path
                            fill="currentColor"
                            d="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9zm4 2v8h2v-8h-2zm4 0v8h2v-8h-2z"
                          />
                        </svg>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>

      {pickerOpen && (
        <AdventureSessionPickerModal
          title={t("characterChat.hub.pickerTitle")}
          selected={null}
          onSelect={handleSelectSource}
          onClose={() => setPickerOpen(false)}
          allowPromptExpander={settingsState.experimentalPromptExpanderEnabled}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("characterChat.hub.deleteTitle")}
        confirmLabel={t("characterChat.hub.deleteConfirm")}
        cancelLabel={t("characterChat.hub.cancel")}
        busy={deleting}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      >
        {t("characterChat.hub.deleteBody", { name: deleteTarget?.name ?? "" })}
      </ConfirmDialog>
    </MainLayout>
  );
}
