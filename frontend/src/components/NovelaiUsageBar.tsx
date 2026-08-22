import { useTranslation } from "react-i18next";
import type { NovelAIUsage } from "../types";
import "./NovelaiUsageBar.css";

interface NovelaiUsageBarProps {
  usage: NovelAIUsage;
  compact?: boolean;
  className?: string;
}

/**
 * NovelAI V5 の利用上限バー。
 * 表示可否（実効モデルが V5 かどうか等）の判断は親コンポーネントが行う。
 */
export function NovelaiUsageBar({
  usage,
  compact = false,
  className,
}: NovelaiUsageBarProps) {
  const { t } = useTranslation();
  const exhausted = usage.percent <= 0 || usage.isNegative;
  const percent = Math.max(0, Math.min(100, usage.percent));
  const classes = [
    "novelai-usage-bar",
    compact ? "novelai-usage-bar--compact" : "",
    exhausted ? "novelai-usage-bar--warning" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={classes}
      title={t("gameplay.novelaiUsageTooltip", {
        percent: usage.percent,
      })}
      data-testid="novelai-usage-bar"
    >
      <span className="novelai-usage-bar__label">
        {t("gameplay.novelaiUsageLabel")}
      </span>
      <span className="novelai-usage-bar__track">
        <i
          className="novelai-usage-bar__fill"
          style={{ width: `${percent}%` }}
        />
      </span>
      <span className="novelai-usage-bar__value">
        {exhausted ? t("gameplay.novelaiUsageExhausted") : `${usage.percent}%`}
      </span>
    </div>
  );
}
