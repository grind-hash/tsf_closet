import type { Ending } from '../types';
import './EndingModal.css';

interface EndingModalProps {
  ending: Ending;
  onClose: () => void;
  onRestart: () => void;
}

export default function EndingModal({ ending, onClose, onRestart }: EndingModalProps) {
  const getEndingEmoji = (endingId: string) => {
    switch (endingId) {
      case 'super_hero': return '🦸';
      case 'magic_master': return '🧙';
      case 'adventurer': return '🗺️';
      case 'transformation_master': return '🌟';
      default: return '🎉';
    }
  };

  const getEndingTitle = (endingId: string) => {
    switch (endingId) {
      case 'super_hero': return 'スーパーヒーローエンド！';
      case 'magic_master': return 'マスターまほうつかいエンド！';
      case 'adventurer': return 'だいぼうけんかエンド！';
      case 'transformation_master': return 'へんしんマスターエンド！';
      default: return ending.title;
    }
  };

  return (
    <div className="ending-modal-overlay" onClick={onClose}>
      <div className="ending-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ending-badge">
          <span className="ending-emoji">{getEndingEmoji(ending.endingId)}</span>
        </div>

        <h2 className="ending-title">
          🎊 おめでとう！ 🎊
        </h2>

        <h3 className="ending-type">
          {getEndingTitle(ending.endingId)}
        </h3>

        {ending.isNew && (
          <div className="new-badge">✨ はじめてたっせい！ ✨</div>
        )}

        <div className="ending-speech">
          <p>「{ending.finalSpeech}」</p>
        </div>

        <div className="ending-summary">
          <p>{ending.summary}</p>
        </div>

        <div className="ending-actions">
          <button className="restart-btn" onClick={onRestart}>
            🔄 もういちどあそぶ
          </button>
          <button className="close-btn" onClick={onClose}>
            ✖️ とじる
          </button>
        </div>
      </div>
    </div>
  );
}
