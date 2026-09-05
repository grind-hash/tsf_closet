import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AnlasBalance } from "../types";
import { NovelaiUsageBar } from "./NovelaiUsageBar";

interface AnlasBarProps {
  balance: AnlasBalance;
  /** 実効モデルが V5 のときは利用上限バーも出す */
  showUsage: boolean;
}

/** US5: Anlas 残高バー(NovelAI のみ)。モバイルでは折りたたみ */
export default function AnlasBar({ balance, showUsage }: AnlasBarProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className={`game-play-screen__anlas-bar${expanded ? " is-expanded" : ""}`}
    >
      <button
        type="button"
        className="game-play-screen__anlas-toggle"
        aria-expanded={expanded}
        aria-controls="mobile-anlas-balance"
        onClick={() => setExpanded((current) => !current)}
      >
        <span>Anlas</span>
        <span
          className="game-play-screen__anlas-toggle-icon"
          aria-hidden="true"
        >
          ▾
        </span>
      </button>
      <div
        id="mobile-anlas-balance"
        className="game-play-screen__anlas-content"
      >
        {showUsage && balance.usage && (
          <NovelaiUsageBar usage={balance.usage} compact />
        )}
        <span className="game-play-screen__anlas-label">
          Anlas: {balance.totalAnlas.toLocaleString()}
        </span>
        <span
          className="game-play-screen__anlas-detail"
          title={t(
            "gameplay.anlasBreakdown",
            "Fixed: {{fixed}}, Purchased: {{purchased}}",
            {
              fixed: balance.fixedAnlas.toLocaleString(),
              purchased: balance.purchasedAnlas.toLocaleString(),
            },
          )}
        >
          ({balance.fixedAnlas.toLocaleString()} +{" "}
          {balance.purchasedAnlas.toLocaleString()})
        </span>
      </div>
    </div>
  );
}
