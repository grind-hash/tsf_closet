/**
 * useSession hook - manages session state and API interactions.
 * Uses original parameter names (bloom, shame, adaptation).
 */

import { useState, useCallback } from "react";
import type {
  SessionStats,
  HistoryItem,
  Character,
  SessionAttribute,
  ConversationMessage,
} from "../types";
import { API_BASE } from "../utils/api";

const DEFAULT_STATS: SessionStats = {
  bloom: 0,
  shame: 50,
  adaptation: 0,
  passedCriticalPoints: [],
  difficulty: "normal",
  nsfwMode: false,
  enablePromptPreview: false,
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
  attributes: SessionAttribute[];
  conversationHistory: ConversationMessage[];

  loadCharacters: () => Promise<void>;
  startSession: (
    characterId: string,
    difficulty?: string,
    nsfwMode?: boolean,
  ) => Promise<void>;
  startWithCustomImage: (
    imageBase64: string,
    difficulty?: string,
    nsfwMode?: boolean,
  ) => Promise<void>;
  restoreSession: () => Promise<boolean>;
  resetSession: () => Promise<void>;
  selfMode: boolean;
  updateStats: (newStats: Partial<SessionStats>) => void;
  updateFromSSE: (data: {
    image?: string;
    historyId?: string;
    stats?: Partial<SessionStats>;
    transformationCount?: number;
  }) => void;
  addAttribute: (text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
  setConversationHistory: React.Dispatch<
    React.SetStateAction<ConversationMessage[]>
  >;
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
  const [attributes, setAttributes] = useState<SessionAttribute[]>([]);
  const [conversationHistory, setConversationHistory] = useState<
    ConversationMessage[]
  >([]);
  const [selfMode, setSelfMode] = useState(false);

  const loadCharacters = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/game/characters`);
      if (!response.ok) throw new Error("キャラクター一覧の取得に失敗しました");
      const data = await response.json();
      setCharacters(data.characters);
    } catch (err) {
      setError(err instanceof Error ? err.message : "エラーが発生しました");
    }
  }, []);

  const startSession = async (
    characterId: string,
    difficulty: string = "normal",
    nsfwMode: boolean = false,
  ) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/game/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          character_id: characterId,
          difficulty,
          nsfw_mode: nsfwMode,
        }),
      });
      if (!response.ok) throw new Error("セッション開始に失敗しました");
      const data = await response.json();
      setSessionId(data.session_id);
      await restoreSession();
    } catch (err) {
      setError(err instanceof Error ? err.message : "エラーが発生しました");
    } finally {
      setIsLoading(false);
    }
  };

  const startWithCustomImage = useCallback(
    async (
      imageBase64: string,
      difficulty: string = "normal",
      nsfwMode: boolean = false,
    ) => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE}/game/start-custom`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image: imageBase64,
            difficulty,
            nsfw_mode: nsfwMode,
          }),
        });
        if (!response.ok)
          throw new Error("カスタム画像でのセッション開始に失敗しました");
        const data = await response.json();
        setSessionId(data.session_id);
        const sessionRes = await fetch(`${API_BASE}/game/session`);
        if (sessionRes.ok) {
          const sessionData = await sessionRes.json();
          setCurrentImageUrl(
            sessionData.current_image_url
              ? `${API_BASE}${sessionData.current_image_url}`
              : null,
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "エラーが発生しました");
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const restoreSession = useCallback(async (): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/game/session`);
      if (!response.ok) return false;
      const data = await response.json();

      // スネークケース→キャメルケース変換
      setSessionId(data.session_id);
      setCurrentImageUrl(
        data.current_image_url ? `${API_BASE}${data.current_image_url}` : null,
      );
      setTransformationCount(data.transformation_count);
      setHistory(
        data.history?.map(
          (h: {
            id: string;
            instruction: string;
            image_url: string;
            feeling_text?: string;
            before_description?: string;
            after_description?: string;
            timestamp: string;
            instruction_type?: string;
            costume_category?: string;
            exposure_level?: number;
            age_impression?: string;
          }) => ({
            id: h.id,
            instruction: h.instruction,
            imageUrl: h.image_url ? `${API_BASE}${h.image_url}` : "",
            feelingText: h.feeling_text || "",
            beforeDescription: h.before_description || "",
            afterDescription: h.after_description || "",
            timestamp: h.timestamp,
            instructionType: h.instruction_type ?? undefined,
            costumeCategory: h.costume_category,
            exposureLevel: h.exposure_level,
            ageImpression: h.age_impression,
          }),
        ) || [],
      );
      if (data.stats) {
        setStats({
          bloom: data.stats.bloom ?? 0,
          shame: data.stats.shame ?? 50,
          adaptation: data.stats.adaptation ?? 0,
          passedCriticalPoints:
            data.stats.passedCriticalPoints ??
            data.stats.passed_critical_points ??
            [],
          difficulty: data.stats.difficulty ?? "normal",
          nsfwMode: data.stats.nsfwMode ?? data.stats.nsfw_mode ?? false,
          enablePromptPreview:
            data.stats.enablePromptPreview ??
            data.stats.enable_prompt_preview ??
            false,
        });
      }
      // 属性を復元 (新APIは { id, text } を返す)
      if (data.attributes) {
        setAttributes(
          data.attributes.map(
            (a: { id: string; text?: string; attribute_text?: string }) => ({
              id: a.id,
              text: a.text || a.attribute_text, // 後方互換性
            }),
          ),
        );
      }
      // self_mode を復元
      setSelfMode(Boolean(data.self_mode));
      // 会話履歴を復元
      if (data.conversation_history) {
        setConversationHistory(
          data.conversation_history.map(
            (c: {
              id: string;
              role: string;
              content: string;
              created_at: string;
              instruction_type?: string | null;
            }) => ({
              id: c.id,
              role: c.role as "user" | "character",
              content: c.content,
              createdAt: c.created_at,
              instruction_type: c.instruction_type ?? undefined,
            }),
          ),
        );
      }
      return true;
    } catch {
      return false;
    }
  }, []);

  const resetSession = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/game/session`, { method: "DELETE" });
      setSessionId(null);
      setCurrentImageUrl(null);
      setTransformationCount(0);
      setHistory([]);
      setStats(DEFAULT_STATS);
      setAttributes([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "リセットに失敗しました");
    }
  }, []);

  const updateStats = useCallback((newStats: Partial<SessionStats>) => {
    setStats((prev) => ({ ...prev, ...newStats }));
  }, []);

  const updateFromSSE = useCallback(
    (data: {
      image?: string;
      historyId?: string;
      stats?: Partial<SessionStats>;
      transformationCount?: number;
    }) => {
      if (data.image && data.historyId) {
        setCurrentImageUrl(`${API_BASE}/history/images/${data.historyId}`);
      }
      if (data.stats) {
        setStats((prev) => ({ ...prev, ...data.stats }));
      }
      if (data.transformationCount !== undefined) {
        setTransformationCount(data.transformationCount);
      }
    },
    [],
  );

  const addAttribute = useCallback(
    async (text: string) => {
      if (!sessionId) return;
      try {
        const params = new URLSearchParams({
          session_id: sessionId,
          attribute_text: text,
        });
        const response = await fetch(
          `${API_BASE}/game/attributes?${params.toString()}`,
          {
            method: "POST",
          },
        );
        if (response.ok) {
          const data = await response.json();
          // バックエンドはattribute.id, attribute.attribute_textを返す
          setAttributes((prev) => [
            ...prev,
            {
              id: data.attribute?.id || data.id,
              text:
                data.attribute?.attribute_text || data.attribute_text || text,
            },
          ]);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "属性の追加に失敗しました",
        );
      }
    },
    [sessionId],
  );

  const removeAttribute = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/game/attributes/${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        setAttributes((prev) => prev.filter((a) => a.id !== id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "属性の削除に失敗しました");
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
    attributes,
    conversationHistory,
    selfMode,
    loadCharacters,
    startSession,
    startWithCustomImage,
    restoreSession,
    resetSession,
    updateStats,
    updateFromSSE,
    addAttribute,
    removeAttribute,
    setConversationHistory,
  };
}
