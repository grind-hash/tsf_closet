/**
 * ChatContext - チャット状態の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  ChatMessage,
  InstructionType,
  PendingMessageIdentity,
} from "../types";

// チャット状態
interface ChatState {
  // メッセージ一覧
  messages: ChatMessage[];

  // 送信直後メッセージの一時 ID 管理
  pendingIdentities: PendingMessageIdentity[];

  // 入力状態
  inputText: string;
  instructionType: InstructionType;
  attachedImage: File | null;
  attachedImagePreview: string | null;

  // UI状態
  isStreaming: boolean;
  highlightedMessageId: string | null;
  scrollToMessageId: string | null;
}

// アクション型
type ChatAction =
  | { type: "SET_MESSAGES"; payload: ChatMessage[] }
  | { type: "ADD_MESSAGE"; payload: ChatMessage }
  | {
      type: "UPDATE_MESSAGE";
      payload: {
        id: string;
        content: string;
        extras?: Partial<ChatMessage>;
      };
    }
  | { type: "APPEND_TO_MESSAGE"; payload: { id: string; content: string } }
  | {
      type: "SET_MESSAGE_STREAMING";
      payload: { id: string; isStreaming: boolean };
    }
  | { type: "SET_INPUT_TEXT"; payload: string }
  | { type: "SET_INSTRUCTION_TYPE"; payload: InstructionType }
  | {
      type: "SET_ATTACHED_IMAGE";
      payload: { file: File | null; preview: string | null };
    }
  | { type: "SET_STREAMING"; payload: boolean }
  | { type: "SET_HIGHLIGHTED_MESSAGE"; payload: string | null }
  | { type: "SET_SCROLL_TO_MESSAGE"; payload: string | null }
  | { type: "UPSERT_PENDING_IDENTITY"; payload: PendingMessageIdentity }
  | {
      type: "ATTACH_FEELING_MESSAGE";
      payload: { tempToken: string; feelingMessageId: string };
    }
  | {
      type: "RESOLVE_PENDING_IDENTITY";
      payload: { tempToken: string; historyId: string };
    }
  | {
      type: "FINALIZE_PENDING_IDENTITY";
      payload: { tempToken: string; historyId?: string | null };
    }
  | { type: "FAIL_PENDING_IDENTITY"; payload: { tempToken: string } }
  | { type: "REPLACE_MESSAGE_ID"; payload: { oldId: string; newId: string } }
  | { type: "CLEAR_INPUT" }
  | { type: "CLEAR_MESSAGES" };

// 音声再生状態（チャット欄下部のオーディオコントロールバー用）
export type AudioPlaybackStatus = "idle" | "loading" | "playing" | "paused";

export interface AudioPlaybackState {
  messageId: string | null;
  status: AudioPlaybackStatus;
  currentTime: number;
  duration: number;
  error: string | null;
}

const defaultAudioPlayback: AudioPlaybackState = {
  messageId: null,
  status: "idle",
  currentTime: 0,
  duration: 0,
  error: null,
};

// 音声再生の環境設定（ミュート/音量/再生速度）。センシティブな内容を読み上げる
// 可能性があるため、初期状態は必ずミュートにし、localStorage に永続化する。
const AUDIO_PREFS_STORAGE_KEY = "tsf_closet_audio_prefs";

export interface AudioPreferences {
  muted: boolean;
  volume: number;
  playbackRate: number;
}

const defaultAudioPreferences: AudioPreferences = {
  muted: true,
  volume: 0.8,
  playbackRate: 1,
};

function loadAudioPreferences(): AudioPreferences {
  try {
    const raw = localStorage.getItem(AUDIO_PREFS_STORAGE_KEY);
    if (!raw) {
      return { ...defaultAudioPreferences };
    }
    const parsed = JSON.parse(raw) as Partial<AudioPreferences>;
    return {
      muted:
        typeof parsed.muted === "boolean"
          ? parsed.muted
          : defaultAudioPreferences.muted,
      volume:
        typeof parsed.volume === "number"
          ? Math.min(1, Math.max(0, parsed.volume))
          : defaultAudioPreferences.volume,
      playbackRate:
        typeof parsed.playbackRate === "number"
          ? Math.min(2, Math.max(0.5, parsed.playbackRate))
          : defaultAudioPreferences.playbackRate,
    };
  } catch {
    return { ...defaultAudioPreferences };
  }
}

function saveAudioPreferences(prefs: AudioPreferences): void {
  try {
    localStorage.setItem(AUDIO_PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage が利用できない環境では無視する
  }
}

// デフォルト状態
const defaultState: ChatState = {
  messages: [],
  pendingIdentities: [],
  inputText: "",
  instructionType: "dress_up",
  attachedImage: null,
  attachedImagePreview: null,
  isStreaming: false,
  highlightedMessageId: null,
  scrollToMessageId: null,
};

// Reducer
function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "SET_MESSAGES":
      return { ...state, messages: action.payload };
    case "ADD_MESSAGE":
      return { ...state, messages: [...state.messages, action.payload] };
    case "UPDATE_MESSAGE":
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === action.payload.id
            ? {
                ...msg,
                content: action.payload.content,
                ...action.payload.extras,
              }
            : msg,
        ),
      };
    case "APPEND_TO_MESSAGE":
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === action.payload.id
            ? { ...msg, content: msg.content + action.payload.content }
            : msg,
        ),
      };
    case "SET_MESSAGE_STREAMING":
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === action.payload.id
            ? { ...msg, isStreaming: action.payload.isStreaming }
            : msg,
        ),
      };
    case "SET_INPUT_TEXT":
      return { ...state, inputText: action.payload };
    case "SET_INSTRUCTION_TYPE":
      return { ...state, instructionType: action.payload };
    case "SET_ATTACHED_IMAGE":
      return {
        ...state,
        attachedImage: action.payload.file,
        attachedImagePreview: action.payload.preview,
      };
    case "SET_STREAMING":
      return { ...state, isStreaming: action.payload };
    case "SET_HIGHLIGHTED_MESSAGE":
      return { ...state, highlightedMessageId: action.payload };
    case "SET_SCROLL_TO_MESSAGE":
      return { ...state, scrollToMessageId: action.payload };
    case "UPSERT_PENDING_IDENTITY": {
      const existingIndex = state.pendingIdentities.findIndex(
        (identity) => identity.tempToken === action.payload.tempToken,
      );

      if (existingIndex === -1) {
        return {
          ...state,
          pendingIdentities: [...state.pendingIdentities, action.payload],
        };
      }

      const pendingIdentities = [...state.pendingIdentities];
      pendingIdentities[existingIndex] = action.payload;
      return { ...state, pendingIdentities };
    }
    case "ATTACH_FEELING_MESSAGE":
      return {
        ...state,
        pendingIdentities: state.pendingIdentities.map((identity) =>
          identity.tempToken === action.payload.tempToken
            ? {
                ...identity,
                feelingMessageId: action.payload.feelingMessageId,
              }
            : identity,
        ),
      };
    case "RESOLVE_PENDING_IDENTITY":
      return {
        ...state,
        pendingIdentities: state.pendingIdentities.map((identity) =>
          identity.tempToken === action.payload.tempToken
            ? {
                ...identity,
                resolvedHistoryId: action.payload.historyId,
                status: "resolvable",
              }
            : identity,
        ),
      };
    case "FINALIZE_PENDING_IDENTITY": {
      const identity = state.pendingIdentities.find(
        (entry) => entry.tempToken === action.payload.tempToken,
      );

      if (!identity) {
        return state;
      }

      const historyId = action.payload.historyId ?? identity.resolvedHistoryId;
      if (!historyId) {
        return {
          ...state,
          pendingIdentities: state.pendingIdentities.map((entry) =>
            entry.tempToken === action.payload.tempToken
              ? { ...entry, status: "failed" }
              : entry,
          ),
        };
      }

      return {
        ...state,
        messages: state.messages.map((message) => {
          if (message.id === identity.userMessageId) {
            return {
              ...message,
              id: `user-${historyId}`,
              relatedHistoryId: historyId,
              pendingToken: undefined,
              isStreaming: false,
            };
          }

          if (
            identity.feelingMessageId &&
            message.id === identity.feelingMessageId
          ) {
            return {
              ...message,
              id: `feeling-${historyId}`,
              relatedHistoryId: historyId,
              pendingToken: undefined,
              isStreaming: false,
            };
          }

          return message;
        }),
        pendingIdentities: state.pendingIdentities.filter(
          (entry) => entry.tempToken !== action.payload.tempToken,
        ),
      };
    }
    case "FAIL_PENDING_IDENTITY":
      return {
        ...state,
        pendingIdentities: state.pendingIdentities.map((identity) =>
          identity.tempToken === action.payload.tempToken
            ? { ...identity, status: "failed" }
            : identity,
        ),
      };
    case "REPLACE_MESSAGE_ID":
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === action.payload.oldId
            ? { ...message, id: action.payload.newId }
            : message,
        ),
      };
    case "CLEAR_INPUT":
      return {
        ...state,
        inputText: "",
        attachedImage: null,
        attachedImagePreview: null,
      };
    case "CLEAR_MESSAGES":
      return { ...state, messages: [] };
    default:
      return state;
  }
}

// Context型定義
interface ChatContextType {
  state: ChatState;
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (
    id: string,
    content: string,
    extras?: Partial<ChatMessage>,
  ) => void;
  appendToMessage: (id: string, content: string) => void;
  setMessageStreaming: (id: string, isStreaming: boolean) => void;
  setInputText: (text: string) => void;
  setInstructionType: (type: InstructionType) => void;
  attachImage: (file: File | null) => void;
  setStreaming: (isStreaming: boolean) => void;
  upsertPendingIdentity: (identity: PendingMessageIdentity) => void;
  attachFeelingMessage: (tempToken: string, feelingMessageId: string) => void;
  resolvePendingIdentity: (tempToken: string, historyId: string) => void;
  finalizePendingIdentity: (
    tempToken: string,
    historyId?: string | null,
  ) => void;
  failPendingIdentity: (tempToken: string) => void;
  replaceMessageId: (oldId: string, newId: string) => void;
  getMessageHistoryId: (messageId: string) => string | null;
  getLatestPendingIdentity: () => PendingMessageIdentity | null;
  highlightMessage: (messageId: string | null, duration?: number) => void;
  scrollToMessage: (messageId: string | null) => void;
  clearInput: () => void;
  clearMessages: () => void;
  messageListRef: React.RefObject<HTMLDivElement | null>;
  audioPlayback: AudioPlaybackState;
  playMessageAudio: (
    messageId: string,
    fetchAudio: () => Promise<Blob>,
  ) => Promise<void>;
  toggleAudioPause: () => void;
  stopAudio: () => void;
  seekAudio: (time: number) => void;
  audioPrefs: AudioPreferences;
  setAudioVolume: (volume: number) => void;
  setAudioMuted: (muted: boolean) => void;
  setAudioPlaybackRate: (rate: number) => void;
}

// Context作成
const ChatContext = createContext<ChatContextType | null>(null);

// Provider コンポーネント
export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, defaultState);
  const messageListRef = useRef<HTMLDivElement | null>(null);

  const [audioPlayback, setAudioPlayback] =
    useState<AudioPlaybackState>(defaultAudioPlayback);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const audioRequestIdRef = useRef(0);
  const [audioPrefs, setAudioPrefsState] = useState<AudioPreferences>(() =>
    loadAudioPreferences(),
  );

  const revokeAudioUrl = useCallback(() => {
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }, []);

  const ensureAudioElement = useCallback(() => {
    if (audioElementRef.current) {
      return audioElementRef.current;
    }

    const audio = new Audio();
    audio.volume = audioPrefs.volume;
    audio.muted = audioPrefs.muted;
    audio.playbackRate = audioPrefs.playbackRate;
    audio.addEventListener("timeupdate", () => {
      setAudioPlayback((prev) => ({ ...prev, currentTime: audio.currentTime }));
    });
    audio.addEventListener("loadedmetadata", () => {
      setAudioPlayback((prev) => ({
        ...prev,
        duration: Number.isFinite(audio.duration) ? audio.duration : 0,
      }));
    });
    audio.addEventListener("play", () => {
      setAudioPlayback((prev) => ({ ...prev, status: "playing" }));
    });
    audio.addEventListener("pause", () => {
      setAudioPlayback((prev) =>
        prev.status === "playing" ? { ...prev, status: "paused" } : prev,
      );
    });
    audio.addEventListener("ended", () => {
      // 再生完了で自動にバーを閉じない。先頭に巻き戻して paused にし、
      // 音量/再生速度の調整や再生をそのまま行えるようにする。
      audio.currentTime = 0;
      setAudioPlayback((prev) => ({
        ...prev,
        status: "paused",
        currentTime: 0,
      }));
    });
    audioElementRef.current = audio;
    return audio;
  }, [audioPrefs]);

  const playMessageAudio = useCallback(
    async (messageId: string, fetchAudio: () => Promise<Blob>) => {
      const requestId = ++audioRequestIdRef.current;
      const audio = ensureAudioElement();
      audio.pause();
      revokeAudioUrl();
      setAudioPlayback({
        messageId,
        status: "loading",
        currentTime: 0,
        duration: 0,
        error: null,
      });

      try {
        const blob = await fetchAudio();
        // ロード中に停止または別メッセージの再生が開始されていたら結果を無視する
        if (audioRequestIdRef.current !== requestId) {
          return;
        }
        const url = URL.createObjectURL(blob);
        audioUrlRef.current = url;
        audio.src = url;
        audio.volume = audioPrefs.volume;
        audio.muted = audioPrefs.muted;
        audio.playbackRate = audioPrefs.playbackRate;
        await audio.play();
        setAudioPlayback({
          messageId,
          status: "playing",
          currentTime: 0,
          duration: 0,
          error: null,
        });
      } catch (error) {
        if (audioRequestIdRef.current !== requestId) {
          return;
        }
        revokeAudioUrl();
        setAudioPlayback({
          messageId,
          status: "idle",
          currentTime: 0,
          duration: 0,
          error: String((error as Error)?.message ?? error),
        });
      }
    },
    [ensureAudioElement, revokeAudioUrl, audioPrefs],
  );

  const toggleAudioPause = useCallback(() => {
    const audio = audioElementRef.current;
    if (!audio) {
      return;
    }
    if (audio.paused) {
      void audio.play();
    } else {
      audio.pause();
    }
  }, []);

  const stopAudio = useCallback(() => {
    audioRequestIdRef.current += 1;
    const audio = audioElementRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    revokeAudioUrl();
    setAudioPlayback(defaultAudioPlayback);
  }, [revokeAudioUrl]);

  const seekAudio = useCallback((time: number) => {
    const audio = audioElementRef.current;
    if (audio) {
      audio.currentTime = time;
    }
  }, []);

  const setAudioVolume = useCallback((volume: number) => {
    const clamped = Math.min(1, Math.max(0, volume));
    const audio = audioElementRef.current;
    if (audio) {
      audio.volume = clamped;
    }
    setAudioPrefsState((prev) => {
      const next = { ...prev, volume: clamped };
      saveAudioPreferences(next);
      return next;
    });
  }, []);

  const setAudioMuted = useCallback((muted: boolean) => {
    const audio = audioElementRef.current;
    if (audio) {
      audio.muted = muted;
    }
    setAudioPrefsState((prev) => {
      const next = { ...prev, muted };
      saveAudioPreferences(next);
      return next;
    });
  }, []);

  const setAudioPlaybackRate = useCallback((rate: number) => {
    const clamped = Math.min(2, Math.max(0.5, rate));
    const audio = audioElementRef.current;
    if (audio) {
      audio.playbackRate = clamped;
    }
    setAudioPrefsState((prev) => {
      const next = { ...prev, playbackRate: clamped };
      saveAudioPreferences(next);
      return next;
    });
  }, []);

  const setMessages = useCallback((messages: ChatMessage[]) => {
    dispatch({ type: "SET_MESSAGES", payload: messages });
  }, []);

  const addMessage = useCallback((message: ChatMessage) => {
    dispatch({ type: "ADD_MESSAGE", payload: message });
  }, []);

  const updateMessage = useCallback(
    (id: string, content: string, extras?: Partial<ChatMessage>) => {
      dispatch({ type: "UPDATE_MESSAGE", payload: { id, content, extras } });
    },
    [],
  );

  const appendToMessage = useCallback((id: string, content: string) => {
    dispatch({ type: "APPEND_TO_MESSAGE", payload: { id, content } });
  }, []);

  const setMessageStreaming = useCallback(
    (id: string, isStreaming: boolean) => {
      dispatch({ type: "SET_MESSAGE_STREAMING", payload: { id, isStreaming } });
    },
    [],
  );

  const setInputText = useCallback((text: string) => {
    dispatch({ type: "SET_INPUT_TEXT", payload: text });
  }, []);

  const setInstructionType = useCallback((type: InstructionType) => {
    dispatch({ type: "SET_INSTRUCTION_TYPE", payload: type });
  }, []);

  const attachImage = useCallback((file: File | null) => {
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        dispatch({
          type: "SET_ATTACHED_IMAGE",
          payload: { file, preview: reader.result as string },
        });
      };
      reader.readAsDataURL(file);
    } else {
      dispatch({
        type: "SET_ATTACHED_IMAGE",
        payload: { file: null, preview: null },
      });
    }
  }, []);

  const setStreaming = useCallback((isStreaming: boolean) => {
    dispatch({ type: "SET_STREAMING", payload: isStreaming });
  }, []);

  const upsertPendingIdentity = useCallback(
    (identity: PendingMessageIdentity) => {
      dispatch({ type: "UPSERT_PENDING_IDENTITY", payload: identity });
    },
    [],
  );

  const attachFeelingMessage = useCallback(
    (tempToken: string, feelingMessageId: string) => {
      dispatch({
        type: "ATTACH_FEELING_MESSAGE",
        payload: { tempToken, feelingMessageId },
      });
    },
    [],
  );

  const resolvePendingIdentity = useCallback(
    (tempToken: string, historyId: string) => {
      dispatch({
        type: "RESOLVE_PENDING_IDENTITY",
        payload: { tempToken, historyId },
      });
    },
    [],
  );

  const finalizePendingIdentity = useCallback(
    (tempToken: string, historyId?: string | null) => {
      dispatch({
        type: "FINALIZE_PENDING_IDENTITY",
        payload: { tempToken, historyId },
      });
    },
    [],
  );

  const failPendingIdentity = useCallback((tempToken: string) => {
    dispatch({ type: "FAIL_PENDING_IDENTITY", payload: { tempToken } });
  }, []);

  const replaceMessageId = useCallback((oldId: string, newId: string) => {
    dispatch({ type: "REPLACE_MESSAGE_ID", payload: { oldId, newId } });
  }, []);

  const getMessageHistoryId = useCallback(
    (messageId: string): string | null => {
      const message = state.messages.find((entry) => entry.id === messageId);
      if (!message) {
        return null;
      }

      if (message.relatedHistoryId) {
        return message.relatedHistoryId;
      }

      const match = message.id.match(/^(?:user|feeling)-(.+)$/);
      if (!match) {
        return null;
      }

      const candidate = match[1];
      return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        candidate,
      )
        ? candidate
        : null;
    },
    [state.messages],
  );

  const getLatestPendingIdentity = useCallback(() => {
    return state.pendingIdentities[state.pendingIdentities.length - 1] ?? null;
  }, [state.pendingIdentities]);

  const highlightMessage = useCallback(
    (messageId: string | null, duration = 2000) => {
      dispatch({ type: "SET_HIGHLIGHTED_MESSAGE", payload: messageId });
      if (messageId && duration > 0) {
        setTimeout(() => {
          dispatch({ type: "SET_HIGHLIGHTED_MESSAGE", payload: null });
        }, duration);
      }
    },
    [],
  );

  const scrollToMessage = useCallback((messageId: string | null) => {
    dispatch({ type: "SET_SCROLL_TO_MESSAGE", payload: messageId });
    // スクロール後にクリア
    if (messageId) {
      setTimeout(() => {
        dispatch({ type: "SET_SCROLL_TO_MESSAGE", payload: null });
      }, 500);
    }
  }, []);

  const clearInput = useCallback(() => {
    dispatch({ type: "CLEAR_INPUT" });
  }, []);

  const clearMessages = useCallback(() => {
    dispatch({ type: "CLEAR_MESSAGES" });
  }, []);

  const value: ChatContextType = {
    state,
    setMessages,
    addMessage,
    updateMessage,
    appendToMessage,
    setMessageStreaming,
    setInputText,
    setInstructionType,
    attachImage,
    setStreaming,
    upsertPendingIdentity,
    attachFeelingMessage,
    resolvePendingIdentity,
    finalizePendingIdentity,
    failPendingIdentity,
    replaceMessageId,
    getMessageHistoryId,
    getLatestPendingIdentity,
    highlightMessage,
    scrollToMessage,
    clearInput,
    clearMessages,
    messageListRef,
    audioPlayback,
    playMessageAudio,
    toggleAudioPause,
    stopAudio,
    seekAudio,
    audioPrefs,
    setAudioVolume,
    setAudioMuted,
    setAudioPlaybackRate,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

// Custom Hook
// eslint-disable-next-line react-refresh/only-export-components
export function useChat(): ChatContextType {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChat must be used within a ChatProvider");
  }
  return context;
}
