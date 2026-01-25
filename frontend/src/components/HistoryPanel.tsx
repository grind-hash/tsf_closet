import type { HistoryItem } from '../types';
import './HistoryPanel.css';

interface HistoryPanelProps {
  history: HistoryItem[];
}

export default function HistoryPanel({ history }: HistoryPanelProps) {
  if (history.length === 0) {
    return null;
  }

  return (
    <div className="history-panel">
      <h3>📁 へんしんのれきし</h3>
      <div className="history-grid">
        {history.map((item) => (
          <div key={item.id} className="history-item">
            <img
              src={item.imageUrl}
              alt={item.instruction}
              className="history-thumbnail"
            />
            <div className="history-info">
              <span className="history-instruction">{item.instruction}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
