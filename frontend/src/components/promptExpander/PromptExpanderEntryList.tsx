/**
 * PromptExpanderEntryList - セッション内のエントリ一覧（新しい順）
 *
 * 一覧は開閉セクション（history）に入れ、画像クリックで ImagePreviewModal を
 * 大きめ（prompt-expander-preview）に開き、前後のエントリへ移動できる。
 * 一覧上部の絞り込みチップ（すべて / 通常 / 漫画 / アップロード）は localStorage に保持し、
 * プレビューの前後移動と「n / N」表示も絞り込み後の並びで行う。
 * プレビュー中（閉じた直後も）のカードは強調し、移動に合わせてスクロールして位置を見失わないようにする。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import ImagePreviewModal from "../ImagePreviewModal";
import PromptExpanderEntryCard from "./PromptExpanderEntryCard";
import PromptExpanderProgress from "./PromptExpanderProgress";
import PromptExpanderSection from "./PromptExpanderSection";
import "./PromptExpanderShared.css";
import "./PromptExpanderEntryList.css";

export const PROMPT_EXPANDER_ENTRY_FILTER_KEY = "prompt_expander_entry_filter";

const ENTRY_FILTERS = ["all", "normal", "manga", "uploaded"] as const;
export type PromptExpanderEntryFilter = (typeof ENTRY_FILTERS)[number];
type PromptExpanderEntryFacet = Exclude<PromptExpanderEntryFilter, "all">;

function isEntryFilter(value: unknown): value is PromptExpanderEntryFilter {
  return (
    typeof value === "string" &&
    (ENTRY_FILTERS as readonly string[]).includes(value)
  );
}

function readPersistedFilter(): PromptExpanderEntryFilter {
  try {
    const raw = localStorage.getItem(PROMPT_EXPANDER_ENTRY_FILTER_KEY);
    return isEntryFilter(raw) ? raw : "all";
  } catch {
    return "all";
  }
}

function writePersistedFilter(filter: PromptExpanderEntryFilter) {
  try {
    localStorage.setItem(PROMPT_EXPANDER_ENTRY_FILTER_KEY, filter);
  } catch {
    // localStorage が使えない環境では保持しない
  }
}

/** エントリの分類。アップロードは kind、それ以外は漫画モードの印で分ける */
export function classifyEntry(
  entry: PromptExpanderEntry,
): PromptExpanderEntryFacet {
  if (entry.kind === "uploaded") return "uploaded";
  return entry.manga_mode ? "manga" : "normal";
}

function escapeSelector(value: string): string {
  return typeof CSS !== "undefined" && typeof CSS.escape === "function"
    ? CSS.escape(value)
    : value;
}

export default function PromptExpanderEntryList() {
  const { t } = useTranslation();
  const { entries, activeSession, loadingSession, generating } =
    usePromptExpander();
  const [filter, setFilterState] =
    useState<PromptExpanderEntryFilter>(readPersistedFilter);
  // プレビュー対象は id で持つ（閉じた後も強調を残し、絞り込みや削除で並びが変わっても追従できる）
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const counts = useMemo(() => {
    const result: Record<PromptExpanderEntryFilter, number> = {
      all: entries.length,
      normal: 0,
      manga: 0,
      uploaded: 0,
    };
    for (const entry of entries) {
      result[classifyEntry(entry)] += 1;
    }
    return result;
  }, [entries]);

  const filteredEntries = useMemo(
    () =>
      filter === "all"
        ? entries
        : entries.filter((entry) => classifyEntry(entry) === filter),
    [entries, filter],
  );

  const setFilter = useCallback((next: PromptExpanderEntryFilter) => {
    setFilterState(next);
    writePersistedFilter(next);
    // 並びが変わるのでプレビュー位置は捨てる
    setPreviewOpen(false);
    setPreviewId(null);
  }, []);

  const previewIndex =
    previewId === null
      ? -1
      : filteredEntries.findIndex((entry) => entry.id === previewId);
  const previewEntry =
    previewOpen && previewIndex >= 0
      ? (filteredEntries[previewIndex] ?? null)
      : null;

  const openPreview = useCallback((entryId: string) => {
    setPreviewId(entryId);
    setPreviewOpen(true);
  }, []);

  const movePreview = useCallback(
    (delta: 1 | -1) => {
      if (previewIndex < 0) return;
      const next = filteredEntries[previewIndex + delta];
      if (next) setPreviewId(next.id);
    },
    [filteredEntries, previewIndex],
  );

  // プレビューで移動した先のカードを一覧上でも見つけられるようスクロールする
  useEffect(() => {
    if (!previewId) return;
    const card = document.querySelector<HTMLElement>(
      `[data-entry-id="${escapeSelector(previewId)}"]`,
    );
    card?.scrollIntoView?.({ block: "nearest" });
  }, [previewId]);

  return (
    <div className="prompt-expander__entries">
      <PromptExpanderSection
        id="history"
        headingLevel="h2"
        className="prompt-expander__entries-section"
        title={activeSession?.title || t("promptExpander.sessions.untitled")}
        toolbar={
          <span className="prompt-expander__hint">
            {t("promptExpander.sessions.entryCount", {
              count: activeSession?.entry_count ?? entries.length,
            })}
          </span>
        }
      >
        {generating && (
          <PromptExpanderProgress
            className="prompt-expander__progress--block"
            label={t("promptExpander.entry.generatingNotice")}
          />
        )}

        {entries.length > 0 && (
          <div
            className="prompt-expander__entry-filters"
            role="group"
            aria-label={t("promptExpander.entry.filterLabel")}
          >
            {ENTRY_FILTERS.map((key) => (
              <button
                key={key}
                type="button"
                className={`prompt-expander__entry-filter-chip${filter === key ? " is-active" : ""}`}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                <span>{t(`promptExpander.entry.filter.${key}`)}</span>
                <span className="prompt-expander__entry-filter-count">
                  {counts[key]}
                </span>
              </button>
            ))}
          </div>
        )}

        {loadingSession && entries.length === 0 ? (
          <p className="prompt-expander__empty">
            {t("promptExpander.entry.loading")}
          </p>
        ) : entries.length === 0 ? (
          <p className="prompt-expander__empty">
            {t("promptExpander.entry.empty")}
          </p>
        ) : filteredEntries.length === 0 ? (
          <p className="prompt-expander__empty">
            {t("promptExpander.entry.filterEmpty")}
          </p>
        ) : (
          <ul className="prompt-expander__entry-list">
            {filteredEntries.map((entry) => (
              <PromptExpanderEntryCard
                key={entry.id}
                entry={entry}
                onPreview={(e) => openPreview(e.id)}
                isPreviewed={previewId === entry.id}
              />
            ))}
          </ul>
        )}
      </PromptExpanderSection>

      <ImagePreviewModal
        className="prompt-expander-preview"
        isOpen={previewEntry !== null}
        imageUrl={previewEntry ? promptExpanderImageUrl(previewEntry) : null}
        onClose={() => setPreviewOpen(false)}
        alt={previewEntry?.instruction ?? previewEntry?.final_prompt ?? ""}
        positionLabel={
          previewEntry
            ? `${previewIndex + 1} / ${filteredEntries.length}`
            : undefined
        }
        hasPrev={previewIndex >= 0 && previewIndex < filteredEntries.length - 1}
        hasNext={previewIndex > 0}
        onPrev={() => movePreview(1)}
        onNext={() => movePreview(-1)}
        caption={
          previewEntry ? (
            <span className="prompt-expander__preview-caption">
              {previewEntry.final_prompt || previewEntry.instruction || ""}
            </span>
          ) : undefined
        }
      />
    </div>
  );
}
