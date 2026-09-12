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
  type CharacterChatAdventureAppearanceMode,
  type CharacterChatAvatarMode,
  type CharacterChatMessage,
  type CharacterChatMessageRequest,
  type CharacterChatPhase,
  type CharacterChatPortraitOptions,
  type CharacterChatSourceRequest,
  type CharacterChatThread,
  createCharacterChatThread,
  deleteCharacterChatThread,
  fetchCharacterChatThread,
  fetchCharacterChatThreads,
  openAdventureCharacterChatThread,
  openBaseCharacterChatThread,
  resetCharacterChatAppearance,
  setCharacterChatAdventureAppearance,
  setCharacterChatAppearance,
  setCharacterChatAvatar,
  streamCharacterChatMessage,
  streamCharacterChatPortrait,
} from "../apis/characterChat";
import type { AdventureSourceSelection } from "../components/adventure/AdventureSessionPickerModal";
import {
  type UseAdventureVoiceResult,
  useAdventureVoice,
} from "../hooks/useAdventureVoice";
import { stripStageDirections } from "../utils/adventureDialogue";
import { textToVoiceSegments } from "../utils/adventureVoiceSegments";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

interface CharacterChatContextValue {
  voice: UseAdventureVoiceResult;
  speakMessage: (message: CharacterChatMessage) => void;
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
  /** 表示中スレッドの姿の差し替え・立ち絵の描き直し中 */
  portraitBusy: boolean;
  /** portraitBusy の内訳(portrait = 画像生成中、appearance = 差し替え/リセット中) */
  portraitBusyKind: CharacterChatPortraitBusyKind | null;
  error: string | null;
  refreshThreads: () => Promise<void>;
  openBase: () => Promise<string | null>;
  /** TSF シナリオの攻略対象と話すスレッドを開く(run ごとに 1 件) */
  openAdventure: (runId: string) => Promise<string | null>;
  createFromSource: (
    selection: AdventureSourceSelection,
    options?: { generatePortrait?: boolean },
  ) => Promise<string | null>;
  /** createFromSource で立ち絵生成を予約したスレッドなら true を 1 回だけ返す */
  takePendingPortrait: (threadId: string) => boolean;
  loadThread: (threadId: string) => Promise<CharacterChatThread | null>;
  leaveThread: () => void;
  deleteThread: (threadId: string) => Promise<boolean>;
  submitMessage: (text: string) => Promise<CharacterChatMessage | null>;
  setAppearanceFromSource: (
    selection: AdventureSourceSelection,
  ) => Promise<boolean>;
  /** 立ち絵を描き直す。threadId 省略時は表示中スレッド。スレッドごとに並行できる */
  regeneratePortrait: (
    threadId?: string,
    options?: CharacterChatPortraitOptions,
  ) => Promise<boolean>;
  resetAppearance: () => Promise<boolean>;
  /** adventure 種: 姿を run の画像に切り替える */
  setAdventureAppearance: (
    mode: Exclude<CharacterChatAdventureAppearanceMode, "custom">,
  ) => Promise<boolean>;
  /** 3D モデルの表示を切り替える(自動 / 2D 立ち絵 / 登録済みモデル) */
  setAvatar: (
    mode: CharacterChatAvatarMode,
    avatarId?: string | null,
  ) => Promise<boolean>;
  /** 3D モデルの読込に失敗したら立ち絵へ戻す(スレッド切替でリセット) */
  avatarFailed: boolean;
  setAvatarFailed: (failed: boolean) => void;
  /** ENABLE_PROMPT_PREVIEW。開発者向けの案内を出し分ける */
  promptPreviewEnabled: boolean;
  /** 一覧をまだ取っていなければ取る(会話画面へ直接来たとき用) */
  ensureThreadsLoaded: () => void;
  clearError: () => void;
}

export type CharacterChatPortraitBusyKind = "portrait" | "appearance";

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
  const { addTotalCost, state: settingsState } = useSettings();
  const voice = useAdventureVoice({
    available: settingsState.ttsEnabled,
    speakerId:
      settingsState.ttsStyleId?.trim() ||
      settingsState.ttsSpeakerId?.trim() ||
      null,
    engineDir: settingsState.ttsEngineDir,
    useGpu: settingsState.ttsUseGpu,
  });
  const speakMessage = useCallback(
    (message: CharacterChatMessage) => {
      const key = `chat:${message.id}`;
      voice.speakSegments(
        textToVoiceSegments(stripStageDirections(message.content), key),
        key,
      );
    },
    [voice.speakSegments],
  );
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
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
  // 姿の処理はスレッド単位で追う。画像生成は 1 分近くかかるため、別スレッドへ
  // 移動しても続行し、戻ったときに反映する(表示中スレッドの分だけ busy を出す)
  const [busyPortraits, setBusyPortraits] = useState<
    Record<string, CharacterChatPortraitBusyKind>
  >({});
  const busyPortraitsRef = useRef(busyPortraits);
  busyPortraitsRef.current = busyPortraits;
  const [error, setError] = useState<string | null>(null);
  const [avatarFailed, setAvatarFailed] = useState(false);
  const [promptPreviewEnabled, setPromptPreviewEnabled] = useState(false);
  // 送信中に別スレッドへ移動しても古いストリームの結果を混ぜない
  const activeThreadIdRef = useRef<string | null>(null);
  activeThreadIdRef.current = activeThread?.id ?? null;
  const threadEpochRef = useRef(0);
  // Hub で「立ち絵を生成する」を ON にして作ったスレッド。Room が開いた時点で 1 回だけ描く
  const pendingPortraitRef = useRef<string | null>(null);

  const clearError = useCallback(() => setError(null), []);
  const markPortraitBusy = useCallback(
    (threadId: string, kind: CharacterChatPortraitBusyKind | null) => {
      setBusyPortraits((prev) => {
        const next = { ...prev };
        if (kind) next[threadId] = kind;
        else delete next[threadId];
        busyPortraitsRef.current = next;
        return next;
      });
    },
    [],
  );
  const applyThreadUpdate = useCallback(
    (threadId: string, patch: Partial<CharacterChatThread>) => {
      setActiveThread((prev) =>
        prev && prev.id === threadId ? { ...prev, ...patch } : prev,
      );
      setThreads((prev) =>
        prev.map((thread) =>
          thread.id === threadId ? { ...thread, ...patch } : thread,
        ),
      );
    },
    [],
  );

  // 一覧を一度でも取りにいったか。会話画面へ直接来たときの取りこぼしを防ぐ
  const threadsRequestedRef = useRef(false);

  const refreshThreads = useCallback(async () => {
    threadsRequestedRef.current = true;
    setThreadsLoading(true);
    try {
      const list = await fetchCharacterChatThreads();
      setThreads(list.threads);
      setPromptPreviewEnabled(list.enablePromptPreview);
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.loadFailed")));
    } finally {
      setThreadsLoading(false);
    }
  }, [t]);

  /**
   * 一覧をまだ取っていなければ取る。
   *
   * 一覧のペイロードには ENABLE_PROMPT_PREVIEW が乗っており、入口(ハブ)を通らず
   * /talk/:threadId へ直接来たときは取りこぼす。ハブは毎回 refreshThreads で
   * 取り直すため、こちらは初回だけでよい。
   */
  const ensureThreadsLoaded = useCallback(() => {
    if (threadsRequestedRef.current) return;
    void refreshThreads();
  }, [refreshThreads]);

  const openAdventure = useCallback(
    async (runId: string) => {
      setThreadLoading(true);
      try {
        const thread = await openAdventureCharacterChatThread(runId);
        setThreads((prev) =>
          prev.some((item) => item.id === thread.id)
            ? prev.map((item) => (item.id === thread.id ? thread : item))
            : [thread, ...prev],
        );
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
      const epoch = ++threadEpochRef.current;
      setThreadLoading(true);
      setSending(false);
      setError(null);
      setDraft("");
      setPendingInput(null);
      setPhase("idle");
      setAvatarFailed(false);
      try {
        const thread = await fetchCharacterChatThread(threadId);
        if (epoch !== threadEpochRef.current) return null;
        setActiveThread(thread);
        return thread;
      } catch (err) {
        if (epoch !== threadEpochRef.current) return null;
        setActiveThread(null);
        setError(errorMessage(err, t("characterChat.errors.loadFailed")));
        return null;
      } finally {
        if (epoch === threadEpochRef.current) setThreadLoading(false);
      }
    },
    [t],
  );

  const leaveThread = useCallback(() => {
    threadEpochRef.current++;
    activeThreadIdRef.current = null;
    voiceRef.current.stop();
    setActiveThread(null);
    setSending(false);
    setPendingInput(null);
    setDraft("");
    setPhase("idle");
  }, []);

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
      const epoch = threadEpochRef.current;
      voiceRef.current.stop();
      setSending(true);
      setError(null);
      setDraft("");
      setPendingInput(content);
      setPhase("plan");
      let characterMessage: CharacterChatMessage | null = null;
      try {
        const request: CharacterChatMessageRequest = {
          content,
          use_web_search: settingsState.characterChatWebSearchEnabled,
          use_weather: settingsState.characterChatWeatherEnabled,
        };
        await streamCharacterChatMessage(threadId, request, (event) => {
          if (
            activeThreadIdRef.current !== threadId ||
            epoch !== threadEpochRef.current
          )
            return;
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
            if (voiceRef.current.canSpeak) speakMessage(character_message);
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
          } else if (event.type === "appearance_updated") {
            // 3D モデル表示中の着替え: 立ち絵は描かず外見タグだけ変わった
            const { appearance, portrait_url } = event.data;
            setActiveThread((prev) =>
              prev && prev.id === threadId
                ? { ...prev, appearance, portrait_url }
                : prev,
            );
            showNotification(
              "info",
              t("characterChat.thread.appearanceChanged"),
              t("characterChat.room.appearanceTagsOnly"),
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
        if (epoch === threadEpochRef.current)
          setError(errorMessage(err, t("characterChat.errors.sendFailed")));
      } finally {
        if (
          activeThreadIdRef.current === threadId &&
          epoch === threadEpochRef.current
        ) {
          setSending(false);
          setPhase("idle");
          setDraft("");
          setPendingInput(null);
        }
      }
      return characterMessage;
    },
    [
      sending,
      settingsState.characterChatWebSearchEnabled,
      settingsState.characterChatWeatherEnabled,
      addTotalCost,
      showNotification,
      speakMessage,
      t,
    ],
  );

  const setAppearanceFromSource = useCallback(
    async (selection: AdventureSourceSelection) => {
      const threadId = activeThreadIdRef.current;
      if (!threadId || busyPortraitsRef.current[threadId]) return false;
      markPortraitBusy(threadId, "appearance");
      try {
        const { messages: _ignored, ...thread } =
          await setCharacterChatAppearance(
            threadId,
            selectionToRequest(selection),
          );
        applyThreadUpdate(threadId, thread);
        return true;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.appearanceFailed")));
        return false;
      } finally {
        markPortraitBusy(threadId, null);
      }
    },
    [t, markPortraitBusy, applyThreadUpdate],
  );

  const regeneratePortrait = useCallback(
    async (targetThreadId?: string, options?: CharacterChatPortraitOptions) => {
      const threadId = targetThreadId ?? activeThreadIdRef.current;
      if (!threadId || busyPortraitsRef.current[threadId]) return false;
      markPortraitBusy(threadId, "portrait");
      let ok = false;
      let failed: string | null = null;
      try {
        await streamCharacterChatPortrait(
          threadId,
          (event) => {
            if (event.type === "portrait_image") {
              ok = true;
              const { image_url, appearance } = event.data;
              // 別スレッドを見ていても、そのスレッドの表示と一覧のサムネイルを更新する
              applyThreadUpdate(threadId, {
                portrait_url: image_url,
                portrait_missing: false,
                appearance,
                can_reset_appearance: true,
              });
            } else if (event.type === "cost") {
              const cost = Number(event.data.cost_usd);
              if (Number.isFinite(cost) && cost > 0) addTotalCost(cost);
            } else if (
              event.type === "portrait_error" ||
              event.type === "error"
            ) {
              failed = event.data.message;
            }
          },
          options,
        );
      } catch (err) {
        failed = errorMessage(err, t("characterChat.errors.portraitFailed"));
      } finally {
        markPortraitBusy(threadId, null);
      }
      if (!ok) {
        const message = failed ?? t("characterChat.errors.portraitFailed");
        setError(message);
        showNotification(
          "warning",
          t("characterChat.errors.portraitFailed"),
          message,
        );
      }
      return ok;
    },
    [addTotalCost, t, markPortraitBusy, applyThreadUpdate, showNotification],
  );

  const resetAppearance = useCallback(async () => {
    const threadId = activeThreadIdRef.current;
    if (!threadId || busyPortraitsRef.current[threadId]) return false;
    markPortraitBusy(threadId, "appearance");
    try {
      const { messages: _ignored, ...thread } =
        await resetCharacterChatAppearance(threadId);
      applyThreadUpdate(threadId, thread);
      return true;
    } catch (err) {
      setError(errorMessage(err, t("characterChat.errors.appearanceFailed")));
      return false;
    } finally {
      markPortraitBusy(threadId, null);
    }
  }, [t, markPortraitBusy, applyThreadUpdate]);

  const setAdventureAppearance = useCallback(
    async (mode: Exclude<CharacterChatAdventureAppearanceMode, "custom">) => {
      const threadId = activeThreadIdRef.current;
      if (!threadId || busyPortraitsRef.current[threadId]) return false;
      markPortraitBusy(threadId, "appearance");
      try {
        const { messages: _ignored, ...thread } =
          await setCharacterChatAdventureAppearance(threadId, mode);
        applyThreadUpdate(threadId, thread);
        return true;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.appearanceFailed")));
        return false;
      } finally {
        markPortraitBusy(threadId, null);
      }
    },
    [t, markPortraitBusy, applyThreadUpdate],
  );

  const setAvatar = useCallback(
    async (mode: CharacterChatAvatarMode, avatarId?: string | null) => {
      const threadId = activeThreadIdRef.current;
      if (!threadId || busyPortraitsRef.current[threadId]) return false;
      markPortraitBusy(threadId, "appearance");
      try {
        const { messages: _ignored, ...thread } = await setCharacterChatAvatar(
          threadId,
          { mode, avatar_id: avatarId ?? null },
        );
        applyThreadUpdate(threadId, thread);
        // 別のモデルに切り替えたら、前のモデルの読込失敗は引きずらない
        setAvatarFailed(false);
        return true;
      } catch (err) {
        setError(errorMessage(err, t("characterChat.errors.avatarFailed")));
        return false;
      } finally {
        markPortraitBusy(threadId, null);
      }
    },
    [t, markPortraitBusy, applyThreadUpdate],
  );

  const activeBusyKind = activeThread
    ? (busyPortraits[activeThread.id] ?? null)
    : null;
  const portraitBusy = activeBusyKind !== null;

  const value = useMemo<CharacterChatContextValue>(
    () => ({
      voice,
      speakMessage,
      threads,
      threadsLoading,
      activeThread,
      threadLoading,
      sending,
      phase,
      draft,
      pendingInput,
      portraitBusy,
      portraitBusyKind: activeBusyKind,
      error,
      refreshThreads,
      openBase,
      openAdventure,
      createFromSource,
      takePendingPortrait,
      loadThread,
      leaveThread,
      deleteThread,
      submitMessage,
      setAppearanceFromSource,
      regeneratePortrait,
      resetAppearance,
      setAdventureAppearance,
      setAvatar,
      avatarFailed,
      setAvatarFailed,
      promptPreviewEnabled,
      ensureThreadsLoaded,
      clearError,
    }),
    [
      voice,
      speakMessage,
      threads,
      threadsLoading,
      activeThread,
      threadLoading,
      sending,
      phase,
      draft,
      pendingInput,
      portraitBusy,
      activeBusyKind,
      error,
      refreshThreads,
      openBase,
      openAdventure,
      createFromSource,
      takePendingPortrait,
      loadThread,
      leaveThread,
      deleteThread,
      submitMessage,
      setAppearanceFromSource,
      regeneratePortrait,
      resetAppearance,
      setAdventureAppearance,
      setAvatar,
      avatarFailed,
      promptPreviewEnabled,
      ensureThreadsLoaded,
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
