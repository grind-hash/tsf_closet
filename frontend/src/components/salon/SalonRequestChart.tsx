import { useTranslation } from "react-i18next";
import type { SessionRequestView } from "../../types";
import {
  type SalonPreferenceChip,
  salonSatisfactionDelta,
} from "../../utils/salonView";

/**
 * HUD の満足度。数値・達成の線入りのメーターと、前の施術からの増減を出す。
 * 施術するまでは数値が無いので「—」にする。
 */
export function SalonSatisfactionTile({
  request,
}: {
  request: SessionRequestView;
}) {
  const { t } = useTranslation();
  const evaluated = request.evaluated_turns > 0;
  const satisfaction = Math.max(0, Math.min(100, request.satisfaction));
  const threshold = Math.max(0, Math.min(100, request.threshold));
  const delta = salonSatisfactionDelta(request);
  const label = evaluated
    ? t("salon.serving.satisfactionMeter", { satisfaction, threshold })
    : t("salon.serving.satisfactionBefore");
  return (
    <div
      className={`salon-hud__tile salon-hud__satisfaction${
        evaluated && satisfaction >= threshold ? " is-reached" : ""
      }`}
      title={label}
    >
      <span>{t("salon.serving.satisfaction")}</span>
      <strong>
        {evaluated ? `${satisfaction}%` : "—"}
        {delta !== null && (
          <small
            className={`salon-delta${
              delta > 0 ? " is-up" : delta < 0 ? " is-down" : ""
            }`}
          >
            {delta > 0
              ? t("salon.serving.satisfactionUp", { delta })
              : delta < 0
                ? t("salon.serving.satisfactionDown", { delta: -delta })
                : t("salon.serving.satisfactionSame")}
          </small>
        )}
      </strong>
      <span
        className="salon-satisfaction-meter"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={evaluated ? satisfaction : 0}
      >
        <span style={{ width: `${evaluated ? satisfaction : 0}%` }} />
        <i style={{ left: `${threshold}%` }} aria-hidden />
      </span>
    </div>
  );
}

/**
 * カルテ。お客様が口にしていない好みの分類を並べ、叶えた好みに印を付ける。
 * onAsk を渡すと(カウンセリング)、分類を押してその好みについて質問を書ける。
 */
export function SalonPreferenceChart({
  chips,
  onAsk,
  selectedId = null,
  disabled = false,
}: {
  chips: SalonPreferenceChip[];
  onAsk?: (chip: SalonPreferenceChip) => void;
  selectedId?: string | null;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  if (chips.length === 0) return null;
  return (
    <div className="salon-karte">
      <span className="salon-karte__label">{t("salon.serving.chart")}</span>
      <ul className="salon-karte__list">
        {chips.map((chip) => {
          const status = chip.met
            ? t("salon.serving.chartMet")
            : chip.focus
              ? t("salon.serving.chartFocus")
              : t("salon.serving.chartPending");
          const className = `salon-karte__chip${chip.met ? " is-met" : ""}${
            chip.focus ? " is-focus" : ""
          }${selectedId === chip.id ? " is-selected" : ""}`;
          const body = (
            <>
              <span className="salon-karte__mark" aria-hidden>
                {chip.met ? "✓" : chip.focus ? "◆" : "・"}
              </span>
              <span className="salon-karte__category">{chip.category}</span>
              {chip.met && chip.text && (
                <small className="salon-karte__text">{chip.text}</small>
              )}
              {onAsk && chip.asked && (
                <small className="salon-karte__asked">
                  {t("salon.serving.chartAsked")}
                </small>
              )}
              <span className="salon-sr-only">{status}</span>
            </>
          );
          return (
            <li key={chip.id}>
              {onAsk ? (
                <button
                  type="button"
                  className={className}
                  disabled={disabled}
                  aria-pressed={selectedId === chip.id}
                  onClick={() => onAsk(chip)}
                >
                  {body}
                </button>
              ) : (
                <span className={className}>{body}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
