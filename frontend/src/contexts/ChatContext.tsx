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
  type ReactNode,
} from "react";
import type { ChatMessage, InstructionType } from "../types";

// チャット状態
interface ChatState {
  // メッセージ一覧
  messages: ChatMessage[];

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
  | { type: "UPDATE_MESSAGE"; payload: { id: string; content: string } }
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
  | { type: "CLEAR_INPUT" }
  | { type: "CLEAR_MESSAGES" };

// デフォルト状態
const defaultState: ChatState = {
  messages: [],
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
            ? { ...msg, content: action.payload.content }
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
  updateMessage: (id: string, content: string) => void;
  appendToMessage: (id: string, content: string) => void;
  setMessageStreaming: (id: string, isStreaming: boolean) => void;
  setInputText: (text: string) => void;
  setInstructionType: (type: InstructionType) => void;
  attachImage: (file: File | null) => void;
  setStreaming: (isStreaming: boolean) => void;
  highlightMessage: (messageId: string | null, duration?: number) => void;
  scrollToMessage: (messageId: string | null) => void;
  clearInput: () => void;
  clearMessages: () => void;
  messageListRef: React.RefObject<HTMLDivElement | null>;
}

// Context作成
const ChatContext = createContext<ChatContextType | null>(null);

// Provider コンポーネント
export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, defaultState);
  const messageListRef = useRef<HTMLDivElement | null>(null);

  const setMessages = useCallback((messages: ChatMessage[]) => {
    dispatch({ type: "SET_MESSAGES", payload: messages });
  }, []);

  const addMessage = useCallback((message: ChatMessage) => {
    dispatch({ type: "ADD_MESSAGE", payload: message });
  }, []);

  const updateMessage = useCallback((id: string, content: string) => {
    dispatch({ type: "UPDATE_MESSAGE", payload: { id, content } });
  }, []);

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
      }, 100);
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
    highlightMessage,
    scrollToMessage,
    clearInput,
    clearMessages,
    messageListRef,
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
