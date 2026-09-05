/**
 * PromptExpanderEntryList - セッション内のエントリ一覧（新しい順）
 *
 * 一覧は開閉セクション（history）に入れ、画像クリックで ImagePreviewModal を
 * 大きめ（prompt-expander-preview）に開き、前後のエントリへ移動できる。
 * 一覧上部の絞り込みチップ（すべて / 通常 / 漫画 / アップロード）は localStorage に保持し、
 * プレビューの前後移動と「n / N」表示も絞り込み後の並びで行う。
 * プレビュー中（閉じた直後も）のカードは強調し、移動に合わせてスクロールして位置を見失わないようにする。
 * 背景透過エントリのプレビューはカードと同じく切り抜き後の画像を出す。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import { PROMPT_EXPANDER_ALPHA_OPTIONS } from "../../constants/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import { usePersistedState } from "../../hooks/usePersistedState";
import { useTransparentImage } from "../../hooks/useTransparentImage";
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
  const [filter, setFilterState] = usePersistedState<PromptExpanderEntryFilter>(
    PROMPT_EXPANDER_ENTRY_FILTER_KEY,
    "all",
    {
      serialize: (value) => value,
      deserialize: (raw) => (isEntryFilter(raw) ? raw : "all"),
    },
  );
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

  const setFilter = useCallback(
    (next: PromptExpanderEntryFilter) => {
      setFilterState(next);
      // 並びが変わるのでプレビュー位置は捨てる
      setPreviewOpen(false);
      setPreviewId(null);
    },
    [setFilterState],
  );

  const previewIndex =
    previewId === null
      ? -1
      : filteredEntries.findIndex((entry) => entry.id === previewId);
  const previewEntry =
    previewOpen && previewIndex >= 0
      ? (filteredEntries[previewIndex] ?? null)
      : null;
  // 透過エントリのプレビューは切り抜き後の画像を出す（カードと同じ設定なのでキャッシュを共有する）
  const previewOriginalUrl = previewEntry
    ? promptExpanderImageUrl(previewEntry)
    : null;
  const { url: previewTransparentUrl, processing: previewProcessing } =
    useTransparentImage(
      previewOriginalUrl,
      Boolean(previewEntry?.transparent_background),
      PROMPT_EXPANDER_ALPHA_OPTIONS,
    );
  const previewUrl =
    previewEntry?.transparent_background && previewTransparentUrl
      ? previewTransparentUrl
      : previewOriginalUrl;

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
        className={`prompt-expander-preview${previewEntry?.transparent_background ? " prompt-expander-preview--transparent" : ""}`}
        isOpen={previewEntry !== null}
        imageUrl={previewUrl}
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
            <>
              {previewProcessing && (
                <PromptExpanderProgress
                  className="prompt-expander__progress--block"
                  label={t("promptExpander.entry.transparentProcessing")}
                />
              )}
              <span className="prompt-expander__preview-caption">
                {previewEntry.final_prompt || previewEntry.instruction || ""}
              </span>
            </>
          ) : undefined
        }
      />
    </div>
  );
}
