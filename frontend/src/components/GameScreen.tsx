import { useState } from 'react';
import type { SessionStats, HistoryItem } from '../types';
import type { Gender } from '../App';
import ParameterBars from './ParameterBars';
import HistoryPanel from './HistoryPanel';
import './GameScreen.css';

interface GameScreenProps {
  currentImageUrl: string | null;
  stats: SessionStats;
  transformationCount: number;
  history: HistoryItem[];
  feelingText: string;
  isTransforming: boolean;
  onTransform: (instruction: string, options?: { useKanji?: boolean }) => void;
  onReset: () => void;
  onGoHome: () => void;
  gender?: Gender;
}

// 性別別の変身候補
const GIRL_SUGGESTIONS = [
  { emoji: '👸', label: 'おひめさま', instruction: 'かわいいおひめさまにへんしん！' },
  { emoji: '🧚', label: 'ようせい', instruction: 'きらきらようせいにへんしん！' },
  { emoji: '🎀', label: 'アイドル', instruction: 'キラキラアイドルにへんしん！' },
  { emoji: '🌸', label: 'まほうしょうじょ', instruction: 'まほうしょうじょにへんしん！' },
  { emoji: '🐱', label: 'ねこみみ', instruction: 'かわいいねこみみにへんしん！' },
  { emoji: '🦋', label: 'ちょうちょ', instruction: 'きれいなちょうちょにへんしん！' },
];

const BOY_SUGGESTIONS = [
  { emoji: '🦸', label: 'ヒーロー', instruction: 'スーパーヒーローにへんしん！' },
  { emoji: '🥷', label: 'にんじゃ', instruction: 'かっこいいにんじゃにへんしん！' },
  { emoji: '🤖', label: 'ロボット', instruction: 'つよいロボットにへんしん！' },
  { emoji: '🚀', label: 'うちゅうひこうし', instruction: 'うちゅうひこうしにへんしん！' },
  { emoji: '🏴‍☠️', label: 'かいぞく', instruction: 'かっこいいかいぞくにへんしん！' },
  { emoji: '⚔️', label: 'ゆうしゃ', instruction: 'つよいゆうしゃにへんしん！' },
];

export default function GameScreen({
  currentImageUrl,
  stats,
  transformationCount,
  history,
  feelingText,
  isTransforming,
  onTransform,
  onReset,
  onGoHome,
  gender = 'unknown',
}: GameScreenProps) {
  const [useKanji, setUseKanji] = useState(false);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const instruction = formData.get('instruction') as string;
    if (instruction.trim()) {
      onTransform(instruction.trim(), { useKanji });
      e.currentTarget.reset();
    }
  };

  // 性別に応じた変身候補を取得
  const getSuggestions = () => {
    if (gender === 'girl') {
      return GIRL_SUGGESTIONS;
    } else if (gender === 'boy') {
      return BOY_SUGGESTIONS;
    } else {
      // unknown: 両方を混ぜて表示
      return [...GIRL_SUGGESTIONS.slice(0, 3), ...BOY_SUGGESTIONS.slice(0, 3)];
    }
  };

  const suggestions = getSuggestions();

  return (
    <div className="game-screen">
      <header className="game-header">
        <h1 className="title-link" onClick={onGoHome} title="トップにもどる">
          ✨ わくわくへんしんマジック！✨
        </h1>
        <div className="transform-counter">
          <span className="label">へんしんかいすう:</span>
          <span className="count">{transformationCount}</span>
        </div>
      </header>

      <div className="game-layout">
        {/* 左カラム: 画像表示 */}
        <div className="image-panel">
          <h3>🪞 いまのすがた</h3>
          <div className="image-container">
            {currentImageUrl ? (
              <img
                src={currentImageUrl}
                alt="現在の姿"
                className="current-image"
              />
            ) : (
              <div className="image-placeholder">
                <span>キャラクターをえらんでね</span>
              </div>
            )}
            {isTransforming && (
              <div className="transform-overlay">
                <div className="magic-spinner"></div>
                <p>へんしんちゅう...✨</p>
                <p className="wait-hint">1ぷんくらいまってね</p>
              </div>
            )}
          </div>
          <ParameterBars stats={stats} />
        </div>

        {/* 右カラム: コントロール */}
        <div className="control-panel">
          <form onSubmit={handleSubmit} className="transform-form">
            <label htmlFor="instruction">🎭 どんなすがたにへんしんする？</label>
            <div className="input-group">
              <input
                type="text"
                name="instruction"
                id="instruction"
                placeholder="れい: ヒーローにへんしん！"
                disabled={isTransforming}
              />
              <button
                type="submit"
                className="transform-btn"
                disabled={isTransforming}
              >
                ✨ へんしん！
              </button>
            </div>
            
            <label className="kanji-toggle">
              <input
                type="checkbox"
                checked={useKanji}
                onChange={(e) => setUseKanji(e.target.checked)}
                disabled={isTransforming}
              />
              <span>📚 漢字よめるよ！</span>
            </label>
          </form>

          <div className="suggestion-categories">
            <p>💡 こんなへんしんはどう？</p>
            <div className="suggestion-badges">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => onTransform(s.instruction, { useKanji })}
                  disabled={isTransforming}
                >
                  {s.emoji} {s.label}
                </button>
              ))}
            </div>
          </div>

          {feelingText && (
            <div className="feeling-box">
              <h4>💭 キャラクターのきもち</h4>
              <p className="feeling-text">{feelingText}</p>
            </div>
          )}

          <button onClick={onReset} className="reset-btn">
            🔄 さいしょからやりなおす
          </button>
        </div>
      </div>

      <HistoryPanel history={history} />
    </div>
  );
}
