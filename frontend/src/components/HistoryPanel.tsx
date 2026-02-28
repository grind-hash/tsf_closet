/**
 * HistoryPanel component - displays transformation history.
 */

import type { HistoryItem } from "../types";
import "./HistoryPanel.css";

interface HistoryPanelProps {
  history: HistoryItem[];
  onSelectHistory: (historyId: string) => void;
}

export default function HistoryPanel({
  history,
  onSelectHistory,
}: HistoryPanelProps) {
  if (history.length === 0) {
    return null;
  }

  return (
    <div className="history-panel">
      <h3>
        📁 履歴
        <span className="history-hint">（クリックでベース画像に選択）</span>
      </h3>
      <div className="history-grid">
        {history.map((item) => (
          <button
            key={item.id}
            className="history-item"
            onClick={() => onSelectHistory(item.id)}
            title={item.instruction}
          >
            <img
              src={item.imageUrl}
              alt={item.instruction}
              className="history-thumbnail"
            />
            <span className="history-instruction">{item.instruction}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
