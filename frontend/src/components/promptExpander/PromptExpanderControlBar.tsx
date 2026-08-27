/**
 * PromptExpanderControlBar - 画面下部の常時表示コントロールエリア
 *
 * セクションを複数開くとページが伸びて「生成」がスクロールの外へ出てしまうため、
 * 生成操作と現在の設定サマリをスクロールしない下端の帯にまとめる。
 * 値はすべて PromptExpanderContext から取り、props は増やさない。
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getPromptExpanderImageModelLabel } from "../../constants/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import {
  setAllPromptExpanderSections,
  usePromptExpanderSectionsAllOpen,
} from "../../hooks/usePersistedSectionState";
import PromptExpanderProgress from "./PromptExpanderProgress";
import "./PromptExpanderShared.css";
import "./PromptExpanderControlBar.css";

/** 生成できない理由コードを文言へ変換する（コンポーザから移設） */
function useDisabledReasonText(reason: string | null): string | null {
  const { t } = useTranslation();
  switch (reason) {
    case "novelai_not_configured":
      return t("promptExpander.composer.disabledNotConfigured");
    case "no_session":
      return t("promptExpander.composer.disabledNoSession");
    case "too_many_characters":
      return t("promptExpander.composer.disabledTooMany");
    case "empty_prompt":
      return t("promptExpander.composer.disabledEmptyPrompt");
    case "pending_expansion":
      return t("promptExpander.composer.disabledPendingExpansion");
    default:
      return null;
  }
}

export default function PromptExpanderControlBar() {
  const { t } = useTranslation();
  const {
    settings,
    runGenerate,
    canGenerate,
    generateDisabledReason,
    generating,
    expanding,
    draftingScript,
    referenceActive,
    referenceAnlasCost,
    transparentActive,
    mangaActive,
    inpaintActive,
  } = usePromptExpander();
  const sectionsAllOpen = usePromptExpanderSectionsAllOpen();

  const disabledReasonText = useDisabledReasonText(generateDisabledReason);
  const busy = generating || expanding || draftingScript;

  // セクションを閉じていても、何で生成されるかがひと目で分かるようにする
  const summaryChips = useMemo(() => {
    const chips: string[] = [
      getPromptExpanderImageModelLabel(settings.image_model),
      t(`promptExpander.composer.size.${settings.image_size}`),
    ];
    if (transparentActive) {
      chips.push(t("promptExpander.controlBar.chipTransparent"));
    }
    if (mangaActive) chips.push(t("promptExpander.controlBar.chipManga"));
    if (inpaintActive) chips.push(t("promptExpander.controlBar.chipInpaint"));
    if (referenceActive) {
      chips.push(t("promptExpander.controlBar.chipReference"));
    }
    return chips;
  }, [
    inpaintActive,
    mangaActive,
    referenceActive,
    settings.image_model,
    settings.image_size,
    t,
    transparentActive,
  ]);

  return (
    <div
      className="prompt-expander__control-bar"
      role="toolbar"
      aria-label={t("promptExpander.controlBar.label")}
    >
      <div className="prompt-expander__control-bar-left">
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm"
          onClick={() => setAllPromptExpanderSections(!sectionsAllOpen)}
        >
          {sectionsAllOpen
            ? t("promptExpander.controlBar.collapseAll")
            : t("promptExpander.controlBar.expandAll")}
        </button>
        <div className="prompt-expander__control-bar-summary">
          {summaryChips.map((chip) => (
            <span key={chip} className="prompt-expander__badge">
              {chip}
            </span>
          ))}
        </div>
      </div>

      <div className="prompt-expander__control-bar-right">
        {generating && (
          <PromptExpanderProgress
            label={t("promptExpander.composer.generatingHint")}
            className="prompt-expander__control-bar-progress"
          />
        )}
        {disabledReasonText && !busy && (
          <span className="prompt-expander__hint prompt-expander__hint--warning">
            {disabledReasonText}
          </span>
        )}
        {referenceActive && (
          <span
            className="prompt-expander__generate-cost"
            title={t("promptExpander.composer.referenceCostHint", {
              cost: referenceAnlasCost,
            })}
          >
            {t("promptExpander.composer.referenceCostBadge", {
              cost: referenceAnlasCost,
            })}
          </span>
        )}
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--primary prompt-expander__generate"
          disabled={!canGenerate}
          onClick={() => void runGenerate()}
          title={disabledReasonText ?? undefined}
        >
          {generating
            ? t("promptExpander.composer.generating")
            : t("promptExpander.composer.generate")}
        </button>
      </div>
    </div>
  );
}
