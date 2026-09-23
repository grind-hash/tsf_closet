/**
 * PromptExpanderEntryGrid - 全セッション横断のエントリグリッド（選択用）
 *
 * fetchPromptExpanderEntries でページングし、末尾までスクロールすると追加読み込みする
 * （「もっと見る」ボタンも残す）。
 * Prompt Expander 内の生成元選択と、後続の WelcomeScreen / Adventure の選択 UI で再利用する。
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  fetchPromptExpanderEntries,
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import { PROMPT_EXPANDER_ALPHA_OPTIONS } from "../../constants/promptExpander";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import "./PromptExpanderShared.css";
import "./PromptExpanderPicker.css";

const PAGE_SIZE = 24;

/** いちばん近い縦スクロールの祖先。呼び出し元（各モーダルの本体）を問わず監視できるようにする */
function findScrollParent(node: HTMLElement): Element | null {
  for (let el = node.parentElement; el; el = el.parentElement) {
    const { overflowY } = getComputedStyle(el);
    if (overflowY === "auto" || overflowY === "scroll") return el;
  }
  return null;
}

/** サムネイル。透過エントリはカードと同じ設定で背景を切り抜く（結果はキャッシュを共有） */
function GridImage({ entry }: { entry: PromptExpanderEntry }) {
  const originalUrl = promptExpanderImageUrl(entry);
  const { url } = useTransparentImage(
    originalUrl,
    entry.transparent_background,
    PROMPT_EXPANDER_ALPHA_OPTIONS,
  );
  // 読み込みに失敗した blob URL は原本へ戻す（表示中は保持されるので通常は起きない）
  const [brokenUrl, setBrokenUrl] = useState<string | null>(null);
  const src = url && url !== brokenUrl ? url : originalUrl;
  return (
    <img src={src} alt="" loading="lazy" onError={() => setBrokenUrl(src)} />
  );
}

interface PromptExpanderEntryGridProps {
  selectedEntryId?: string | null;
  onSelect: (entry: PromptExpanderEntry) => void;
}

export default function PromptExpanderEntryGrid({
  selectedEntryId,
  onSelect,
}: PromptExpanderEntryGridProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<PromptExpanderEntry[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(async (nextPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPromptExpanderEntries(nextPage, PAGE_SIZE);
      setItems((prev) =>
        nextPage === 1 ? data.items : [...prev, ...data.items],
      );
      setPage(data.page);
      setHasMore(data.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPage(1);
  }, [loadPage]);

  const [scrollRoot, setScrollRoot] = useState<Element | null>(null);
  const wrapRef = useCallback((node: HTMLDivElement | null) => {
    setScrollRoot(node ? findScrollParent(node) : null);
  }, []);
  const sentinelRef = useInfiniteScroll({
    enabled: hasMore && !loading && !error && items.length > 0,
    onLoadMore: () => void loadPage(page + 1),
    root: scrollRoot,
  });

  return (
    <div className="prompt-expander__entry-grid-wrap" ref={wrapRef}>
      {error && (
        <p className="prompt-expander__error" role="alert">
          {error}
        </p>
      )}
      {items.length === 0 && !loading && !error ? (
        <p className="prompt-expander__empty">
          {t("promptExpander.picker.empty")}
        </p>
      ) : (
        <ul className="prompt-expander__entry-grid">
          {items.map((entry) => {
            const selected = entry.id === selectedEntryId;
            const label =
              entry.instruction?.trim() ||
              entry.final_prompt?.trim() ||
              t("promptExpander.entry.uploadedNoText");
            return (
              <li key={entry.id}>
                {/* 画像を <button> で包むと右クリックの画像保存が効かないため div[role=button] にする */}
                <div
                  className={`prompt-expander__entry-grid-item ${selected ? "is-selected" : ""} ${entry.transparent_background ? "is-transparent" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(entry)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(entry);
                    }
                  }}
                  aria-pressed={selected}
                  title={label}
                >
                  <GridImage entry={entry} />
                  <span className="prompt-expander__entry-grid-label">
                    {label}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {loading && (
        <p className="prompt-expander__hint">
          {t("promptExpander.picker.loading")}
        </p>
      )}
      {hasMore && !loading && (
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--block"
          onClick={() => void loadPage(page + 1)}
        >
          {t("promptExpander.picker.loadMore")}
        </button>
      )}
      <div
        ref={sentinelRef}
        className="prompt-expander__entry-grid-sentinel"
        aria-hidden
      />
    </div>
  );
}
