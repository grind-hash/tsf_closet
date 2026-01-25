import { useState, useEffect, useCallback } from 'react';
import { useSession } from './hooks/useSession';
import { useSSE } from './hooks/useSSE';
import CharacterSelect from './components/CharacterSelect';
import GameScreen from './components/GameScreen';
import EndingModal from './components/EndingModal';
import type { Ending } from './types';
import './App.css';

export type Gender = 'girl' | 'boy' | 'unknown';

// 性別選択モーダル
function GenderSelectModal({ onSelect }: { onSelect: (gender: Gender) => void }) {
  return (
    <div className="gender-modal-overlay">
      <div className="gender-modal">
        <h2>🌈 おしえてね！</h2>
        <p>あなたは おんなのこ？ おとこのこ？</p>
        <div className="gender-buttons">
          <button className="gender-btn girl" onClick={() => onSelect('girl')}>
            👧 おんなのこ
          </button>
          <button className="gender-btn boy" onClick={() => onSelect('boy')}>
            👦 おとこのこ
          </button>
          <button className="gender-btn unknown" onClick={() => onSelect('unknown')}>
            🤔 わからない
          </button>
        </div>
      </div>
    </div>
  );
}

function App() {
  const session = useSession();
  const [screen, setScreen] = useState<'character-select' | 'game'>('character-select');
  const [feelingText, setFeelingText] = useState('');
  const [isTransforming, setIsTransforming] = useState(false);
  const [ending, setEnding] = useState<Ending | null>(null);
  const [gender, setGender] = useState<Gender>('unknown');
  const [pendingCustomImage, setPendingCustomImage] = useState<string | null>(null);
  const [showGenderModal, setShowGenderModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // SSEハンドラ
  const sse = useSSE({
    onText: (chunk) => {
      setFeelingText((prev) => prev + chunk);
    },
    onImage: (image, historyId) => {
      session.updateFromSSE({ image, historyId });
      setIsTransforming(false);
    },
    onStats: (stats) => {
      session.updateStats({
        excitement: stats.excitement,
        immersion: stats.immersion,
        challenge: stats.challenge,
      });
    },
    onEnding: (data) => {
      setEnding(data);
    },
    onComplete: (_, transformationCount) => {
      session.updateFromSSE({ transformationCount });
      setIsTransforming(false);
    },
    onError: (message) => {
      console.error('SSE Error:', message);
      setErrorMessage(message);  // エラーモーダルを表示
      setIsTransforming(false);
    },
  });

  // 初期化: セッション復元を試みる
  useEffect(() => {
    const init = async () => {
      await session.loadCharacters();
      const restored = await session.restoreSession();
      if (restored && session.sessionId) {
        setScreen('game');
      }
    };
    init();
  }, []);

  // 変身実行
  const handleTransform = useCallback((instruction: string, options?: { useKanji?: boolean }) => {
    if (!session.sessionId || isTransforming) return;
    
    setIsTransforming(true);
    setFeelingText('');
    
    const useKanji = options?.useKanji ? 'true' : 'false';
    const url = `/game/play/stream?session_id=${session.sessionId}&instruction=${encodeURIComponent(instruction)}&use_kanji=${useKanji}`;
    sse.startStream(url);
  }, [session.sessionId, isTransforming, sse]);

  // キャラクター選択
  const handleSelectCharacter = useCallback(async (characterId: string) => {
    // キャラクター情報から性別を取得
    const character = session.characters.find(c => c.id === characterId);
    if (character) {
      setGender(character.gender);
    } else {
      setGender('unknown');
    }
    
    await session.startSession(characterId);
    const restored = await session.restoreSession();
    if (restored) {
      setScreen('game');
    }
  }, [session]);

  // カスタム画像選択（性別モーダルを表示）
  const handleCustomImage = useCallback((imageBase64: string) => {
    setPendingCustomImage(imageBase64);
    setShowGenderModal(true);
  }, []);

  // 性別選択後にセッション開始
  const handleGenderSelect = useCallback(async (selectedGender: Gender) => {
    setGender(selectedGender);
    setShowGenderModal(false);
    if (pendingCustomImage) {
      await session.startWithCustomImage(pendingCustomImage);
      setPendingCustomImage(null);
      setScreen('game');
    }
  }, [pendingCustomImage, session]);

  // リセット
  const handleReset = useCallback(async () => {
    await session.resetSession();
    setScreen('character-select');
    setFeelingText('');
    setEnding(null);
    setGender('unknown');
  }, [session]);

  return (
    <div className="app">
      {screen === 'character-select' ? (
        <CharacterSelect
          characters={session.characters}
          onSelectCharacter={handleSelectCharacter}
          onCustomImage={handleCustomImage}
          isLoading={session.isLoading}
        />
      ) : (
        <GameScreen
          currentImageUrl={session.currentImageUrl}
          stats={session.stats}
          transformationCount={session.transformationCount}
          history={session.history}
          feelingText={feelingText}
          isTransforming={isTransforming}
          onTransform={handleTransform}
          onReset={handleReset}
          onGoHome={() => setScreen('character-select')}
          gender={gender}
        />
      )}

      {showGenderModal && (
        <GenderSelectModal onSelect={handleGenderSelect} />
      )}

      {session.isLoading && (
        <div className="conversion-overlay">
          <div className="conversion-spinner"></div>
          <p>アニメキャラクターに へんかんちゅう...✨</p>
          <p className="conversion-hint">1ぷんくらいまってね</p>
        </div>
      )}

      {ending && (
        <EndingModal
          ending={ending}
          onClose={() => setEnding(null)}
          onRestart={handleReset}
        />
      )}

      {errorMessage && (
        <div className="error-modal-overlay" onClick={() => setErrorMessage(null)}>
          <div className="error-modal" onClick={(e) => e.stopPropagation()}>
            <div className="error-modal-icon">⚠️</div>
            <h3>コンテンツフィルターエラー</h3>
            <p>{errorMessage}</p>
            <button className="error-modal-close" onClick={() => setErrorMessage(null)}>
              わかった
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
