/**
 * PromptExpanderSourcePickerModal - 生成元（i2i 元）／精密参照画像の選択モーダル
 *
 * TSFシナリオの開始素材と同じ AdventureSessionPickerModal を使い、
 * セッション・お気に入り・Prompt Expander・キャラクターの4タブから選ばせる。
 * - Prompt Expander エントリ: kind="entry"
 * - セッション／お気に入り: kind="history"。「現在の状態」は fetchSessionFrames で最新履歴 ID に解決する
 * - キャラクター: 立ち絵を取り込み kind="upload" で渡す（バックエンドにキャラクター用の種類は無い）
 * target="reference" のときは選択結果を i2i 元ではなく精密参照の画像に入れる。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchSessionFrames } from "../../apis/gallery";
import { promptExpanderImageUrl } from "../../apis/promptExpander";
import {
  type PromptExpanderPickerTarget,
  type PromptExpanderSource,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import { fetchMediaBlob, readBlobAsDataUrl } from "../../utils/mediaImage";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import "./PromptExpanderShared.css";
import "./PromptExpanderPicker.css";

interface PromptExpanderSourcePickerModalProps {
  open: boolean;
  onClose: () => void;
  /** 選択結果の入れ先（既定は i2i 元） */
  target?: PromptExpanderPickerTarget;
}

/** 選択中のエントリをモーダルの「選択中」表示とグリッドのハイライトに渡す形にする */
function toPickerSelection(
  current: PromptExpanderSource | null,
): AdventureSourceSelection | null {
  if (current?.kind !== "entry" || !current.entryId) return null;
  return {
    sessionId: "",
    historyId: undefined,
    promptExpanderEntryId: current.entryId,
    characterName: null,
    thumbnailUrl: current.thumbnailUrl,
    pointLabel: current.label || null,
    origin: "prompt_expander",
  };
}

export default function PromptExpanderSourcePickerModal({
  open,
  onClose,
  target = "source",
}: PromptExpanderSourcePickerModalProps) {
  const { t } = useTranslation();
  const { source, reference, setSource, setReference } = usePromptExpander();
  const current = target === "reference" ? reference : source;
  const assign = target === "reference" ? setReference : setSource;
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const handleEntrySelect = (selection: AdventureSourceSelection) => {
    if (!selection.promptExpanderEntryId) return;
    assign({
      kind: "entry",
      entryId: selection.promptExpanderEntryId,
      thumbnailUrl: promptExpanderImageUrl(selection.thumbnailUrl),
      label: selection.pointLabel?.trim() || selection.promptExpanderEntryId,
    });
    onClose();
  };

  const handleCharacterSelect = async (selection: AdventureSourceSelection) => {
    setBusyLabel(t("promptExpander.picker.loadingCharacter"));
    try {
      const blob = await fetchMediaBlob(selection.thumbnailUrl);
      const dataUrl = await readBlobAsDataUrl(blob);
      assign({
        kind: "upload",
        uploadDataUrl: dataUrl,
        thumbnailUrl: dataUrl,
        label:
          selection.characterName?.trim() ||
          t("promptExpander.picker.characterLabelFallback"),
      });
      onClose();
    } catch (err) {
      console.error("Failed to load the character portrait", err);
      setResolveError(t("promptExpander.picker.characterLoadFailed"));
    } finally {
      setBusyLabel(null);
    }
  };

  const handlePlaySelect = async (selection: AdventureSourceSelection) => {
    let historyId = selection.historyId ?? null;
    let thumbnailUrl = selection.thumbnailUrl;
    if (!historyId) {
      // 「現在の状態」= セッションの最新履歴
      setBusyLabel(t("promptExpander.picker.resolving"));
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
        setBusyLabel(null);
      }
    }
    const label =
      selection.pointLabel?.trim() ||
      selection.characterName?.trim() ||
      t("promptExpander.picker.playLabelFallback");
    assign({
      kind: "history",
      historyId,
      thumbnailUrl: promptExpanderImageUrl(thumbnailUrl),
      label,
    });
    onClose();
  };

  const handleSelect = (selection: AdventureSourceSelection) => {
    setResolveError(null);
    if (selection.origin === "prompt_expander") {
      handleEntrySelect(selection);
    } else if (selection.origin === "character") {
      void handleCharacterSelect(selection);
    } else {
      void handlePlaySelect(selection);
    }
  };

  if (!open) return null;

  return (
    <>
      <AdventureSessionPickerModal
        title={
          target === "reference"
            ? t("promptExpander.picker.titleReference")
            : t("promptExpander.picker.title")
        }
        selected={toPickerSelection(current)}
        onSelect={handleSelect}
        onClose={onClose}
        allowPromptExpander
        characters="tab"
        defaultTab="prompt_expander"
        busyLabel={busyLabel}
      />
      {resolveError && (
        <div className="prompt-expander__picker-overlay" role="alert">
          <div className="prompt-expander__picker-overlay-error">
            <p className="prompt-expander__error">{resolveError}</p>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={() => setResolveError(null)}
            >
              {t("promptExpander.picker.close")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
