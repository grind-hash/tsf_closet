/**
 * EndingModal component - displays ending achievement.
 */

import type { Ending } from "../types";
import "./EndingModal.css";

interface EndingModalProps {
  ending: Ending;
  onClose: () => void;
  onRestart: () => void;
  onGallery: () => void;
}

export default function EndingModal({
  ending,
  onClose,
  onRestart,
  onGallery,
}: EndingModalProps) {
  return (
    <div className="ending-modal" onClick={onClose}>
      <div className="ending-content" onClick={(e) => e.stopPropagation()}>
        <div className="ending-badge">{ending.badge}</div>
        <h2 className="ending-title">{ending.name}</h2>
        <p className="ending-description">{ending.description}</p>

        {ending.speech && <div className="ending-speech">{ending.speech}</div>}

        {ending.summary && (
          <div className="ending-summary">{ending.summary}</div>
        )}

        <div className="ending-actions">
          <button className="btn btn-primary" onClick={onGallery}>
            ギャラリーへ
          </button>
          <button className="btn btn-outline" onClick={onRestart}>
            もう一度プレイ
          </button>
        </div>
      </div>
    </div>
  );
}
