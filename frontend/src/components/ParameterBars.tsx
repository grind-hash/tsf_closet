/**
 * ParameterBars component - displays bloom, shame, and adaptation bars.
 */

import type { SessionStats } from "../types";
import "./ParameterBars.css";

interface ParameterBarsProps {
  stats: SessionStats;
}

export default function ParameterBars({ stats }: ParameterBarsProps) {
  return (
    <div className="parameters-panel">
      {/* 開花度 (bloom) */}
      <div className="parameter-bar">
        <label>開花度</label>
        <div className="progress-container">
          <div
            className="progress-bar bloom"
            style={{ width: `${Math.min(100, Math.max(0, stats.bloom))}%` }}
          />
        </div>
        <span className="parameter-value">{stats.bloom}</span>
      </div>

      {/* 羞恥心 (shame) */}
      <div className="parameter-bar">
        <label>羞恥心</label>
        <div className="progress-container">
          <div
            className="progress-bar shame"
            style={{ width: `${Math.min(100, Math.max(0, stats.shame))}%` }}
          />
        </div>
        <span className="parameter-value">{stats.shame}</span>
      </div>

      {/* 順応度 (adaptation) - 中央起点 */}
      <div className="parameter-bar">
        <label>順応度</label>
        <div className="progress-container adaptation-container">
          <div
            className="progress-bar adaptation"
            style={{
              width: `${Math.abs(stats.adaptation)}%`,
              marginLeft:
                stats.adaptation >= 0
                  ? "50%"
                  : `${50 - Math.abs(stats.adaptation)}%`,
            }}
          />
        </div>
        <span className="parameter-value">{stats.adaptation}</span>
      </div>
    </div>
  );
}
