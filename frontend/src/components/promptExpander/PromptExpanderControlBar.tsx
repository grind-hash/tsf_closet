/**
 * PromptExpanderControlBar - 画面下部の常時表示コントロールエリア
 *
 * セクションを複数開くとページが伸びて「生成」がスクロールの外へ出てしまうため、
 * 生成操作と現在の設定サマリをスクロールしない下端の帯にまとめる。
 * Anlas と V5 上限も、生成の直前に見られるようここに常に出す（見出しはスクロールで隠れるため）。
 * 値はすべて PromptExpanderContext から取り、props は増やさない。
 */

import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
import { getPromptExpanderImageModelLabel } from "../../constants/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import {
  revealPromptExpanderSection,
  setAllPromptExpanderSections,
  usePromptExpanderSectionsAllOpen,
} from "../../hooks/usePersistedSectionState";
import { hasApiKeyConsent } from "../apiKeyConsentStorage";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
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
    sendableReferences,
    transparentActive,
    mangaActive,
    inpaintActive,
    anlas,
    activeSession,
    lastGenerateOutcome,
    dismissGenerateOutcome,
    requestEntryReveal,
  } = usePromptExpander();
  const navigate = useNavigate();

  // 「結果を見る」: 開始元のセッションへ移ってから、生成履歴で新着のエントリを見せる
  const showGeneratedEntry = () => {
    if (lastGenerateOutcome?.status !== "success") return;
    if (activeSession?.id !== lastGenerateOutcome.sessionId) {
      navigate(`/prompt-expander/${lastGenerateOutcome.sessionId}`);
    }
    requestEntryReveal(lastGenerateOutcome.entryId);
  };
  // 「詳細を見る」: 画面上部のエラー行へ移る
  const showGenerateError = () => {
    const row = document.querySelector<HTMLElement>(
      ".prompt-expander__error-row",
    );
    row?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    row?.focus({ preventScroll: true });
  };
  const usage =
    isV5ImageModel(settings.image_model) && anlas?.usage ? anlas.usage : null;
  const sectionsAllOpen = usePromptExpanderSectionsAllOpen();

  const disabledReasonText = useDisabledReasonText(generateDisabledReason);
  const busy = generating || expanding || draftingScript;

  // Ctrl+Shift+Enter（Mac は ⌘+Shift+Enter）で生成する。ダイアログを開いている間と
  // 変換中の入力では反応しない（確認ダイアログの裏で生成が走らないように）
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "Enter" ||
        !event.shiftKey ||
        !(event.ctrlKey || event.metaKey) ||
        event.isComposing
      ) {
        return;
      }
      // API キーの利用同意前は生成しない（同意画面は背後のキー操作を止めないため、ここでも見る）
      if (!hasApiKeyConsent()) return;
      if (document.querySelector('[role="dialog"]')) return;
      event.preventDefault();
      if (canGenerate) void runGenerate();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canGenerate, runGenerate]);

  // セクションを閉じていても、何で生成されるかがひと目で分かるようにする。
  // チップを押すとその設定のセクションを開いて移る（長い画面で欄を探す往復を減らす）
  const summaryChips = useMemo(() => {
    const chips: { label: string; section: string }[] = [
      {
        label: getPromptExpanderImageModelLabel(settings.image_model),
        section: "params",
      },
      {
        label: t(`promptExpander.composer.size.${settings.image_size}`),
        section: "params",
      },
    ];
    if (transparentActive) {
      chips.push({
        label: t("promptExpander.controlBar.chipTransparent"),
        section: "params",
      });
    }
    if (mangaActive) {
      chips.push({
        label: t("promptExpander.controlBar.chipManga"),
        section: "manga",
      });
    }
    if (inpaintActive) {
      chips.push({
        label: t("promptExpander.controlBar.chipInpaint"),
        section: "inpaint",
      });
    }
    if (referenceActive) {
      chips.push({
        label: t("promptExpander.controlBar.chipReference"),
        section: "reference",
      });
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
            <button
              key={chip.label}
              type="button"
              className="prompt-expander__badge prompt-expander__summary-chip"
              onClick={() => revealPromptExpanderSection(chip.section)}
              title={t("promptExpander.controlBar.chipJumpTitle", {
                label: chip.label,
              })}
            >
              {chip.label}
            </button>
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
        {/* 直近の生成の成否。入力位置を保ったまま、結果やエラーへ移れるようにする */}
        {!generating && lastGenerateOutcome && (
          <span
            className={`prompt-expander__control-bar-outcome prompt-expander__hint${lastGenerateOutcome.status === "error" ? " prompt-expander__hint--warning" : ""}`}
            role="status"
          >
            <span>
              {lastGenerateOutcome.status === "success"
                ? t("promptExpander.controlBar.outcomeSuccess")
                : t("promptExpander.controlBar.outcomeError")}
            </span>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={
                lastGenerateOutcome.status === "success"
                  ? showGeneratedEntry
                  : showGenerateError
              }
              title={
                lastGenerateOutcome.status === "error"
                  ? lastGenerateOutcome.message
                  : undefined
              }
            >
              {lastGenerateOutcome.status === "success"
                ? t("promptExpander.controlBar.outcomeShowResult")
                : t("promptExpander.controlBar.outcomeShowError")}
            </button>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__control-bar-outcome-close"
              onClick={dismissGenerateOutcome}
              aria-label={t("promptExpander.controlBar.outcomeDismiss")}
              title={t("promptExpander.controlBar.outcomeDismiss")}
            >
              ×
            </button>
          </span>
        )}
        {disabledReasonText && !busy && (
          <span className="prompt-expander__hint prompt-expander__hint--warning">
            {disabledReasonText}
          </span>
        )}
        {usage && (
          <NovelaiUsageBar
            usage={usage}
            compact
            className="prompt-expander__control-bar-usage"
          />
        )}
        {anlas && (
          <span
            className="prompt-expander__control-bar-anlas"
            title={t("promptExpander.header.anlasTitle")}
          >
            {t("promptExpander.header.anlas", {
              value: anlas.totalAnlas.toLocaleString(),
            })}
          </span>
        )}
        {referenceActive && (
          <span
            className="prompt-expander__generate-cost"
            title={t("promptExpander.composer.referenceCostTotalHint", {
              count: sendableReferences.length,
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
          title={
            disabledReasonText ?? t("promptExpander.controlBar.generateTitle")
          }
        >
          {generating
            ? t("promptExpander.composer.generating")
            : t("promptExpander.composer.generate")}
        </button>
      </div>
    </div>
  );
}
