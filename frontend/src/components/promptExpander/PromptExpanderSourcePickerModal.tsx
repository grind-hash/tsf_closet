/**
 * PromptExpanderSourcePickerModal - 生成元（i2i 元）の選択モーダル
 *
 * タブ「Prompt Expander」: 全セッション横断のエントリグリッド
 * タブ「プレイセッション」: AdventureSessionPickerModal を再利用し、
 *   「現在の状態」が選ばれた場合は fetchSessionFrames で最新履歴 ID を解決する。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchSessionFrames } from "../../apis/gallery";
import {
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import { API_BASE } from "../../utils/api";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import PromptExpanderEntryGrid from "./PromptExpanderEntryGrid";
import PromptExpanderModal from "./PromptExpanderModal";
import "./PromptExpanderShared.css";
import "./PromptExpanderPicker.css";

type PickerTab = "entries" | "play";

interface PromptExpanderSourcePickerModalProps {
  open: boolean;
  onClose: () => void;
}

function galleryMediaUrl(url: string): string {
  if (!url) return url;
  if (
    url.startsWith("data:") ||
    url.startsWith("http://") ||
    url.startsWith("https://") ||
    url.startsWith(`${API_BASE}/`)
  ) {
    return url;
  }
  return url.startsWith("/") ? `${API_BASE}${url}` : `${API_BASE}/${url}`;
}

export default function PromptExpanderSourcePickerModal({
  open,
  onClose,
}: PromptExpanderSourcePickerModalProps) {
  const { t } = useTranslation();
  const { source, setSource } = usePromptExpander();
  const [tab, setTab] = useState<PickerTab>("entries");
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const handleEntrySelect = (entry: PromptExpanderEntry) => {
    setSource({
      kind: "entry",
      entryId: entry.id,
      thumbnailUrl: promptExpanderImageUrl(entry),
      label:
        entry.instruction?.trim() || entry.final_prompt?.trim() || entry.id,
    });
    onClose();
  };

  const handlePlaySelect = async (selection: AdventureSourceSelection) => {
    setResolveError(null);
    let historyId = selection.historyId ?? null;
    let thumbnailUrl = selection.thumbnailUrl;
    if (!historyId) {
      // 「現在の状態」= セッションの最新履歴
      setResolving(true);
      try {
        const frames = await fetchSessionFrames(selection.sessionId);
        const latest = frames[frames.length - 1];
        if (!latest) {
          setResolveError(t("promptExpander.picker.noHistory"));
          return;
        }
        historyId = latest.id;
        thumbnailUrl = latest.image_url || thumbnailUrl;
      } catch (err) {
        setResolveError(err instanceof Error ? err.message : String(err));
        return;
      } finally {
        setResolving(false);
      }
    }
    const label =
      selection.pointLabel?.trim() ||
      selection.characterName?.trim() ||
      t("promptExpander.picker.playLabelFallback");
    setSource({
      kind: "history",
      historyId,
      thumbnailUrl: galleryMediaUrl(thumbnailUrl),
      label,
    });
    onClose();
  };

  if (!open) return null;

  // プレイセッションタブは既存のピッカーモーダルをそのまま表示する
  if (tab === "play") {
    return (
      <>
        <AdventureSessionPickerModal
          title={t("promptExpander.picker.playTitle")}
          selected={null}
          onSelect={(selection) => void handlePlaySelect(selection)}
          onClose={() => {
            if (resolving) return;
            setTab("entries");
          }}
        />
        {(resolving || resolveError) && (
          <div className="prompt-expander__picker-overlay" role="status">
            {resolving ? (
              <p className="prompt-expander__notice">
                {t("promptExpander.picker.resolving")}
              </p>
            ) : (
              <div className="prompt-expander__picker-overlay-error">
                <p className="prompt-expander__error" role="alert">
                  {resolveError}
                </p>
                <button
                  type="button"
                  className="prompt-expander__btn prompt-expander__btn--sm"
                  onClick={() => setResolveError(null)}
                >
                  {t("promptExpander.picker.close")}
                </button>
              </div>
            )}
          </div>
        )}
      </>
    );
  }

  return (
    <PromptExpanderModal
      open={open}
      title={t("promptExpander.picker.title")}
      onClose={onClose}
      closeLabel={t("promptExpander.picker.close")}
      size="lg"
    >
      <div className="prompt-expander__picker-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "entries"}
          className={`prompt-expander__picker-tab ${tab === "entries" ? "is-active" : ""}`}
          onClick={() => setTab("entries")}
        >
          {t("promptExpander.picker.tabEntries")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={false}
          className="prompt-expander__picker-tab"
          onClick={() => setTab("play")}
        >
          {t("promptExpander.picker.tabPlay")}
        </button>
      </div>
      <PromptExpanderEntryGrid
        selectedEntryId={source?.kind === "entry" ? source.entryId : null}
        onSelect={handleEntrySelect}
      />
    </PromptExpanderModal>
  );
}
