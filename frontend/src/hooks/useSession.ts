/**
 * useSession hook - GameContext 互換ラッパー
 */

import { useCallback } from "react";
import { useGame } from "../contexts/GameContext";
import type {
  Character,
  ConversationMessage,
  HistoryItem,
  SessionAttribute,
  SessionStats,
} from "../types";
import { API_BASE } from "../utils/api";

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
    seed?: number;
  }) => void;
  addAttribute: (text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
  updateAttributesFromSSE: (attr: { id: string; text: string }) => void;
  setConversationHistory: React.Dispatch<
    React.SetStateAction<ConversationMessage[]>
  >;
}

export function useSession(): UseSessionReturn {
  const game = useGame();

  const defaultStats: SessionStats = game.state.stats ?? {
    bloom: 0,
    shame: 50,
    adaptation: 0,
    passedCriticalPoints: [],
    difficulty: "normal",
    nsfwMode: false,
    enablePromptPreview: false,
  };

  const loadCharacters = useCallback(async () => {
    await game.loadCharacters();
  }, [game]);

  const startSession = async (
    characterId: string,
    difficulty: string = "normal",
    nsfwMode: boolean = false,
  ) => {
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
      const character = game.state.characters.find(
        (entry) => entry.id === characterId,
      ) ?? {
        id: characterId,
        name: "",
        description: "",
        thumbnail: data.image_path ?? "",
      };
      await game.startSession(
        data.session_id,
        character,
        data.image_path ?? "",
      );
      await game.restoreActiveSession();
    } catch (err) {
      game.setError(
        err instanceof Error ? err.message : "エラーが発生しました",
      );
    }
  };

  const startWithCustomImage = useCallback(
    async (
      imageBase64: string,
      difficulty: string = "normal",
      nsfwMode: boolean = false,
    ) => {
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
        await game.startSession(
          data.session_id,
          {
            id: "custom",
            name: "",
            description: "",
            thumbnail: data.image_path ?? "",
          },
          data.image_path ?? "",
        );
        await game.restoreActiveSession();
      } catch (err) {
        game.setError(
          err instanceof Error ? err.message : "エラーが発生しました",
        );
      }
    },
    [game],
  );

  const restoreSession = useCallback(async (): Promise<boolean> => {
    return game.restoreActiveSession();
  }, [game]);

  const resetSession = useCallback(async () => {
    await game.resetSession();
  }, [game]);

  const updateStats = useCallback(
    (newStats: Partial<SessionStats>) => {
      game.updateStats(newStats);
    },
    [game],
  );

  const updateFromSSE = useCallback(
    (data: {
      image?: string;
      historyId?: string;
      stats?: Partial<SessionStats>;
      transformationCount?: number;
      seed?: number;
    }) => {
      game.updateFromSSE(data);
    },
    [game],
  );

  const addAttribute = useCallback(
    async (text: string) => {
      await game.addAttribute(text);
    },
    [game],
  );

  const removeAttribute = useCallback(
    async (id: string) => {
      await game.removeAttribute(id);
    },
    [game],
  );

  const updateAttributesFromSSE = useCallback(
    (attr: { id: string; text: string }) => {
      game.updateAttributesFromSSE(attr);
    },
    [game],
  );

  return {
    sessionId: game.state.sessionId,
    currentImageUrl: game.state.currentImage,
    transformationCount: game.state.transformationCount,
    history: game.state.history,
    stats: game.state.stats ?? defaultStats,
    isLoading: game.state.isLoading,
    error: game.state.error,
    characters: game.state.characters,
    attributes: game.state.attributes,
    conversationHistory: game.state.conversationHistory,
    selfMode: game.state.selfMode,
    loadCharacters,
    startSession,
    startWithCustomImage,
    restoreSession,
    resetSession,
    updateStats,
    updateFromSSE,
    addAttribute,
    removeAttribute,
    updateAttributesFromSSE,
    setConversationHistory: (value) => {
      if (typeof value === "function") {
        game.setConversationHistory(value(game.state.conversationHistory));
        return;
      }
      game.setConversationHistory(value);
    },
  };
}
