import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AdventureRealityCost } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureRealityCostPanelProps {
  costs: AdventureRealityCost[];
  /** 過去の場面を表示中か。表示中は支払いを止める */
  viewingPast: boolean;
}

/**
 * HUD の「改変の代償」ポップオーバー本体。
 * 未解決を上、解決済みを下に並べ、romance の請求は所持金から支払える。
 */
export default function AdventureRealityCostPanel({
  costs,
  viewingPast,
}: AdventureRealityCostPanelProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, payRealityCost } = useAdventure();
  const [payingId, setPayingId] = useState<string | null>(null);
  if (!activeRun) return null;
  const sim = activeRun.preset === "romance" ? (activeRun.sim ?? null) : null;
  const active = costs.filter((cost) => cost.resolved_turn === null);
  const resolved = costs.filter((cost) => cost.resolved_turn !== null);
  const runOpen = activeRun.status === "active" && !activeRun.epilogue;

  // 支払えない理由。null なら支払える
  const payBlockReason = (cost: AdventureRealityCost): string | null => {
    if (!runOpen) return t("adventure.realityCost.cannotPayEnded");
    if (viewingPast) return t("adventure.realityCost.cannotPayPast");
    if (!activeRun.reality_cost_enabled) {
      return t("adventure.realityCost.cannotPayDisabled");
    }
    const money = sim?.money ?? 0;
    const amount = cost.amount ?? 0;
    if (money < amount) {
      return t("adventure.realityCost.cannotPayFunds", {
        shortage: (amount - money).toLocaleString(),
      });
    }
    return null;
  };

  const pay = async (cost: AdventureRealityCost) => {
    setPayingId(cost.id);
    try {
      await payRealityCost(cost.id);
    } catch {
      // エラー表示は Context 側で行う
    } finally {
      setPayingId(null);
    }
  };

  const origin = (cost: AdventureRealityCost) =>
    cost.source_rule
      ? t("adventure.realityCost.origin", {
          turn: cost.created_turn ?? "-",
          rule: cost.source_rule,
        })
      : t("adventure.realityCost.originNoRule", {
          turn: cost.created_turn ?? "-",
        });

  return (
    <>
      <p className="adventure-hud__note">
        {t(
          sim
            ? "adventure.realityCost.panelHintRomance"
            : "adventure.realityCost.panelHint",
        )}
      </p>
      {!activeRun.reality_cost_enabled && (
        <p className="adventure-hud__note">
          {t("adventure.realityCost.disabledNote")}
        </p>
      )}
      {costs.length === 0 ? (
        <p className="adventure-hud__note">
          {t("adventure.realityCost.empty")}
        </p>
      ) : (
        <ul className="adventure-hud__costs">
          {active.map((cost) => {
            const blockReason =
              cost.amount != null ? payBlockReason(cost) : null;
            return (
              <li key={cost.id}>
                <div className="adventure-hud__cost-head">
                  <strong>{cost.text}</strong>
                  {cost.severity === "major" && (
                    <em className="adventure-hud__cost-badge">
                      {t("adventure.realityCost.major")}
                    </em>
                  )}
                </div>
                <span className="adventure-hud__cost-meta">{origin(cost)}</span>
                {cost.amount != null && (
                  <div className="adventure-hud__cost-actions">
                    <button
                      type="button"
                      disabled={
                        blockReason !== null || streaming || payingId !== null
                      }
                      onClick={() => void pay(cost)}
                    >
                      {payingId === cost.id
                        ? t("adventure.realityCost.paying")
                        : t("adventure.realityCost.pay", {
                            amount: cost.amount.toLocaleString(),
                          })}
                    </button>
                    {blockReason && (
                      <span className="adventure-hud__cost-blocked">
                        {blockReason}
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
          {resolved.map((cost) => (
            <li key={cost.id} className="is-resolved">
              <div className="adventure-hud__cost-head">
                <strong>{cost.text}</strong>
              </div>
              <span className="adventure-hud__cost-meta">
                {cost.resolution === "paid"
                  ? t("adventure.realityCost.resolvedPaid", {
                      amount: (cost.amount ?? 0).toLocaleString(),
                    })
                  : t("adventure.realityCost.resolvedStory", {
                      turn: cost.resolved_turn,
                    })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
