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
  ConversationMessage,
  SurroundingsImageState,
} from "../types";
import { API_BASE } from "../utils/api";

interface GameState {
  sessionId: string | null;
  isActive: boolean;
  character: Character | null;
  characters: Character[];
  currentImage: string | null;
  stats: SessionStats | null;
  history: HistoryItem[];
  currentHistoryIndex: number;
  attributes: SessionAttribute[];
  conversationHistory: ConversationMessage[];
  ending: Ending | null;
  selfMode: boolean;
  isTransforming: boolean;
  isLoading: boolean;
  error: string | null;
  feelingText: string;
  transformationCount: number;
  lastGeneratedSeed: number | null;
  lastSurroundingsImage: SurroundingsImageState | null;
}

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
        character: Character | null;
        currentImage: string | null;
        stats: SessionStats | null;
        history: HistoryItem[];
        attributes: SessionAttribute[];
        conversationHistory: ConversationMessage[];
        selfMode: boolean;
        transformationCount: number;
      };
    }
  | { type: "SET_CHARACTERS"; payload: Character[] }
  | { type: "UPDATE_STATS"; payload: Partial<SessionStats> }
  | { type: "ADD_HISTORY_ITEM"; payload: HistoryItem }
  | { type: "SET_HISTORY"; payload: HistoryItem[] }
  | { type: "SET_CURRENT_IMAGE"; payload: string | null }
  | { type: "SET_ENDING"; payload: Ending | null }
  | { type: "NAVIGATE_HISTORY"; payload: number }
  | { type: "SET_TRANSFORMING"; payload: boolean }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null }
  | { type: "SET_ATTRIBUTES"; payload: SessionAttribute[] }
  | { type: "ADD_ATTRIBUTE"; payload: SessionAttribute }
  | { type: "REMOVE_ATTRIBUTE"; payload: string }
  | { type: "SET_SELF_MODE"; payload: boolean }
  | { type: "SET_CONVERSATION_HISTORY"; payload: ConversationMessage[] }
  | { type: "APPEND_FEELING_TEXT"; payload: string }
  | { type: "SET_FEELING_TEXT"; payload: string }
  | { type: "SET_TRANSFORMATION_COUNT"; payload: number }
  | { type: "SET_LAST_GENERATED_SEED"; payload: number | null }
  | {
      type: "SET_LAST_SURROUNDINGS_IMAGE";
      payload: SurroundingsImageState | null;
    }
  | { type: "CLEAR_SESSION" };

const defaultState: GameState = {
  sessionId: null,
  isActive: false,
  character: null,
  characters: [],
  currentImage: null,
  stats: null,
  history: [],
  currentHistoryIndex: -1,
  attributes: [],
  conversationHistory: [],
  ending: null,
  selfMode: false,
  isTransforming: false,
  isLoading: false,
  error: null,
  feelingText: "",
  transformationCount: 0,
  lastGeneratedSeed: null,
  lastSurroundingsImage: null,
};

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
        attributes: [],
        conversationHistory: [],
        ending: null,
        error: null,
        feelingText: "",
        transformationCount: 0,
        lastGeneratedSeed: null,
        lastSurroundingsImage: null,
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
        attributes: action.payload.attributes,
        conversationHistory: action.payload.conversationHistory,
        selfMode: action.payload.selfMode,
        transformationCount: action.payload.transformationCount,
        error: null,
      };
    case "SET_CHARACTERS":
      return { ...state, characters: action.payload };
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
        attributes: state.attributes.filter(
          (attribute) => attribute.id !== action.payload,
        ),
      };
    case "SET_SELF_MODE":
      return { ...state, selfMode: action.payload };
    case "SET_CONVERSATION_HISTORY":
      return { ...state, conversationHistory: action.payload };
    case "APPEND_FEELING_TEXT":
      return { ...state, feelingText: state.feelingText + action.payload };
    case "SET_FEELING_TEXT":
      return { ...state, feelingText: action.payload };
    case "SET_TRANSFORMATION_COUNT":
      return { ...state, transformationCount: action.payload };
    case "SET_LAST_GENERATED_SEED":
      return { ...state, lastGeneratedSeed: action.payload };
    case "SET_LAST_SURROUNDINGS_IMAGE":
      return { ...state, lastSurroundingsImage: action.payload };
    case "CLEAR_SESSION":
      return { ...defaultState, characters: state.characters };
    default:
      return state;
  }
}

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
  loadCharacters: () => Promise<void>;
  restoreActiveSession: () => Promise<boolean>;
  restoreSessionById: (sessionId: string) => Promise<boolean>;
  resetSession: () => Promise<void>;
  updateStats: (stats: Partial<SessionStats>) => void;
  updateFromSSE: (data: {
    image?: string;
    historyId?: string;
    stats?: Partial<SessionStats>;
    transformationCount?: number;
    seed?: number;
  }) => void;
  updateAttributesFromSSE: (attribute: SessionAttribute) => void;
  addHistoryItem: (item: HistoryItem) => void;
  setHistory: (history: HistoryItem[]) => void;
  setCurrentImage: (image: string | null) => void;
  setEnding: (ending: Ending | null) => void;
  navigateHistory: (index: number) => void;
  navigatePrevHistory: () => void;
  navigateNextHistory: () => void;
  setTransforming: (isTransforming: boolean) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  clearSession: () => void;
  addAttribute: (text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
  setAttributes: (attributes: SessionAttribute[]) => void;
  setSelfMode: (selfMode: boolean) => void;
  setConversationHistory: (history: ConversationMessage[]) => void;
  appendFeelingText: (chunk: string) => void;
  setFeelingText: (text: string) => void;
  clearFeelingText: () => void;
  setTransformationCount: (count: number) => void;
  setLastGeneratedSeed: (seed: number | null) => void;
  setLastSurroundingsImage: (image: SurroundingsImageState | null) => void;
}

const GameContext = createContext<GameContextType | null>(null);
const SESSION_STORAGE_KEY = "current_session_id";

function mapHistoryItem(item: {
  id: string;
  instruction: string;
  image_url?: string;
  feeling_text?: string;
  before_description?: string;
  after_description?: string;
  timestamp: string;
  instruction_type?: string;
  costume_category?: string;
  exposure_level?: string;
  age_impression?: string;
  seed?: number;
  surroundings_image_url?: string;
}): HistoryItem {
  return {
    id: item.id,
    instruction: item.instruction,
    imageUrl: item.image_url ? `${API_BASE}${item.image_url}` : "",
    feelingText: item.feeling_text || "",
    beforeDescription: item.before_description || "",
    afterDescription: item.after_description || "",
    timestamp: item.timestamp,
    instructionType: item.instruction_type ?? undefined,
    costumeCategory: item.costume_category,
    exposureLevel: item.exposure_level,
    ageImpression: item.age_impression,
    relatedMessageId: item.id ? `user-${item.id}` : undefined,
    seed: item.seed,
    surroundingsImageUrl: item.surroundings_image_url
      ? `${API_BASE}${item.surroundings_image_url}`
      : undefined,
  };
}

function mapSessionResponse(data: {
  session_id: string;
  current_image_url?: string | null;
  transformation_count?: number;
  history?: Array<Parameters<typeof mapHistoryItem>[0]>;
  stats?: {
    bloom?: number;
    shame?: number;
    adaptation?: number;
    passedCriticalPoints?: number[];
    passed_critical_points?: number[];
    difficulty?: string;
    nsfwMode?: boolean;
    nsfw_mode?: boolean;
    enablePromptPreview?: boolean;
    enable_prompt_preview?: boolean;
  } | null;
  attributes?: Array<{ id: string; text?: string; attribute_text?: string }>;
  conversation_history?: Array<{
    id: string;
    role: string;
    content: string;
    created_at: string;
    instruction_type?: string | null;
  }>;
  self_mode?: boolean;
  character_id?: string | null;
}): GameAction & { type: "RESTORE_SESSION" } {
  const history = (data.history ?? []).map(mapHistoryItem);
  const currentImage = data.current_image_url
    ? `${API_BASE}${data.current_image_url}`
    : (history.at(-1)?.imageUrl ?? null);
  const character = data.character_id
    ? {
        id: data.character_id,
        name: "",
        description: "",
        thumbnail: currentImage ?? "",
      }
    : null;

  return {
    type: "RESTORE_SESSION",
    payload: {
      sessionId: data.session_id,
      character,
      currentImage,
      stats: data.stats
        ? {
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
          }
        : null,
      history,
      attributes: (data.attributes ?? []).map((attribute) => ({
        id: attribute.id,
        text: attribute.text || attribute.attribute_text || "",
      })),
      conversationHistory: (data.conversation_history ?? []).map((message) => ({
        id: message.id,
        role: message.role as "user" | "character",
        content: message.content,
        createdAt: message.created_at,
        instruction_type: message.instruction_type ?? undefined,
      })),
      selfMode: Boolean(data.self_mode),
      transformationCount: data.transformation_count ?? history.length,
    },
  };
}

export function GameProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(gameReducer, defaultState);

  useEffect(() => {
    const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
    if (savedSessionId && !state.sessionId) {
      dispatch({
        type: "START_SESSION",
        payload: {
          sessionId: savedSessionId,
          character: { id: "", name: "", description: "", thumbnail: "" },
          currentImage: "",
        },
      });
    }
  }, [state.sessionId]);

  useEffect(() => {
    if (state.sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, state.sessionId);
    }
  }, [state.sessionId]);

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
          conversationHistory: state.conversationHistory,
          selfMode: selfMode ?? false,
          transformationCount: history.length,
        },
      });
    },
    [state.conversationHistory],
  );

  const loadCharacters = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/game/characters`);
      if (!response.ok) {
        throw new Error("キャラクター一覧の取得に失敗しました");
      }
      const data = await response.json();
      dispatch({ type: "SET_CHARACTERS", payload: data.characters ?? [] });
    } catch (error) {
      dispatch({
        type: "SET_ERROR",
        payload:
          error instanceof Error
            ? error.message
            : "キャラクター一覧の取得に失敗しました",
      });
    }
  }, []);

  const restoreActiveSession = useCallback(async (): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/game/session`);
      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      dispatch(mapSessionResponse(data));
      return true;
    } catch {
      return false;
    }
  }, []);

  const restoreSessionById = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/game/sessions/${sessionId}/restore`,
        { method: "POST" },
      );
      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      dispatch(mapSessionResponse(data));
      return true;
    } catch {
      return false;
    }
  }, []);

  const resetSession = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/game/session`, { method: "DELETE" });
    } finally {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      dispatch({ type: "CLEAR_SESSION" });
    }
  }, []);

  const updateStats = useCallback((stats: Partial<SessionStats>) => {
    dispatch({ type: "UPDATE_STATS", payload: stats });
  }, []);

  const updateFromSSE = useCallback(
    (data: {
      image?: string;
      historyId?: string;
      stats?: Partial<SessionStats>;
      transformationCount?: number;
      seed?: number;
    }) => {
      if (data.image && data.historyId) {
        dispatch({
          type: "SET_CURRENT_IMAGE",
          payload: `${API_BASE}/history/images/${data.historyId}`,
        });
      }
      if (data.stats) {
        dispatch({ type: "UPDATE_STATS", payload: data.stats });
      }
      if (data.transformationCount !== undefined) {
        dispatch({
          type: "SET_TRANSFORMATION_COUNT",
          payload: data.transformationCount,
        });
      }
      if (data.seed !== undefined) {
        dispatch({ type: "SET_LAST_GENERATED_SEED", payload: data.seed });
      }
    },
    [],
  );

  const updateAttributesFromSSE = useCallback((attribute: SessionAttribute) => {
    dispatch({ type: "ADD_ATTRIBUTE", payload: attribute });
  }, []);

  const addHistoryItem = useCallback((item: HistoryItem) => {
    dispatch({ type: "ADD_HISTORY_ITEM", payload: item });
  }, []);

  const setHistory = useCallback((history: HistoryItem[]) => {
    dispatch({ type: "SET_HISTORY", payload: history });
  }, []);

  const setCurrentImage = useCallback((image: string | null) => {
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

  const setAttributes = useCallback((attributes: SessionAttribute[]) => {
    dispatch({ type: "SET_ATTRIBUTES", payload: attributes });
  }, []);

  const setSelfMode = useCallback((selfMode: boolean) => {
    dispatch({ type: "SET_SELF_MODE", payload: selfMode });
  }, []);

  const setConversationHistory = useCallback(
    (history: ConversationMessage[]) => {
      dispatch({ type: "SET_CONVERSATION_HISTORY", payload: history });
    },
    [],
  );

  const appendFeelingText = useCallback((chunk: string) => {
    dispatch({ type: "APPEND_FEELING_TEXT", payload: chunk });
  }, []);

  const setFeelingText = useCallback((text: string) => {
    dispatch({ type: "SET_FEELING_TEXT", payload: text });
  }, []);

  const clearFeelingText = useCallback(() => {
    dispatch({ type: "SET_FEELING_TEXT", payload: "" });
  }, []);

  const setTransformationCount = useCallback((count: number) => {
    dispatch({ type: "SET_TRANSFORMATION_COUNT", payload: count });
  }, []);

  const setLastGeneratedSeed = useCallback((seed: number | null) => {
    dispatch({ type: "SET_LAST_GENERATED_SEED", payload: seed });
  }, []);

  const setLastSurroundingsImage = useCallback(
    (image: SurroundingsImageState | null) => {
      dispatch({ type: "SET_LAST_SURROUNDINGS_IMAGE", payload: image });
    },
    [],
  );

  const addAttribute = useCallback(
    async (text: string): Promise<void> => {
      if (!state.sessionId) {
        console.error("Cannot add attribute: no active session");
        return;
      }

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
      dispatch({
        type: "ADD_ATTRIBUTE",
        payload: {
          id: result.attribute.id,
          text: result.attribute.attribute_text || result.attribute.text,
        },
      });
    },
    [state.sessionId],
  );

  const removeAttribute = useCallback(
    async (id: string): Promise<void> => {
      if (!state.sessionId) {
        console.error("Cannot remove attribute: no active session");
        return;
      }

      const response = await fetch(`/api/game/attributes/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Failed to remove attribute: ${response.status}`);
      }
      dispatch({ type: "REMOVE_ATTRIBUTE", payload: id });
    },
    [state.sessionId],
  );

  const value: GameContextType = {
    state,
    startSession,
    restoreSession,
    loadCharacters,
    restoreActiveSession,
    restoreSessionById,
    resetSession,
    updateStats,
    updateFromSSE,
    updateAttributesFromSSE,
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
    setConversationHistory,
    appendFeelingText,
    setFeelingText,
    clearFeelingText,
    setTransformationCount,
    setLastGeneratedSeed,
    setLastSurroundingsImage,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useGame(): GameContextType {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error("useGame must be used within a GameProvider");
  }
  return context;
}
