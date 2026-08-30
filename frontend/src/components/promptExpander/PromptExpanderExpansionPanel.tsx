/**
 * PromptExpanderExpansionPanel - 拡張結果のインライン確認カード
 *
 * 拡張した欄（正プロンプト / ネガティブ）の直下に表示し、結果を編集してから
 * 「欄へ反映」「この内容で生成」「破棄」のいずれかを選ぶ。
 * target が一致する pendingExpansion があるときだけ描画する。
 */

import { useEffect, useState } from "react";
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
    pendingExpansion,
    applyExpansion,
    generateFromExpansion,
    discardExpansion,
    generating,
    positiveText,
  } = usePromptExpander();

  const [positive, setPositive] = useState("");
  const [characters, setCharacters] = useState<string[] | null>(null);
  const [negative, setNegative] = useState("");

  const active = pendingExpansion?.target === target ? pendingExpansion : null;

  // 拡張結果が届くたびに編集欄を初期化する
  useEffect(() => {
    if (!active) return;
    setPositive(active.positivePrompt ?? "");
    setCharacters(active.characterPrompts);
    setNegative(active.negativePrompt ?? "");
  }, [active]);

  if (!active) return null;

  const isPositive = target === "positive";
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
              onChange={(e) => setPositive(e.target.value)}
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
                  setCharacters((prev) =>
                    prev
                      ? prev.map((p, i) => (i === index ? e.target.value : p))
                      : prev,
                  )
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
            onChange={(e) => setNegative(e.target.value)}
          />
        </div>
      )}
      <div className="prompt-expander__expansion-actions">
        <button
          type="button"
          className="prompt-expander__btn"
          onClick={discardExpansion}
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
