/**
 * PromptExpanderEntryList - セッション内のエントリ一覧（新しい順）
 *
 * 一覧は開閉セクション（history）に入れ、画像クリックで ImagePreviewModal を
 * 大きめ（prompt-expander-preview）に開き、前後のエントリへ移動できる。
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { promptExpanderImageUrl } from "../../apis/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import ImagePreviewModal from "../ImagePreviewModal";
import PromptExpanderEntryCard from "./PromptExpanderEntryCard";
import PromptExpanderSection from "./PromptExpanderSection";
import "./PromptExpanderShared.css";
import "./PromptExpanderEntryList.css";

export default function PromptExpanderEntryList() {
  const { t } = useTranslation();
  const { entries, activeSession, loadingSession, generating } =
    usePromptExpander();
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const previewEntry =
    previewIndex !== null ? (entries[previewIndex] ?? null) : null;

  const openPreview = useCallback(
    (entryId: string) => {
      const index = entries.findIndex((e) => e.id === entryId);
      if (index >= 0) setPreviewIndex(index);
    },
    [entries],
  );

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
          <p className="prompt-expander__notice" role="status">
            {t("promptExpander.entry.generatingNotice")}
          </p>
        )}

        {loadingSession && entries.length === 0 ? (
          <p className="prompt-expander__empty">
            {t("promptExpander.entry.loading")}
          </p>
        ) : entries.length === 0 ? (
          <p className="prompt-expander__empty">
            {t("promptExpander.entry.empty")}
          </p>
        ) : (
          <ul className="prompt-expander__entry-list">
            {entries.map((entry) => (
              <PromptExpanderEntryCard
                key={entry.id}
                entry={entry}
                onPreview={(e) => openPreview(e.id)}
              />
            ))}
          </ul>
        )}
      </PromptExpanderSection>

      <ImagePreviewModal
        className="prompt-expander-preview"
        isOpen={previewEntry !== null}
        imageUrl={previewEntry ? promptExpanderImageUrl(previewEntry) : null}
        onClose={() => setPreviewIndex(null)}
        alt={previewEntry?.instruction ?? previewEntry?.final_prompt ?? ""}
        hasPrev={previewIndex !== null && previewIndex < entries.length - 1}
        hasNext={previewIndex !== null && previewIndex > 0}
        onPrev={() =>
          setPreviewIndex((i) =>
            i !== null && i < entries.length - 1 ? i + 1 : i,
          )
        }
        onNext={() => setPreviewIndex((i) => (i !== null && i > 0 ? i - 1 : i))}
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
