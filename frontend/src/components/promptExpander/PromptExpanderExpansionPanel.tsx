/**
 * PromptExpanderExpansionPanel - ネガティブ欄の変換結果のインライン確認カード
 *
 * ネガティブ欄の直下に表示し、結果を手直ししてから「欄へ反映」「この内容で生成」「破棄」の
 * いずれかを選ぶ。変換カード（negativeExpansion）があるときだけ描画する。
 * 手直しした内容は Context に書き戻し、書きかけと一緒にセッションごとに保存する。
 * 正プロンプト側はカードを使わず、プロンプト化の結果をプロンプト欄へ直接入れる。
 */

import { useTranslation } from "react-i18next";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import "./PromptExpanderShared.css";
import "./PromptExpanderComposer.css";

export default function PromptExpanderExpansionPanel() {
  const { t } = useTranslation();
  const {
    negativeExpansion,
    editNegativeExpansion,
    applyNegativeExpansion,
    generateFromNegativeExpansion,
    discardNegativeExpansion,
    generating,
    positiveText,
  } = usePromptExpander();

  if (!negativeExpansion) return null;

  // ネガティブ拡張からの生成はプロンプト欄が埋まっている必要がある
  const canGenerate = positiveText.trim().length > 0;
  const title = t("promptExpander.expansion.titleNegative");

  return (
    <section className="prompt-expander__expansion" aria-label={title}>
      <div className="prompt-expander__expansion-head">
        <h4 className="prompt-expander__expansion-title">{title}</h4>
        <span className="prompt-expander__badge prompt-expander__badge--accent">
          {negativeExpansion.mode === "japanese"
            ? t("promptExpander.composer.expandJapanese")
            : t("promptExpander.composer.expandTags")}
        </span>
      </div>
      <p className="prompt-expander__hint">
        {t("promptExpander.expansion.hint")}
      </p>
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
          value={negativeExpansion.negativePrompt}
          onChange={(e) => editNegativeExpansion(e.target.value)}
        />
      </div>
      <div className="prompt-expander__expansion-actions">
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={discardNegativeExpansion}
          disabled={generating}
        >
          {t("promptExpander.expansion.discard")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={applyNegativeExpansion}
          disabled={generating}
        >
          {t("promptExpander.composer.applyExpansion")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--primary"
          disabled={generating || !canGenerate}
          title={
            canGenerate
              ? undefined
              : t("promptExpander.composer.disabledEmptyPrompt")
          }
          onClick={() => void generateFromNegativeExpansion()}
        >
          {generating
            ? t("promptExpander.composer.generating")
            : t("promptExpander.expansion.confirm")}
        </button>
      </div>
      {!canGenerate && (
        <span className="prompt-expander__hint prompt-expander__hint--warning">
          {t("promptExpander.composer.disabledEmptyPrompt")}
        </span>
      )}
    </section>
  );
}
