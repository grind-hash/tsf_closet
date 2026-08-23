/**
 * PromptExpanderSuggestModal - メモリから好みのキャラクターを提案するモーダル
 *
 * 件数（1〜5）とモード（日本語/タグ）を選んで提案を取得し、各提案を
 * 選択したスロット / 新規スロット（キャラクターモード ON）またはプロンプト欄（OFF）へ挿入する。
 * メモリが空（memory_empty）のときは設定の「メモリ情報を持ってくる」への案内を出す。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PromptExpanderApiError,
  type PromptExpanderSuggestion,
} from "../../apis/promptExpander";
import type { PromptExpandMode } from "../../constants/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import PromptExpanderModal from "./PromptExpanderModal";
import "./PromptExpanderShared.css";
import "./PromptExpanderSuggestModal.css";

interface PromptExpanderSuggestModalProps {
  open: boolean;
  onClose: () => void;
}

const NEW_SLOT = "new";

export default function PromptExpanderSuggestModal({
  open,
  onClose,
}: PromptExpanderSuggestModalProps) {
  const { t } = useTranslation();
  const {
    suggestCharacters,
    suggesting,
    characterMode,
    characterSlots,
    maxCharacterPrompts,
    addCharacterSlot,
    updateCharacterSlot,
    positiveText,
    setPositiveText,
    positiveMode,
  } = usePromptExpander();
  const [count, setCount] = useState(3);
  const [mode, setMode] = useState<PromptExpandMode>(positiveMode);
  const [suggestions, setSuggestions] = useState<PromptExpanderSuggestion[]>(
    [],
  );
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [target, setTarget] = useState<string>(NEW_SLOT);
  const [insertedIndex, setInsertedIndex] = useState<number | null>(null);

  useEffect(() => {
    if (open) {
      setSuggestions([]);
      setErrorCode(null);
      setErrorMessage(null);
      setInsertedIndex(null);
      setMode(positiveMode);
      setTarget(NEW_SLOT);
    }
  }, [open, positiveMode]);

  const handleRun = async () => {
    setErrorCode(null);
    setErrorMessage(null);
    setInsertedIndex(null);
    try {
      const result = await suggestCharacters(count, mode);
      setSuggestions(result);
    } catch (err) {
      if (err instanceof PromptExpanderApiError) {
        setErrorCode(err.code);
        setErrorMessage(err.message);
      } else {
        setErrorMessage(err instanceof Error ? err.message : String(err));
      }
    }
  };

  const atMax = characterSlots.length >= maxCharacterPrompts;

  const handleInsert = (
    suggestion: PromptExpanderSuggestion,
    index: number,
  ) => {
    if (characterMode) {
      if (target === NEW_SLOT) {
        if (atMax) return;
        addCharacterSlot(suggestion.prompt);
      } else {
        const slotIndex = Number.parseInt(target, 10);
        if (!Number.isNaN(slotIndex)) {
          updateCharacterSlot(slotIndex, suggestion.prompt);
        }
      }
    } else {
      const sep = positiveText.trim() ? "\n" : "";
      setPositiveText(`${positiveText}${sep}${suggestion.prompt}`);
    }
    setInsertedIndex(index);
  };

  return (
    <PromptExpanderModal
      open={open}
      title={t("promptExpander.suggest.title")}
      onClose={onClose}
      closeLabel={t("promptExpander.suggest.close")}
      footer={
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={onClose}
        >
          {t("promptExpander.suggest.close")}
        </button>
      }
    >
      <div className="prompt-expander__suggest-controls">
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-suggest-count"
          >
            {t("promptExpander.suggest.count")}
          </label>
          <select
            id="prompt-expander-suggest-count"
            className="prompt-expander__select"
            value={count}
            onChange={(e) => setCount(Number.parseInt(e.target.value, 10))}
            disabled={suggesting}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="prompt-expander__field">
          <span className="prompt-expander__label">
            {t("promptExpander.suggest.mode")}
          </span>
          <div className="prompt-expander__radio-group" role="radiogroup">
            {(["japanese", "tags"] as PromptExpandMode[]).map((m) => (
              <label
                key={m}
                className={`prompt-expander__radio ${mode === m ? "is-active" : ""}`}
              >
                <input
                  type="radio"
                  name="prompt-expander-suggest-mode"
                  value={m}
                  checked={mode === m}
                  onChange={() => setMode(m)}
                  disabled={suggesting}
                />
                {m === "japanese"
                  ? t("promptExpander.composer.expandJapanese")
                  : t("promptExpander.composer.expandTags")}
              </label>
            ))}
          </div>
        </div>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--primary"
          onClick={() => void handleRun()}
          disabled={suggesting}
        >
          {suggesting
            ? t("promptExpander.suggest.running")
            : t("promptExpander.suggest.run")}
        </button>
      </div>

      {characterMode && (
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-suggest-target"
          >
            {t("promptExpander.suggest.insertTarget")}
          </label>
          <select
            id="prompt-expander-suggest-target"
            className="prompt-expander__select"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value={NEW_SLOT}>
              {t("promptExpander.suggest.newSlot")}
            </option>
            {characterSlots.map((slot, index) => (
              <option
                // biome-ignore lint/suspicious/noArrayIndexKey: スロットの並び順を保ち、テキストは重複しうる
                key={`target-${index}`}
                value={String(index)}
              >
                {t("promptExpander.suggest.slotN", {
                  index: index + 1,
                  preview: slot.trim()
                    ? slot.trim().slice(0, 24)
                    : t("promptExpander.suggest.emptySlot"),
                })}
              </option>
            ))}
          </select>
          {target === NEW_SLOT && atMax && (
            <span className="prompt-expander__hint prompt-expander__hint--warning">
              {t("promptExpander.composer.addSlotMax", {
                max: maxCharacterPrompts,
              })}
            </span>
          )}
        </div>
      )}
      {!characterMode && (
        <p className="prompt-expander__hint">
          {t("promptExpander.suggest.intoPrompt")}
        </p>
      )}

      {errorCode === "memory_empty" ? (
        <div className="prompt-expander__notice" role="alert">
          <p className="prompt-expander__suggest-error-title">
            {t("promptExpander.suggest.memoryEmpty")}
          </p>
          <p className="prompt-expander__suggest-error-hint">
            {t("promptExpander.suggest.memoryEmptyHint")}
          </p>
        </div>
      ) : errorMessage ? (
        <p className="prompt-expander__error" role="alert">
          {errorMessage}
        </p>
      ) : null}

      {suggestions.length > 0 ? (
        <ul className="prompt-expander__suggest-list">
          {suggestions.map((suggestion, index) => (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: 同名の提案が返ることがある
              key={`${suggestion.title}-${index}`}
              className="prompt-expander__suggest-item"
            >
              <div className="prompt-expander__suggest-item-main">
                <strong className="prompt-expander__suggest-item-title">
                  {suggestion.title}
                </strong>
                <p className="prompt-expander__suggest-item-prompt">
                  {suggestion.prompt}
                </p>
              </div>
              <button
                type="button"
                className={`prompt-expander__btn prompt-expander__btn--sm ${insertedIndex === index ? "prompt-expander__btn--primary" : ""}`}
                onClick={() => handleInsert(suggestion, index)}
                disabled={characterMode && target === NEW_SLOT && atMax}
              >
                {insertedIndex === index
                  ? t("promptExpander.suggest.inserted")
                  : t("promptExpander.suggest.insert")}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        !suggesting &&
        !errorMessage && (
          <p className="prompt-expander__hint">
            {t("promptExpander.suggest.empty")}
          </p>
        )
      )}
    </PromptExpanderModal>
  );
}
