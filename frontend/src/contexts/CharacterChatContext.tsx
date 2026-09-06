/**
 * キャラチャットの共有状態。/talk 配下だけで提供する(App.tsx で包む)。
 *
 * スレッド一覧・表示中スレッド・送信中の下書き(ストリーム)・立ち絵の描き直しを持ち、
 * SSE の各イベントをここで state へ反映する(AdventureContext.submitTalk と同じ流れ)。
 * 通常ゲームの GameContext / useGameSSE には統合しない。
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  type CharacterChatMessage,
  type CharacterChatPhase,
  type CharacterChatSourceRequest,
  type CharacterChatThread,
  createCharacterChatThread,
  deleteCharacterChatThread,
  fetchCharacterChatThread,
  fetchCharacterChatThreads,
  openBaseCharacterChatThread,
  resetCharacterChatAppearance,
  setCharacterChatAppearance,
  streamCharacterChatMessage,
  streamCharacterChatPortrait,
} from "../apis/characterChat";
import type { AdventureSourceSelection } from "../components/adventure/AdventureSessionPickerModal";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

interface CharacterChatContextValue {
  threads: CharacterChatThread[];
  threadsLoading: boolean;
  activeThread: CharacterChatThread | null;
  threadLoading: boolean;
  /** 発言の送信中(判定〜complete まで) */
  sending: boolean;
  phase: CharacterChatPhase | "idle";
  /** ストリーミング中の返答 */
  draft: string;
  /** 送信済みでまだ messages に載っていない自分の発言 */
  pendingInput: string | null;
  /** 姿の差し替え・立ち絵の描き直し中 */
  portraitBusy: boolean;
  error: string | null;
  refreshThreads: () => Promise<void>;
  openBase: () => Promise<string | null>;
  createFromSource: (
    selection: AdventureSourceSelection,
    options?: { generatePortrait?: boolean },
  ) => Promise<string | null>;
  /** createFromSource で立ち絵生成を予約したスレッドなら true を 1 回だけ返す */
  takePendingPortrait: (threadId: string) => boolean;
  loadThread: (threadId: string) => Promise<CharacterChatThread | null>;
  deleteThread: (threadId: string) => Promise<boolean>;
  submitMessage: (text: string) => Promise<CharacterChatMessage | null>;
  setAppearanceFromSource: (
    selection: AdventureSourceSelection,
  ) => Promise<boolean>;
  regeneratePortrait: () => Promise<boolean>;
  resetAppearance: () => Promise<boolean>;
  clearError: () => void;
}

const CharacterChatContext = createContext<CharacterChatContextValue | null>(
  null,
);

function selectionToRequest(
  selection: AdventureSourceSelection,
): CharacterChatSourceRequest {
  if (selection.origin === "prompt_expander") {
    return { source_prompt_expander_entry_id: selection.promptExpanderEntryId };
  }
  return {
    source_session_id: selection.sessionId,
    source_history_id: selection.historyId,
  };
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function CharacterChatProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { addTotalCost } = useSettings();
  const { showNotification } = useNotification();
  const [threads, setThreads] = useState<CharacterChatThread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [activeThread, setActiveThread] = useState<CharacterChatThread | null>(
    null,
  );
  const [threadLoading, setThreadLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [phase, setPhase] = useState<CharacterChatPhase | "idle">("idle");
  const [draft, setDraft] = useState("");
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const [portraitBusy, setPortraitBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 送信中に別スレッドへ移動しても古いストリームの結果を混ぜない
  const activeThreadIdRef = useRef<string | null>(null);
  activeThreadIdRef.current = activeThread?.id ?? null;
  // Hub で「立ち絵を生成する」を ON にして作ったスレッド。Room が開いた時点で 1 回だけ描く
  const pendingPortraitRef = useRef<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const refreshThreads = useCallback(async () => {
    setThreadsLoading(true);
    try {
      setThreads(await fetchCharacterChatThreads());
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.loadFailed")));
    } finally {
      setThreadsLoading(false);
    }
  }, [t]);

  const openBase = useCallback(async () => {
    setThreadLoading(true);
    try {
      const thread = await openBaseCharacterChatThread();
      return thread.id;
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.createFailed")));
      return null;
    } finally {
      setThreadLoading(false);
    }
  }, [t]);

  const createFromSource = useCallback(
    async (
      selection: AdventureSourceSelection,
      options?: { generatePortrait?: boolean },
    ) => {
      setThreadLoading(true);
      try {
        const thread = await createCharacterChatThread(
          selectionToRequest(selection),
        );
        setThreads((prev) => [thread, ...prev]);
        pendingPortraitRef.current = options?.generatePortrait
          ? thread.id
          : null;
        return thread.id;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.createFailed")));
        return null;
      } finally {
        setThreadLoading(false);
      }
    },
    [t],
  );

  const takePendingPortrait = useCallback((threadId: string) => {
    if (pendingPortraitRef.current !== threadId) return false;
    pendingPortraitRef.current = null;
    return true;
  }, []);

  const loadThread = useCallback(
    async (threadId: string) => {
      setThreadLoading(true);
      setDraft("");
      setPendingInput(null);
      setPhase("idle");
      try {
        const thread = await fetchCharacterChatThread(threadId);
        setActiveThread(thread);
        return thread;
      } catch (err) {
        setActiveThread(null);
        setError(errorMessage(err, t("characterChat.errors.loadFailed")));
        return null;
      } finally {
        setThreadLoading(false);
      }
    },
    [t],
  );

  const deleteThread = useCallback(
    async (threadId: string) => {
      try {
        await deleteCharacterChatThread(threadId);
        setThreads((prev) => prev.filter((thread) => thread.id !== threadId));
        setActiveThread((prev) => (prev?.id === threadId ? null : prev));
        return true;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.deleteFailed")));
        return false;
      }
    },
    [t],
  );

  const submitMessage = useCallback(
    async (text: string) => {
      const content = text.trim();
      const threadId = activeThreadIdRef.current;
      if (!content || !threadId || sending) return null;
      setSending(true);
      setError(null);
      setDraft("");
      setPendingInput(content);
      setPhase("plan");
      let characterMessage: CharacterChatMessage | null = null;
      try {
        await streamCharacterChatMessage(threadId, { content }, (event) => {
          if (activeThreadIdRef.current !== threadId) return;
          if (event.type === "status") {
            setPhase(event.data.phase);
          } else if (event.type === "chat_chunk") {
            setDraft((prev) =>
              prev ? prev + event.data.chunk : event.data.chunk.trimStart(),
            );
          } else if (event.type === "chat_done") {
            characterMessage = event.data.character_message;
            const { user_message, character_message, thread } = event.data;
            setActiveThread((prev) =>
              prev && prev.id === threadId
                ? {
                    ...prev,
                    message_count: thread.message_count,
                    updated_at: thread.updated_at,
                    last_message: {
                      role: character_message.role,
                      content: character_message.content,
                      created_at: character_message.created_at,
                    },
                    messages: [
                      ...(prev.messages ?? []),
                      user_message,
                      character_message,
                    ],
                  }
                : prev,
            );
            setPendingInput(null);
            setDraft("");
          } else if (event.type === "portrait_image") {
            const { image_url, appearance } = event.data;
            setActiveThread((prev) =>
              prev && prev.id === threadId
                ? {
                    ...prev,
                    portrait_url: image_url,
                    portrait_missing: false,
                    appearance,
                  }
                : prev,
            );
          } else if (event.type === "portrait_error") {
            showNotification(
              "warning",
              t("characterChat.errors.portraitFailed"),
              event.data.message,
            );
          } else if (event.type === "cost") {
            const cost = Number(event.data.cost_usd);
            if (Number.isFinite(cost) && cost > 0) addTotalCost(cost);
          } else if (event.type === "error") {
            setError(event.data.message);
          }
        });
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.sendFailed")));
      } finally {
        if (activeThreadIdRef.current === threadId) {
          setSending(false);
          setPhase("idle");
          setDraft("");
          setPendingInput(null);
        }
      }
      return characterMessage;
    },
    [sending, addTotalCost, showNotification, t],
  );

  const setAppearanceFromSource = useCallback(
    async (selection: AdventureSourceSelection) => {
      const threadId = activeThreadIdRef.current;
      if (!threadId) return false;
      setPortraitBusy(true);
      try {
        const thread = await setCharacterChatAppearance(
          threadId,
          selectionToRequest(selection),
        );
        setActiveThread((prev) =>
          prev && prev.id === threadId
            ? { ...prev, ...thread, messages: prev.messages }
            : prev,
        );
        return true;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.appearanceFailed")));
        return false;
      } finally {
        setPortraitBusy(false);
      }
    },
    [t],
  );

  const regeneratePortrait = useCallback(async () => {
    const threadId = activeThreadIdRef.current;
    if (!threadId || portraitBusy) return false;
    setPortraitBusy(true);
    let ok = false;
    try {
      await streamCharacterChatPortrait(threadId, (event) => {
        if (activeThreadIdRef.current !== threadId) return;
        if (event.type === "portrait_image") {
          ok = true;
          const { image_url, appearance } = event.data;
          setActiveThread((prev) =>
            prev && prev.id === threadId
              ? {
                  ...prev,
                  portrait_url: image_url,
                  portrait_missing: false,
                  appearance,
                }
              : prev,
          );
        } else if (event.type === "cost") {
          const cost = Number(event.data.cost_usd);
          if (Number.isFinite(cost) && cost > 0) addTotalCost(cost);
        } else if (event.type === "error") {
          setError(event.data.message);
        }
      });
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.portraitFailed")));
    } finally {
      setPortraitBusy(false);
    }
    return ok;
  }, [portraitBusy, addTotalCost, t]);

  const resetAppearance = useCallback(async () => {
    const threadId = activeThreadIdRef.current;
    if (!threadId || portraitBusy) return false;
    setPortraitBusy(true);
    try {
      const thread = await resetCharacterChatAppearance(threadId);
      setActiveThread((prev) =>
        prev && prev.id === threadId
          ? { ...prev, ...thread, messages: prev.messages }
          : prev,
      );
      return true;
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.appearanceFailed")));
      return false;
    } finally {
      setPortraitBusy(false);
    }
  }, [portraitBusy, t]);

  const value = useMemo<CharacterChatContextValue>(
    () => ({
      threads,
      threadsLoading,
      activeThread,
      threadLoading,
      sending,
      phase,
      draft,
      pendingInput,
      portraitBusy,
      error,
      refreshThreads,
      openBase,
      createFromSource,
      takePendingPortrait,
      loadThread,
      deleteThread,
      submitMessage,
      setAppearanceFromSource,
      regeneratePortrait,
      resetAppearance,
      clearError,
    }),
    [
      threads,
      threadsLoading,
      activeThread,
      threadLoading,
      sending,
      phase,
      draft,
      pendingInput,
      portraitBusy,
      error,
      refreshThreads,
      openBase,
      createFromSource,
      takePendingPortrait,
      loadThread,
      deleteThread,
      submitMessage,
      setAppearanceFromSource,
      regeneratePortrait,
      resetAppearance,
      clearError,
    ],
  );

  return (
    <CharacterChatContext.Provider value={value}>
      {children}
    </CharacterChatContext.Provider>
  );
}

export function useCharacterChat(): CharacterChatContextValue {
  const context = useContext(CharacterChatContext);
  if (!context) {
    throw new Error(
      "useCharacterChat must be used within CharacterChatProvider",
    );
  }
  return context;
}
