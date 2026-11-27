/**
 * PromptExpanderExpansionPanel - 拡張結果のインライン確認カード
 *
 * 拡張した欄（正プロンプト / ネガティブ）の直下に表示し、結果を編集してから
 * 「欄へ反映」「この内容で生成」「破棄」のいずれかを選ぶ。
 * その欄の変換カード（pendingExpansions[target]）があるときだけ描画する。
 * 正プロンプトのカードは、変換したときの原文と今の欄の内容が違えば、そのことと再変換の操作を出す。
 * カードで手直しした内容は Context に書き戻し、書きかけと一緒にセッションごとに保存する。
 */

import { useTranslation } from "react-i18next";
import {
  type PromptExpanderExpansionTarget,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import "./PromptExpanderShared.css";
import "./PromptExpanderComposer.css";

interface PromptExpanderExpansionPanelProps {
  target: PromptExpanderExpansionTarget;
}

export default function PromptExpanderExpansionPanel({
  target,
}: PromptExpanderExpansionPanelProps) {
  const { t } = useTranslation();
  const {
    pendingExpansions,
    editPendingExpansion,
    applyExpansion,
    generateFromExpansion,
    discardExpansion,
    expandPositive,
    generating,
    expanding,
    draftingScript,
    positiveText,
  } = usePromptExpander();

  const active = pendingExpansions[target];

  if (!active) return null;

  const isPositive = target === "positive";
  const positive = active.positivePrompt ?? "";
  const characters = active.characterPrompts;
  const negative = active.negativePrompt ?? "";
  const edited = {
    ...active,
    positivePrompt: isPositive ? positive : null,
    characterPrompts: isPositive ? characters : null,
    negativePrompt: isPositive ? null : negative,
  };
  // ネガティブ拡張からの生成は正プロンプト欄が埋まっている必要がある
  const canGenerate = isPositive
    ? positive.trim().length > 0
    : positiveText.trim().length > 0;
  const title = isPositive
    ? t("promptExpander.expansion.titlePositive")
    : t("promptExpander.expansion.titleNegative");
  // 変換したあとで原文を直したか（この候補は直す前の原文から作られている）
  const instructionChanged =
    isPositive &&
    active.instruction !== null &&
    positiveText.trim().length > 0 &&
    positiveText.trim() !== active.instruction.trim();

  return (
    <section className="prompt-expander__expansion" aria-label={title}>
      <div className="prompt-expander__expansion-head">
        <h4 className="prompt-expander__expansion-title">{title}</h4>
        <span className="prompt-expander__badge prompt-expander__badge--accent">
          {active.mode === "japanese"
            ? t("promptExpander.composer.expandJapanese")
            : t("promptExpander.composer.expandTags")}
        </span>
      </div>
      <p className="prompt-expander__hint">
        {t("promptExpander.expansion.hint")}
      </p>
      {instructionChanged && (
        <p
          className="prompt-expander__hint prompt-expander__hint--warning prompt-expander__draft-done"
          role="status"
        >
          <span>{t("promptExpander.expansion.instructionChanged")}</span>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => void expandPositive()}
            disabled={generating || expanding || draftingScript}
          >
            {t("promptExpander.expansion.reExpand")}
          </button>
        </p>
      )}
      {isPositive ? (
        <>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-expansion-positive"
            >
              {t("promptExpander.expansion.basePrompt")}
            </label>
            <textarea
              id="prompt-expander-expansion-positive"
              className="prompt-expander__textarea"
              rows={5}
              value={positive}
              onChange={(e) =>
                editPendingExpansion(target, { positivePrompt: e.target.value })
              }
            />
          </div>
          {characters?.map((text, index) => (
            <div
              // biome-ignore lint/suspicious/noArrayIndexKey: 並び順がスロット番号に対応し、テキストは重複しうる
              key={`expanded-slot-${index}`}
              className="prompt-expander__field"
            >
              <label
                className="prompt-expander__label"
                htmlFor={`prompt-expander-expansion-char-${index}`}
              >
                {t("promptExpander.expansion.characterPrompt", {
                  index: index + 1,
                })}
              </label>
              <textarea
                id={`prompt-expander-expansion-char-${index}`}
                className="prompt-expander__textarea"
                rows={2}
                value={text}
                onChange={(e) =>
                  editPendingExpansion(target, {
                    characterPrompts: characters
                      ? characters.map((p, i) =>
                          i === index ? e.target.value : p,
                        )
                      : characters,
                  })
                }
              />
            </div>
          ))}
        </>
      ) : (
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-expansion-negative"
          >
            {t("promptExpander.expansion.negativePrompt")}
          </label>
          <textarea
            id="prompt-expander-expansion-negative"
            className="prompt-expander__textarea"
            rows={3}
            value={negative}
            onChange={(e) =>
              editPendingExpansion(target, { negativePrompt: e.target.value })
            }
          />
        </div>
      )}
      <div className="prompt-expander__expansion-actions">
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={() => discardExpansion(target)}
          disabled={generating}
        >
          {t("promptExpander.expansion.discard")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={() => applyExpansion(edited)}
          disabled={generating}
        >
          {t("promptExpander.composer.applyExpansion")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--primary"
          disabled={generating || !canGenerate}
          title={
            !canGenerate && !isPositive
              ? t("promptExpander.composer.disabledEmptyPrompt")
              : undefined
          }
          onClick={() => void generateFromExpansion(edited)}
        >
          {generating
            ? t("promptExpander.composer.generating")
            : t("promptExpander.expansion.confirm")}
        </button>
      </div>
      {!canGenerate && !isPositive && (
        <span className="prompt-expander__hint prompt-expander__hint--warning">
          {t("promptExpander.composer.disabledEmptyPrompt")}
        </span>
      )}
    </section>
  );
}
