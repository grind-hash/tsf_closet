import { type RefObject, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { SalonVisit } from "../../apis/salon";
import { useCountUp } from "../../hooks/useCountUp";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import {
  formatSignedNumber,
  formatSignedYen,
  formatYen,
} from "../../utils/salonView";

/** 会計の演出の段取り(ms)。満足度 → お支払い → 封蝋 → 支払いが現金へ飛ぶ、の順 */
const SATISFACTION_DELAY_MS = 200;
const PAYMENT_DELAY_MS = 500;
const COUNT_MS = 900;
const CHIP_DELAY_MS = 1500;
const CHIP_FLIGHT_MS = 800;
/** 支払いのチップが HUD の現金に届く時刻。HUD の現金はここから数え上げる */
export const RECEIPT_CASH_ARRIVAL_MS = CHIP_DELAY_MS + CHIP_FLIGHT_MS * 0.85;

interface SalonReceiptProps {
  visit: SalonVisit;
  language: string;
  /** 会計した直後だけ演出する。済んだ来店を開き直したときは最終値だけ見せる */
  celebrate: boolean;
  /** 支払いのチップが飛んでいく先(HUD の現金) */
  cashTarget: RefObject<HTMLElement | null>;
}

/** 接客の会計の領収書(満足度・お支払い・評判と、願いを叶えたかどうか) */
export default function SalonReceipt({
  visit,
  language,
  celebrate,
  cashTarget,
}: SalonReceiptProps) {
  const { t } = useTranslation();
  const reducedMotion = usePrefersReducedMotion();
  const paymentRef = useRef<HTMLElement>(null);
  const satisfactionTarget = visit.satisfaction ?? 0;
  const satisfaction = useCountUp(satisfactionTarget, {
    from: celebrate ? 0 : satisfactionTarget,
    durationMs: COUNT_MS,
    delayMs: SATISFACTION_DELAY_MS,
  });
  const payment = useCountUp(visit.payment, {
    from: celebrate ? 0 : visit.payment,
    durationMs: COUNT_MS,
    delayMs: PAYMENT_DELAY_MS,
  });
  const sealText = t("salon.serving.seal");

  return (
    <div className={`salon-receipt-sheet${celebrate ? " is-celebrating" : ""}`}>
      <dl className="salon-receipt">
        <div>
          <dt>{t("salon.serving.satisfaction")}</dt>
          <dd className="salon-receipt__big">{satisfaction}%</dd>
        </div>
        {visit.extra_cost > 0 && (
          <div>
            <dt>{t("salon.serving.extraCost")}</dt>
            <dd>{formatSignedYen(-visit.extra_cost, language)}</dd>
          </div>
        )}
        {visit.experience_bonus > 0 && (
          <div>
            <dt>{t("salon.serving.experienceBonus")}</dt>
            <dd>+{visit.experience_bonus}%</dd>
          </div>
        )}
        <div>
          <dt>{t("salon.serving.payment")}</dt>
          <dd ref={paymentRef}>{formatYen(payment, language)}</dd>
        </div>
        <div>
          <dt>{t("salon.serving.reputation")}</dt>
          <dd>{formatSignedNumber(visit.reputation_delta)}</dd>
        </div>
      </dl>
      <div className="salon-receipt__result">
        <p
          className={`salon-receipt__verdict${visit.fulfilled ? " is-fulfilled" : ""}`}
        >
          {t(
            visit.fulfilled
              ? "salon.serving.fulfilled"
              : visit.experience_bonus > 0
                ? "salon.serving.notFulfilledAfterExperience"
                : "salon.serving.notFulfilled",
          )}
        </p>
        {visit.fulfilled && (
          <span
            className={`salon-receipt__seal${sealText.length > 3 ? " is-long" : ""}`}
            aria-hidden
          >
            {sealText}
          </span>
        )}
      </div>
      {(visit.kept_look || !visit.fulfilled) && (
        <p className="salon-receipt__look">
          {t(
            visit.kept_look
              ? "salon.serving.keptLook"
              : visit.experience_bonus > 0
                ? "salon.serving.revertedAfterExperience"
                : "salon.serving.revertedLook",
          )}
        </p>
      )}
      {celebrate && !reducedMotion && visit.payment > 0 && (
        <PaymentChip
          text={formatSignedYen(visit.payment, language)}
          from={paymentRef}
          to={cashTarget}
        />
      )}
    </div>
  );
}

/**
 * お支払いの額を、領収書から HUD の現金へ飛ばす飾り。
 * 祖先の transform に位置をずらされないよう body に置き、Web Animations API で動かす。
 */
function PaymentChip({
  text,
  from,
  to,
}: {
  text: string;
  from: RefObject<HTMLElement | null>;
  to: RefObject<HTMLElement | null>;
}) {
  const chipRef = useRef<HTMLSpanElement>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const chip = chipRef.current;
    const start = from.current?.getBoundingClientRect();
    const end = to.current?.getBoundingClientRect();
    if (!chip || !start || !end || typeof chip.animate !== "function") {
      setDone(true);
      return;
    }
    const startX = start.left + start.width / 2;
    const startY = start.top + start.height / 2;
    const dx = end.left + end.width / 2 - startX;
    const dy = end.top + end.height / 2 - startY;
    chip.style.left = `${startX}px`;
    chip.style.top = `${startY}px`;
    const animation = chip.animate(
      [
        { transform: "translate(-50%, -50%) scale(0.8)", opacity: 0 },
        {
          transform: "translate(-50%, -110%) scale(1.05)",
          opacity: 1,
          offset: 0.2,
        },
        {
          transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(0.7)`,
          opacity: 1,
          offset: 0.85,
        },
        {
          transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(0.5)`,
          opacity: 0,
        },
      ],
      {
        duration: CHIP_FLIGHT_MS,
        delay: CHIP_DELAY_MS,
        easing: "ease-in-out",
        fill: "both",
      },
    );
    animation.onfinish = () => setDone(true);
    return () => animation.cancel();
  }, [from, to]);

  if (done) return null;
  return createPortal(
    <span ref={chipRef} className="salon-payment-chip" aria-hidden>
      {text}
    </span>,
    document.body,
  );
}
