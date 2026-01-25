import { useState, useCallback } from 'react';
import type { SessionStats, HistoryItem, Character } from '../types';

const API_BASE = '';

const DEFAULT_STATS: SessionStats = {
  excitement: 0,
  immersion: 50,
  challenge: 0,
  passedCriticalPoints: [],
  difficulty: 'normal',
};

export interface UseSessionReturn {
  sessionId: string | null;
  currentImageUrl: string | null;
  transformationCount: number;
  history: HistoryItem[];
  stats: SessionStats;
  isLoading: boolean;
  error: string | null;
  characters: Character[];
  
  loadCharacters: () => Promise<void>;
  startSession: (characterId: string) => Promise<void>;
  startWithCustomImage: (imageBase64: string) => Promise<void>;
  restoreSession: () => Promise<boolean>;
  resetSession: () => Promise<void>;
  updateStats: (newStats: Partial<SessionStats>) => void;
  updateFromSSE: (data: {
    image?: string;
    historyId?: string;
    stats?: Partial<SessionStats>;
    transformationCount?: number;
  }) => void;
}

export function useSession(): UseSessionReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentImageUrl, setCurrentImageUrl] = useState<string | null>(null);
  const [transformationCount, setTransformationCount] = useState(0);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [stats, setStats] = useState<SessionStats>(DEFAULT_STATS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);

  const loadCharacters = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/game/characters`);
      if (!response.ok) throw new Error('キャラクター一覧の取得に失敗しました');
      const data = await response.json();
      setCharacters(data.characters);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'エラーが発生しました');
    }
  }, []);

  const startSession = useCallback(async (characterId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/game/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: characterId }),
      });
      if (!response.ok) throw new Error('セッション開始に失敗しました');
      const data = await response.json();
      setSessionId(data.session_id);
      // セッション情報を取得
      await restoreSession();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'エラーが発生しました');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const startWithCustomImage = useCallback(async (imageBase64: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/game/start-custom`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: imageBase64 }),
      });
      if (!response.ok) throw new Error('カスタム画像でのセッション開始に失敗しました');
      const data = await response.json();
      setSessionId(data.session_id);
      // 変換後の画像をセッションから取得
      const sessionRes = await fetch(`${API_BASE}/game/session`);
      if (sessionRes.ok) {
        const sessionData = await sessionRes.json();
        setCurrentImageUrl(sessionData.current_image_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'エラーが発生しました');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const restoreSession = useCallback(async (): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/game/session`);
      if (!response.ok) return false;
      const data = await response.json();
      
      // スネークケース→キャメルケース変換
      setSessionId(data.session_id);
      setCurrentImageUrl(data.current_image_url);
      setTransformationCount(data.transformation_count);
      setHistory(data.history?.map((h: any) => ({
        id: h.id,
        instruction: h.instruction,
        imageUrl: h.image_url,
        feelingText: h.feeling_text || '',
        beforeDescription: h.before_description || '',
        afterDescription: h.after_description || '',
        timestamp: h.timestamp,
        costumeCategory: h.costume_category,
        sparkleLevel: h.sparkle_level,
        ageImpression: h.age_impression,
      })) || []);
      if (data.stats) {
        setStats({
          excitement: data.stats.excitement ?? 0,
          immersion: data.stats.immersion ?? 50,
          challenge: data.stats.challenge ?? 0,
          passedCriticalPoints: data.stats.passed_critical_points ?? [],
          difficulty: data.stats.difficulty ?? 'normal',
        });
      }
      return true;
    } catch {
      return false;
    }
  }, []);

  const resetSession = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/game/session`, { method: 'DELETE' });
      setSessionId(null);
      setCurrentImageUrl(null);
      setTransformationCount(0);
      setHistory([]);
      setStats(DEFAULT_STATS);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'リセットに失敗しました');
    }
  }, []);

  const updateStats = useCallback((newStats: Partial<SessionStats>) => {
    setStats(prev => ({ ...prev, ...newStats }));
  }, []);

  const updateFromSSE = useCallback((data: {
    image?: string;
    historyId?: string;
    stats?: Partial<SessionStats>;
    transformationCount?: number;
  }) => {
    if (data.image && data.historyId) {
      setCurrentImageUrl(`/history/images/${data.historyId}`);
    }
    if (data.stats) {
      setStats(prev => ({ ...prev, ...data.stats }));
    }
    if (data.transformationCount !== undefined) {
      setTransformationCount(data.transformationCount);
    }
  }, []);

  return {
    sessionId,
    currentImageUrl,
    transformationCount,
    history,
    stats,
    isLoading,
    error,
    characters,
    loadCharacters,
    startSession,
    startWithCustomImage,
    restoreSession,
    resetSession,
    updateStats,
    updateFromSSE,
  };
}
