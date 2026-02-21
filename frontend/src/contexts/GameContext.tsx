/**
 * GameContext - ゲームセッション状態の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import type {
  SessionStats,
  HistoryItem,
  Character,
  Ending,
  SessionAttribute,
} from "../types";

// ゲーム状態
interface GameState {
  // セッション情報
  sessionId: string | null;
  isActive: boolean;

  // キャラクター
  character: Character | null;
  currentImage: string | null;

  // 統計
  stats: SessionStats | null;

  // 履歴
  history: HistoryItem[];
  currentHistoryIndex: number;

  // 属性 (007: FR-019)
  attributes: SessionAttribute[];

  // エンディング
  ending: Ending | null;

  // 自分自身モード (US5)
  selfMode: boolean;

  // UI状態
  isTransforming: boolean;
  isLoading: boolean;
  error: string | null;
}

// アクション型
type GameAction =
  | {
      type: "START_SESSION";
      payload: {
        sessionId: string;
        character: Character;
        currentImage: string;
      };
    }
  | {
      type: "RESTORE_SESSION";
      payload: {
        sessionId: string;
        character: Character;
        currentImage: string;
        stats: SessionStats;
        history: HistoryItem[];
        attributes?: SessionAttribute[];
        selfMode?: boolean;
      };
    }
  | { type: "UPDATE_STATS"; payload: Partial<SessionStats> }
  | { type: "ADD_HISTORY_ITEM"; payload: HistoryItem }
  | { type: "SET_HISTORY"; payload: HistoryItem[] }
  | { type: "SET_CURRENT_IMAGE"; payload: string }
  | { type: "SET_ENDING"; payload: Ending | null }
  | { type: "NAVIGATE_HISTORY"; payload: number }
  | { type: "SET_TRANSFORMING"; payload: boolean }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null }
  | { type: "SET_ATTRIBUTES"; payload: SessionAttribute[] }
  | { type: "ADD_ATTRIBUTE"; payload: SessionAttribute }
  | { type: "REMOVE_ATTRIBUTE"; payload: string }
  | { type: "SET_SELF_MODE"; payload: boolean }
  | { type: "CLEAR_SESSION" };

// デフォルト状態
const defaultState: GameState = {
  sessionId: null,
  isActive: false,
  character: null,
  currentImage: null,
  stats: null,
  history: [],
  currentHistoryIndex: -1,
  attributes: [],
  ending: null,
  selfMode: false,
  isTransforming: false,
  isLoading: false,
  error: null,
};

// Reducer
function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case "START_SESSION":
      return {
        ...state,
        sessionId: action.payload.sessionId,
        isActive: true,
        character: action.payload.character,
        currentImage: action.payload.currentImage,
        stats: null,
        history: [],
        currentHistoryIndex: -1,
        ending: null,
        error: null,
      };
    case "RESTORE_SESSION":
      return {
        ...state,
        sessionId: action.payload.sessionId,
        isActive: true,
        character: action.payload.character,
        currentImage: action.payload.currentImage,
        stats: action.payload.stats,
        history: action.payload.history,
        currentHistoryIndex: action.payload.history.length - 1,
        attributes: action.payload.attributes || [],
        selfMode: action.payload.selfMode ?? false,
        ending: null,
        error: null,
      };
    case "UPDATE_STATS":
      return {
        ...state,
        stats: state.stats ? { ...state.stats, ...action.payload } : null,
      };
    case "ADD_HISTORY_ITEM":
      return {
        ...state,
        history: [...state.history, action.payload],
        currentHistoryIndex: state.history.length,
      };
    case "SET_HISTORY":
      return {
        ...state,
        history: action.payload,
        currentHistoryIndex: action.payload.length - 1,
      };
    case "SET_CURRENT_IMAGE":
      return { ...state, currentImage: action.payload };
    case "SET_ENDING":
      return { ...state, ending: action.payload };
    case "NAVIGATE_HISTORY": {
      const newIndex = Math.max(
        0,
        Math.min(action.payload, state.history.length - 1),
      );
      const historyItem = state.history[newIndex];
      return {
        ...state,
        currentHistoryIndex: newIndex,
        currentImage: historyItem?.imageUrl || state.currentImage,
      };
    }
    case "SET_TRANSFORMING":
      return { ...state, isTransforming: action.payload };
    case "SET_LOADING":
      return { ...state, isLoading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "SET_ATTRIBUTES":
      return { ...state, attributes: action.payload };
    case "ADD_ATTRIBUTE":
      return { ...state, attributes: [...state.attributes, action.payload] };
    case "REMOVE_ATTRIBUTE":
      return {
        ...state,
        attributes: state.attributes.filter((a) => a.id !== action.payload),
      };
    case "SET_SELF_MODE":
      return { ...state, selfMode: action.payload };
    case "CLEAR_SESSION":
      return defaultState;
    default:
      return state;
  }
}

// Context型定義
interface GameContextType {
  state: GameState;
  startSession: (
    sessionId: string,
    character: Character,
    currentImage: string,
  ) => void;
  restoreSession: (
    sessionId: string,
    character: Character,
    currentImage: string,
    stats: SessionStats,
    history: HistoryItem[],
    attributes?: SessionAttribute[],
    selfMode?: boolean,
  ) => void;
  updateStats: (stats: Partial<SessionStats>) => void;
  addHistoryItem: (item: HistoryItem) => void;
  setHistory: (history: HistoryItem[]) => void;
  setCurrentImage: (image: string) => void;
  setEnding: (ending: Ending | null) => void;
  navigateHistory: (index: number) => void;
  navigatePrevHistory: () => void;
  navigateNextHistory: () => void;
  setTransforming: (isTransforming: boolean) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  clearSession: () => void;
  // 007: 属性管理 (FR-019)
  addAttribute: (text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
  setAttributes: (attributes: SessionAttribute[]) => void;
  // US5: 自分自身モード
  setSelfMode: (selfMode: boolean) => void;
}

// Context作成
const GameContext = createContext<GameContextType | null>(null);

// localStorage キー
const SESSION_STORAGE_KEY = "current_session_id";

// Provider コンポーネント
export function GameProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(gameReducer, defaultState);

  // 初回マウント時にセッションIDを復元
  useEffect(() => {
    const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
    if (savedSessionId) {
      // セッション復元はApp.tsxで既存のuseSession hookと連携
      // ここではIDの復元のみ
      console.log("Found saved session:", savedSessionId);
    }
  }, []);

  // セッションID変更時にlocalStorageに保存
  useEffect(() => {
    if (state.sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, state.sessionId);
    }
  }, [state.sessionId]);

  // アクション関数
  const startSession = useCallback(
    (sessionId: string, character: Character, currentImage: string) => {
      dispatch({
        type: "START_SESSION",
        payload: { sessionId, character, currentImage },
      });
    },
    [],
  );

  const restoreSession = useCallback(
    (
      sessionId: string,
      character: Character,
      currentImage: string,
      stats: SessionStats,
      history: HistoryItem[],
      attributes?: SessionAttribute[],
      selfMode?: boolean,
    ) => {
      dispatch({
        type: "RESTORE_SESSION",
        payload: {
          sessionId,
          character,
          currentImage,
          stats,
          history,
          attributes: attributes || [],
          selfMode: selfMode ?? false,
        },
      });
    },
    [],
  );

  const updateStats = useCallback((stats: Partial<SessionStats>) => {
    dispatch({ type: "UPDATE_STATS", payload: stats });
  }, []);

  const addHistoryItem = useCallback((item: HistoryItem) => {
    dispatch({ type: "ADD_HISTORY_ITEM", payload: item });
  }, []);

  const setHistory = useCallback((history: HistoryItem[]) => {
    dispatch({ type: "SET_HISTORY", payload: history });
  }, []);

  const setCurrentImage = useCallback((image: string) => {
    dispatch({ type: "SET_CURRENT_IMAGE", payload: image });
  }, []);

  const setEnding = useCallback((ending: Ending | null) => {
    dispatch({ type: "SET_ENDING", payload: ending });
  }, []);

  const navigateHistory = useCallback((index: number) => {
    dispatch({ type: "NAVIGATE_HISTORY", payload: index });
  }, []);

  const navigatePrevHistory = useCallback(() => {
    dispatch({
      type: "NAVIGATE_HISTORY",
      payload: state.currentHistoryIndex - 1,
    });
  }, [state.currentHistoryIndex]);

  const navigateNextHistory = useCallback(() => {
    dispatch({
      type: "NAVIGATE_HISTORY",
      payload: state.currentHistoryIndex + 1,
    });
  }, [state.currentHistoryIndex]);

  const setTransforming = useCallback((isTransforming: boolean) => {
    dispatch({ type: "SET_TRANSFORMING", payload: isTransforming });
  }, []);

  const setLoading = useCallback((isLoading: boolean) => {
    dispatch({ type: "SET_LOADING", payload: isLoading });
  }, []);

  const setError = useCallback((error: string | null) => {
    dispatch({ type: "SET_ERROR", payload: error });
  }, []);

  const clearSession = useCallback(() => {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    dispatch({ type: "CLEAR_SESSION" });
  }, []);

  // 属性管理関数
  const setAttributes = useCallback((attributes: SessionAttribute[]) => {
    dispatch({ type: "SET_ATTRIBUTES", payload: attributes });
  }, []);

  const setSelfMode = useCallback((selfMode: boolean) => {
    dispatch({ type: "SET_SELF_MODE", payload: selfMode });
  }, []);

  const addAttribute = useCallback(
    async (text: string): Promise<void> => {
      if (!state.sessionId) {
        console.error("Cannot add attribute: no active session");
        return;
      }
      try {
        // Backend expects query parameters, not JSON body
        const params = new URLSearchParams({
          session_id: state.sessionId,
          attribute_text: text,
        });
        const response = await fetch(
          `/api/game/attributes?${params.toString()}`,
          {
            method: "POST",
          },
        );
        if (!response.ok) {
          throw new Error(`Failed to add attribute: ${response.status}`);
        }
        const result = await response.json();
        // Backend returns { success: true, attribute: { id, attribute_text, created_at } }
        // Map attribute_text to text for frontend compatibility
        const attribute: SessionAttribute = {
          id: result.attribute.id,
          text: result.attribute.attribute_text || result.attribute.text,
        };
        dispatch({ type: "ADD_ATTRIBUTE", payload: attribute });
      } catch (error) {
        console.error("Failed to add attribute:", error);
        throw error;
      }
    },
    [state.sessionId],
  );

  const removeAttribute = useCallback(
    async (id: string): Promise<void> => {
      if (!state.sessionId) {
        console.error("Cannot remove attribute: no active session");
        return;
      }
      try {
        // Backend expects attribute_id as path parameter only
        const response = await fetch(`/api/game/attributes/${id}`, {
          method: "DELETE",
        });
        if (!response.ok) {
          throw new Error(`Failed to remove attribute: ${response.status}`);
        }
        dispatch({ type: "REMOVE_ATTRIBUTE", payload: id });
      } catch (error) {
        console.error("Failed to remove attribute:", error);
        throw error;
      }
    },
    [state.sessionId],
  );

  const value: GameContextType = {
    state,
    startSession,
    restoreSession,
    updateStats,
    addHistoryItem,
    setHistory,
    setCurrentImage,
    setEnding,
    navigateHistory,
    navigatePrevHistory,
    navigateNextHistory,
    setTransforming,
    setLoading,
    setError,
    clearSession,
    addAttribute,
    removeAttribute,
    setAttributes,
    setSelfMode,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

// Custom Hook
// eslint-disable-next-line react-refresh/only-export-components
export function useGame(): GameContextType {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error("useGame must be used within a GameProvider");
  }
  return context;
}
