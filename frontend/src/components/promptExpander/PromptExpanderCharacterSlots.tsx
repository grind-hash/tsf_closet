/**
 * PromptExpanderCharacterSlots - キャラクタープロンプト欄
 *
 * 「n / max」のカウンタ、追加（上限で無効化 + 理由）、各スロットのテキストエリアと削除。
 * メモリからの提案はセクション見出しの「提案」ボタン（Composer 側）から開く。
 */

import { useTranslation } from "react-i18next";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import PromptExpanderDeleteButton from "./PromptExpanderDeleteButton";
import "./PromptExpanderShared.css";
import "./PromptExpanderComposer.css";

export default function PromptExpanderCharacterSlots() {
  const { t } = useTranslation();
  const {
    characterSlots,
    characterSlotsOverCap,
    maxCharacterPrompts,
    addCharacterSlot,
    updateCharacterSlot,
    removeCharacterSlot,
    settings,
    expandingTarget,
    characterMode,
  } = usePromptExpander();

  const atMax = characterSlots.length >= maxCharacterPrompts;
  // キャラクターモードでの正プロンプト化中はスロットも結果で置き換わるため、編集を止める
  const slotsBusy = expandingTarget === "positive" && characterMode;

  return (
    <div className="prompt-expander__slots">
      <div className="prompt-expander__slots-header">
        <span className="prompt-expander__slots-counter">
          {t("promptExpander.composer.characterCounter", {
            count: characterSlots.length,
            max: maxCharacterPrompts,
          })}
        </span>
        <div className="prompt-expander__slots-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => addCharacterSlot()}
            disabled={atMax || slotsBusy}
            title={
              atMax
                ? t("promptExpander.composer.addSlotMax", {
                    max: maxCharacterPrompts,
                  })
                : undefined
            }
          >
            {t("promptExpander.composer.addSlot")}
          </button>
        </div>
      </div>
      {atMax && !characterSlotsOverCap && (
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.addSlotMax", {
            max: maxCharacterPrompts,
          })}
        </p>
      )}
      {characterSlotsOverCap && (
        <p className="prompt-expander__hint prompt-expander__hint--warning">
          {t("promptExpander.composer.overCapWarning", {
            max: maxCharacterPrompts,
            model: settings.image_model,
          })}
        </p>
      )}
      {characterSlots.length === 0 ? (
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.noSlots")}
        </p>
      ) : (
        <ol className="prompt-expander__slot-list">
          {characterSlots.map((slot, index) => (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: スロットは並び順が意味を持ち、テキストは重複しうる
              key={`slot-${index}`}
              className={`prompt-expander__slot ${index >= maxCharacterPrompts ? "prompt-expander__slot--over" : ""}`}
            >
              <span className="prompt-expander__slot-index">{index + 1}</span>
              <textarea
                className={`prompt-expander__textarea prompt-expander__slot-textarea${slotsBusy ? " prompt-expander__textarea--busy" : ""}`}
                value={slot}
                rows={2}
                readOnly={slotsBusy}
                aria-busy={slotsBusy}
                onChange={(e) => updateCharacterSlot(index, e.target.value)}
                placeholder={t("promptExpander.composer.slotPlaceholder")}
                aria-label={t("promptExpander.composer.slotLabel", {
                  index: index + 1,
                })}
              />
              <PromptExpanderDeleteButton
                label={t("promptExpander.composer.removeSlot", {
                  index: index + 1,
                })}
                onClick={() => removeCharacterSlot(index)}
                disabled={slotsBusy}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
