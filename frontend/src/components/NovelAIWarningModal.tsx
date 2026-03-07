/**
 * NovelAI Warning Modal Component
 *
 * NovelAIプロバイダー利用時、非Opusプランユーザーに案内を表示するモーダル。
 * tier !== 3 の場合に表示され、続行またはキャンセルを選択できる。
 * tier === 0 (Free/Paper) の場合は未対応プランである旨を追加表示する。
 */

import { useTranslation } from "react-i18next";
import "./NovelAIWarningModal.css";

interface NovelAIWarningModalProps {
  tier: number;
  onContinue: () => void;
  onCancel: () => void;
}

const TIER_NAMES: Record<number, string> = {
  0: "Free (Paper)",
  1: "Tablet",
  2: "Scroll",
  3: "Opus",
};

export default function NovelAIWarningModal({
  tier,
  onContinue,
  onCancel,
}: NovelAIWarningModalProps) {
  const { t } = useTranslation();
  const tierName = TIER_NAMES[tier] ?? `Unknown (${tier})`;
  const isTrialTier = tier === 0;
  const title = isTrialTier
    ? t("novelaiWarning.titleUnsupported")
    : t("novelaiWarning.titleInfo");

  return (
    <div className="novelai-warning-overlay">
      <div className="novelai-warning-modal">
        <div className="novelai-warning-icon">⚠️</div>
        <h2>{title}</h2>

        <div className="novelai-warning-content">
          <p className="novelai-warning-plan">
            {t("novelaiWarning.currentPlan")}
            <strong>{tierName}</strong>
          </p>
          {isTrialTier && (
            <p className="novelai-warning-main">
              {t("novelaiWarning.unsupportedMessage")}
            </p>
          )}
          {!isTrialTier && (
            <p className="novelai-warning-detail">
              {t("novelaiWarning.recommendOpus")}
            </p>
          )}
        </div>

        <div className="novelai-warning-actions">
          {!isTrialTier && (
            <button
              type="button"
              className="novelai-warning-cancel"
              onClick={onCancel}
            >
              {t("novelaiWarning.cancel")}
            </button>
          )}
          <button
            type="button"
            className="novelai-warning-continue"
            onClick={isTrialTier ? onCancel : onContinue}
          >
            {isTrialTier
              ? t("novelaiWarning.close")
              : t("novelaiWarning.continue")}
          </button>
        </div>

        {!isTrialTier && (
          <p className="novelai-warning-note">{t("novelaiWarning.note")}</p>
        )}
      </div>
    </div>
  );
}
