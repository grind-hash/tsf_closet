/**
 * GameContext - ゲームセッション状態の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
} from "react";
import { useTranslation } from "react-i18next";
import type {
  Character,
  ConversationMessage,
  Ending,
  HistoryItem,
  SessionAttribute,
  SessionCharacter,
  SessionStats,
  SurroundingsImageState,
} from "../types";
import { API_BASE } from "../utils/api";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

export interface PlayMemoryState {
  systemEnabled: boolean;
  userEnabled: boolean;
  systemText: string | null;
  userText: string | null;
  systemUpdatedAt: string | null;
}

function mapPlayMemoryResponse(data: PlayMemoryApiResponse): PlayMemoryState {
  return {
    systemEnabled: data.system_enabled,
    userEnabled: data.user_enabled,
    systemText: data.system_text,
    userText: data.user_text,
    systemUpdatedAt: data.system_updated_at,
  };
}

import {
  createSessionCharacter as apiCreateSessionCharacter,
  deleteSessionCharacter as apiDeleteSessionCharacter,
  ensureProtagonistCharacter as apiEnsureProtagonistCharacter,
  updateSessionCharacter as apiUpdateSessionCharacter,
  applyPresetToSession,
  type CreateSessionCharacterPayload,
  listSessionCharacters,
  type UpdateSessionCharacterPayload,
} from "../apis/characters";
import {
  addSessionAttribute as apiAddSessionAttribute,
  branchSessionFromHistory as apiBranchSessionFromHistory,
  deleteActiveSession as apiDeleteActiveSession,
  fetchActiveSession as apiFetchActiveSession,
  fetchCharacters as apiFetchCharacters,
  regeneratePlayMemory as apiRegeneratePlayMemory,
  removeSessionAttribute as apiRemoveSessionAttribute,
  restoreSession as apiRestoreSession,
  updatePlayMemory as apiUpdatePlayMemory,
  type BranchSessionResponse,
  type PlayMemoryApiResponse,
} from "../apis/game";
import { ApiError } from "../utils/http";

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
  sessionCharacters: SessionCharacter[];
  playMemory: PlayMemoryState;
}

type GameAction =
  | {
      type: "START_SESSION";
      payload: {
        sessionId: string;
        character: Character;
        currentImage: string;
        playMemory?: PlayMemoryState;
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
        playMemory: PlayMemoryState;
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
  | {
      type: "REMOVE_HISTORY_ENTRY";
      payload: { historyId: string; restoredHistoryId: string };
    }
  | { type: "SET_SESSION_CHARACTERS"; payload: SessionCharacter[] }
  | { type: "SET_PLAY_MEMORY"; payload: PlayMemoryState }
  | { type: "UPSERT_SESSION_CHARACTER"; payload: SessionCharacter }
  | { type: "REMOVE_SESSION_CHARACTER"; payload: string }
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
  sessionCharacters: [],
  playMemory: {
    systemEnabled: true,
    userEnabled: true,
    systemText: null,
    userText: null,
    systemUpdatedAt: null,
  },
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
        playMemory: action.payload.playMemory ?? defaultState.playMemory,
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
        playMemory: action.payload.playMemory,
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
    case "REMOVE_HISTORY_ENTRY": {
      const { historyId, restoredHistoryId } = action.payload;
      const newHistory = state.history.filter((h) => h.id !== historyId);
      const removedIndex = state.history.findIndex((h) => h.id === historyId);
      // Determine new currentHistoryIndex
      let newIndex = state.currentHistoryIndex;
      if (newHistory.length === 0) {
        newIndex = -1;
      } else if (removedIndex <= state.currentHistoryIndex) {
        newIndex = Math.max(0, state.currentHistoryIndex - 1);
      }
      // Update currentImage to the restored history entry or previous
      let newImage = state.currentImage;
      if (restoredHistoryId && newHistory.length > 0) {
        newImage = `${API_BASE}/history/images/${restoredHistoryId}`;
      } else if (newHistory.length > 0) {
        const entry = newHistory[Math.min(newIndex, newHistory.length - 1)];
        newImage = `${API_BASE}/history/images/${entry.id}`;
      }
      return {
        ...state,
        history: newHistory,
        currentHistoryIndex: newIndex,
        currentImage: newImage,
        transformationCount: Math.max(0, state.transformationCount - 1),
      };
    }
    case "CLEAR_SESSION":
      return { ...defaultState, characters: state.characters };
    case "SET_SESSION_CHARACTERS":
      return { ...state, sessionCharacters: action.payload };
    case "SET_PLAY_MEMORY":
      return { ...state, playMemory: action.payload };
    case "UPSERT_SESSION_CHARACTER": {
      const incoming = action.payload;
      const idx = state.sessionCharacters.findIndex(
        (c) => c.id === incoming.id,
      );
      const next =
        idx >= 0
          ? state.sessionCharacters.map((c) =>
              c.id === incoming.id ? incoming : c,
            )
          : [...state.sessionCharacters, incoming];
      next.sort((a, b) => a.slot_index - b.slot_index);
      return { ...state, sessionCharacters: next };
    }
    case "REMOVE_SESSION_CHARACTER":
      return {
        ...state,
        sessionCharacters: state.sessionCharacters.filter(
          (c) => c.id !== action.payload,
        ),
      };
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
  ) => Promise<void>;
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
  /**
   * 履歴画像から新規セッションを分岐開始する。
   * 成功時は Game 状態を差し替え、session_id を返す。
   */
  startSessionFromHistory: (
    historyId: string,
    options?: { inheritStats?: boolean; selfMode?: boolean },
  ) => Promise<BranchSessionResponse>;
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
  navigateToHistoryById: (historyId: string) => boolean;
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
  removeHistoryEntry: (historyId: string, restoredHistoryId: string) => void;
  loadSessionCharacters: () => Promise<void>;
  ensureProtagonistCharacter: () => Promise<void>;
  addSessionCharacter: (
    payload: CreateSessionCharacterPayload,
  ) => Promise<SessionCharacter>;
  updateSessionCharacterAction: (
    characterId: string,
    payload: UpdateSessionCharacterPayload,
  ) => Promise<SessionCharacter>;
  removeSessionCharacter: (characterId: string) => Promise<void>;
  applyPresetToCurrentSession: (presetId: string) => Promise<SessionCharacter>;
  updatePlayMemory: (updates: {
    system_enabled?: boolean;
    user_enabled?: boolean;
    user_text?: string | null;
  }) => Promise<void>;
  regeneratePlayMemory: (language: string) => Promise<void>;
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
  play_memory?: {
    system_enabled?: boolean;
    user_enabled?: boolean;
    system_text?: string | null;
    user_text?: string | null;
    system_updated_at?: string | null;
  };
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
      playMemory: {
        systemEnabled: data.play_memory?.system_enabled ?? true,
        userEnabled: data.play_memory?.user_enabled ?? true,
        systemText: data.play_memory?.system_text ?? null,
        userText: data.play_memory?.user_text ?? null,
        systemUpdatedAt: data.play_memory?.system_updated_at ?? null,
      },
    },
  };
}

export function GameProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { showNotification } = useNotification();
  const {
    state: settingsState,
    setPlayMemorySystemEnabled,
    setPlayMemoryUserEnabled,
  } = useSettings();
  const [state, dispatch] = useReducer(gameReducer, defaultState);
  const previousPlayMemoryEnabledRef = useRef(settingsState.playMemoryEnabled);

  const syncPlayMemoryPreferences = useCallback(
    async (sessionId: string): Promise<PlayMemoryState | null> => {
      try {
        const data = await apiUpdatePlayMemory(sessionId, {
          system_enabled: settingsState.playMemorySystemEnabled,
          user_enabled: settingsState.playMemoryUserEnabled,
        });
        return mapPlayMemoryResponse(data);
      } catch (error) {
        // localStorage から復元しただけの古いセッションIDでは 404 になる。
        // 設定自体は保存済みで、実在するセッションの開始時に改めて同期
        // されるため黙って無視する(遊び方ガイド等、プレイ画面外での
        // トグルで警告が出るのを防ぐ)
        if (error instanceof ApiError && error.status === 404) return null;
        showNotification(
          "warning",
          t("settings.playMemory.sectionTitle"),
          t("settings.playMemory.error"),
        );
        return null;
      }
    },
    [
      settingsState.playMemorySystemEnabled,
      settingsState.playMemoryUserEnabled,
      showNotification,
      t,
    ],
  );

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

  useEffect(() => {
    const wasEnabled = previousPlayMemoryEnabledRef.current;
    previousPlayMemoryEnabledRef.current = settingsState.playMemoryEnabled;
    if (wasEnabled || !settingsState.playMemoryEnabled || !state.sessionId) {
      return;
    }
    void syncPlayMemoryPreferences(state.sessionId).then((playMemory) => {
      if (playMemory) {
        dispatch({ type: "SET_PLAY_MEMORY", payload: playMemory });
      }
    });
  }, [
    settingsState.playMemoryEnabled,
    state.sessionId,
    syncPlayMemoryPreferences,
  ]);

  const startSession = useCallback(
    async (sessionId: string, character: Character, currentImage: string) => {
      const playMemory = await syncPlayMemoryPreferences(sessionId);
      dispatch({
        type: "START_SESSION",
        payload: {
          sessionId,
          character,
          currentImage,
          ...(playMemory ? { playMemory } : {}),
        },
      });
    },
    [syncPlayMemoryPreferences],
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
          playMemory: {
            ...defaultState.playMemory,
            systemEnabled: settingsState.playMemorySystemEnabled,
            userEnabled: settingsState.playMemoryUserEnabled,
          },
        },
      });
      void syncPlayMemoryPreferences(sessionId).then((playMemory) => {
        if (playMemory) {
          dispatch({ type: "SET_PLAY_MEMORY", payload: playMemory });
        }
      });
    },
    [
      settingsState.playMemorySystemEnabled,
      settingsState.playMemoryUserEnabled,
      state.conversationHistory,
      syncPlayMemoryPreferences,
    ],
  );

  const loadCharacters = useCallback(async () => {
    try {
      const characters = await apiFetchCharacters();
      dispatch({ type: "SET_CHARACTERS", payload: characters });
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
      const data = await apiFetchActiveSession();
      const action = mapSessionResponse(
        data as Parameters<typeof mapSessionResponse>[0],
      );
      const playMemory = await syncPlayMemoryPreferences(data.session_id);
      if (playMemory) {
        action.payload.playMemory = playMemory;
      }
      dispatch(action);
      return true;
    } catch {
      return false;
    }
  }, [syncPlayMemoryPreferences]);

  const restoreSessionById = useCallback(
    async (sessionId: string) => {
      try {
        const data = await apiRestoreSession(sessionId);
        const action = mapSessionResponse(
          data as Parameters<typeof mapSessionResponse>[0],
        );
        const playMemory = await syncPlayMemoryPreferences(data.session_id);
        if (playMemory) {
          action.payload.playMemory = playMemory;
        }
        dispatch(action);
        return true;
      } catch {
        return false;
      }
    },
    [syncPlayMemoryPreferences],
  );

  const startSessionFromHistory = useCallback(
    async (
      historyId: string,
      options?: { inheritStats?: boolean; selfMode?: boolean },
    ): Promise<BranchSessionResponse> => {
      const data = await apiBranchSessionFromHistory(historyId, options);
      const action = mapSessionResponse(
        data as Parameters<typeof mapSessionResponse>[0] & {
          session_id: string;
        },
      );
      const playMemory = await syncPlayMemoryPreferences(data.session_id);
      if (playMemory) {
        action.payload.playMemory = playMemory;
      }
      dispatch(action);
      try {
        const records = await listSessionCharacters(data.session_id);
        dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
      } catch {
        dispatch({ type: "SET_SESSION_CHARACTERS", payload: [] });
      }
      return data;
    },
    [syncPlayMemoryPreferences],
  );

  const resetSession = useCallback(async () => {
    try {
      await apiDeleteActiveSession();
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

  const navigateToHistoryById = useCallback(
    (historyId: string): boolean => {
      const index = state.history.findIndex((h) => h.id === historyId);
      if (index >= 0) {
        dispatch({ type: "NAVIGATE_HISTORY", payload: index });
        return true;
      }
      return false;
    },
    [state.history],
  );

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

  const removeHistoryEntry = useCallback(
    (historyId: string, restoredHistoryId: string) => {
      dispatch({
        type: "REMOVE_HISTORY_ENTRY",
        payload: { historyId, restoredHistoryId },
      });
    },
    [],
  );

  const loadSessionCharacters = useCallback(async () => {
    if (!state.sessionId) {
      return;
    }
    try {
      const records = await listSessionCharacters(state.sessionId);
      dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
    } catch (error) {
      console.error("Failed to load session characters", error);
    }
  }, [state.sessionId]);

  const ensureProtagonistCharacter = useCallback(async () => {
    if (!state.sessionId) {
      return;
    }
    try {
      const records = await apiEnsureProtagonistCharacter(state.sessionId);
      dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
    } catch (error) {
      console.error("Failed to ensure protagonist character", error);
    }
  }, [state.sessionId]);

  const addSessionCharacter = useCallback(
    async (
      payload: CreateSessionCharacterPayload,
    ): Promise<SessionCharacter> => {
      if (!state.sessionId) {
        throw new Error("session_inactive");
      }
      const created = await apiCreateSessionCharacter(state.sessionId, payload);
      dispatch({ type: "UPSERT_SESSION_CHARACTER", payload: created });
      // re-sync to capture position reassignments
      try {
        const records = await listSessionCharacters(state.sessionId);
        dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
      } catch {
        // ignore
      }
      return created;
    },
    [state.sessionId],
  );

  const updateSessionCharacterAction = useCallback(
    async (
      characterId: string,
      payload: UpdateSessionCharacterPayload,
    ): Promise<SessionCharacter> => {
      if (!state.sessionId) {
        throw new Error("session_inactive");
      }
      const updated = await apiUpdateSessionCharacter(
        state.sessionId,
        characterId,
        payload,
      );
      dispatch({ type: "UPSERT_SESSION_CHARACTER", payload: updated });
      if (payload.slot_index !== undefined) {
        try {
          const records = await listSessionCharacters(state.sessionId);
          dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
        } catch {
          // ignore
        }
      }
      return updated;
    },
    [state.sessionId],
  );

  const removeSessionCharacter = useCallback(
    async (characterId: string): Promise<void> => {
      if (!state.sessionId) {
        throw new Error("session_inactive");
      }
      await apiDeleteSessionCharacter(state.sessionId, characterId);
      dispatch({ type: "REMOVE_SESSION_CHARACTER", payload: characterId });
      try {
        const records = await listSessionCharacters(state.sessionId);
        dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
      } catch {
        // ignore
      }
    },
    [state.sessionId],
  );

  const applyPresetToCurrentSession = useCallback(
    async (presetId: string): Promise<SessionCharacter> => {
      if (!state.sessionId) {
        throw new Error("session_inactive");
      }
      const created = await applyPresetToSession(state.sessionId, presetId);
      dispatch({ type: "UPSERT_SESSION_CHARACTER", payload: created });
      try {
        const records = await listSessionCharacters(state.sessionId);
        dispatch({ type: "SET_SESSION_CHARACTERS", payload: records });
      } catch {
        // ignore
      }
      return created;
    },
    [state.sessionId],
  );

  const addAttribute = useCallback(
    async (text: string): Promise<void> => {
      if (!state.sessionId) {
        console.error("Cannot add attribute: no active session");
        return;
      }

      const result = await apiAddSessionAttribute(state.sessionId, text);
      dispatch({
        type: "ADD_ATTRIBUTE",
        payload: {
          id: result.attribute.id,
          text: result.attribute.attribute_text || result.attribute.text || "",
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

      await apiRemoveSessionAttribute(id);
      dispatch({ type: "REMOVE_ATTRIBUTE", payload: id });
    },
    [state.sessionId],
  );

  const updatePlayMemory = useCallback(
    async (updates: {
      system_enabled?: boolean;
      user_enabled?: boolean;
      user_text?: string | null;
    }) => {
      if (!state.sessionId) return;
      const data = await apiUpdatePlayMemory(state.sessionId, updates);
      dispatch({
        type: "SET_PLAY_MEMORY",
        payload: mapPlayMemoryResponse(data),
      });
      if (updates.system_enabled !== undefined) {
        setPlayMemorySystemEnabled(data.system_enabled);
      }
      if (updates.user_enabled !== undefined) {
        setPlayMemoryUserEnabled(data.user_enabled);
      }
    },
    [setPlayMemorySystemEnabled, setPlayMemoryUserEnabled, state.sessionId],
  );

  const regeneratePlayMemory = useCallback(
    async (language: string) => {
      if (!state.sessionId) return;
      const data = await apiRegeneratePlayMemory(state.sessionId, language);
      dispatch({
        type: "SET_PLAY_MEMORY",
        payload: mapPlayMemoryResponse(data),
      });
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
    startSessionFromHistory,
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
    navigateToHistoryById,
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
    removeHistoryEntry,
    loadSessionCharacters,
    ensureProtagonistCharacter,
    addSessionCharacter,
    updateSessionCharacterAction,
    removeSessionCharacter,
    applyPresetToCurrentSession,
    updatePlayMemory,
    regeneratePlayMemory,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}

export function useGame(): GameContextType {
  const context = useContext(GameContext);
  if (!context) {
    throw new Error("useGame must be used within a GameProvider");
  }
  return context;
}
