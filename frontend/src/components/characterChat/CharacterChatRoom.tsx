import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { CharacterChatMessage } from "../../apis/characterChat";
import {
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "../../constants/companionAvatar";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { useNotification } from "../../contexts/NotificationContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureSpeechInput } from "../../hooks/useAdventureSpeechInput";
import { useCharacterChatPortraitPreference } from "../../hooks/useCharacterChatPortraitPreference";
import { usePersistedState } from "../../hooks/usePersistedState";
import { ROUTES } from "../../routes";
import { readStorageFlag, writeStorageFlag } from "../../utils/storage";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import MainLayout from "../layout/MainLayout";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import ConfirmDialog from "../ui/ConfirmDialog";
import CharacterChatAppearanceMenu from "./CharacterChatAppearanceMenu";
import CharacterChatInfoPanel from "./CharacterChatInfoPanel";
import CharacterChatInput from "./CharacterChatInput";
import CharacterChatLogDrawer from "./CharacterChatLogDrawer";
import CharacterChatMessageBox from "./CharacterChatMessageBox";
import CharacterChatSoundControl from "./CharacterChatSoundControl";
import CharacterChatStage from "./CharacterChatStage";

interface CharacterChatRoomProps {
  threadId: string;
}

const voiceKey = (messageId: string) => `chat:${messageId}`;
const INFO_PANEL_OPEN_KEY = "character_chat_info_panel_open";
/** 精密参照の Anlas 確認を「ブラウザを閉じるまで出さない」印(sessionStorage) */
const ANLAS_WARN_SUPPRESSED_KEY = "character_chat_anlas_warn_suppressed";

const KIND_LABEL_KEY = {
  base: "characterChat.hub.kindBase",
  session: "characterChat.hub.kindSession",
  adventure: "characterChat.hub.kindAdventure",
} as const;

/**
 * 会話画面。Adventure の対面会話モードと同じ ADV 風の構成:
 * 全画面のステージ中央にキャラクターを大きく置き、下端にメッセージ窓と入力欄、
 * 上端に薄いバー(戻る / 名前 / 操作)。過去ログは右のドロワー、記憶と情報は右パネル。
 * adventure 種は run に 3D モデル(VRM)があれば立ち絵の代わりに表示する。
 */
export default function CharacterChatRoom({
  threadId,
}: CharacterChatRoomProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState, loadMemoryText } = useSettings();
  const { showNotification } = useNotification();
  const {
    activeThread,
    threadLoading,
    sending,
    phase,
    draft,
    pendingInput,
    portraitBusy,
    portraitBusyKind,
    error,
    clearError,
    loadThread,
    leaveThread,
    deleteThread,
    submitMessage,
    setAppearanceFromSource,
    regeneratePortrait,
    resetAppearance,
    setAdventureAppearance,
    setAvatar,
    takePendingPortrait,
    avatarFailed,
    setAvatarFailed,
    ensureThreadsLoaded,
    voice,
    speakMessage,
  } = useCharacterChat();
  const [input, setInput] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [soundOpen, setSoundOpen] = useState(false);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [messageWindowHidden, setMessageWindowHidden] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [panelOpen, setPanelOpen] = usePersistedState<boolean>(
    INFO_PANEL_OPEN_KEY,
    true,
  );
  const [generatePortrait, setGeneratePortrait] =
    useCharacterChatPortraitPreference();
  // adventure 種: 場面画像から描くときに精密参照(Anlas)を使うか。初期値は run の設定
  const [usePrecise, setUsePrecise] = useState<boolean | null>(null);
  const [pendingRedraw, setPendingRedraw] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setLogOpen(false);
    setMessageWindowHidden(false);
    setAppearanceOpen(false);
    setUsePrecise(null);
    // ハブを通らずここへ直接来たときも、一覧由来の設定(開発者向け案内の出し分け)を取る
    ensureThreadsLoaded();
    void loadThread(threadId).then((thread) => {
      setLoaded(true);
      // Hub で「立ち絵を生成する」を ON にして作った直後は、開いた時点で描く
      if (thread && takePendingPortrait(threadId)) {
        void regeneratePortrait(threadId);
      }
    });
    return leaveThread;
  }, [
    threadId,
    loadThread,
    leaveThread,
    takePendingPortrait,
    regeneratePortrait,
    ensureThreadsLoaded,
  ]);

  // 窓の ✕ と「ウィンドウを表示」は押すと消えるため、押した後は対になるボタンへフォーカスを移す
  const hideWindowRef = useRef<HTMLButtonElement>(null);
  const showWindowRef = useRef<HTMLButtonElement>(null);
  const windowToggledRef = useRef(false);
  useEffect(() => {
    if (!windowToggledRef.current) return;
    windowToggledRef.current = false;
    (messageWindowHidden ? showWindowRef : hideWindowRef).current?.focus();
  }, [messageWindowHidden]);
  const toggleMessageWindow = () => {
    windowToggledRef.current = true;
    setMessageWindowHidden((hidden) => !hidden);
  };

  // 右パネルのユーザーメモリ。設定画面を開いていない起動直後は未取得のことがある
  const memoryText = settingsState.memoryText;
  useEffect(() => {
    if (memoryText === null) void loadMemoryText();
  }, [memoryText, loadMemoryText]);

  const handleSubmit = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || sending) return;
      setInput("");
      await submitMessage(content);
    },
    [input, sending, submitMessage],
  );

  const speechInput = useAdventureSpeechInput({
    language: i18n.language ?? "",
    input,
    setInput,
    onSubmit: (value) => void handleSubmit(value),
    active: true,
    voiceStatus: voice.status,
    stopVoice: voice.stop,
  });

  const activeVoiceMessageId =
    voice.status !== "idle" && voice.currentKey?.startsWith("chat:")
      ? voice.currentKey.slice("chat:".length)
      : null;
  const handleReplay = (message: CharacterChatMessage) => {
    if (activeVoiceMessageId === message.id) {
      voice.stop();
      return;
    }
    speakMessage(message);
  };
  const threadVoice = {
    canSpeak: voice.canSpeak,
    activeMessageId: activeVoiceMessageId,
    onReplay: handleReplay,
  };

  const thread = activeThread?.id === threadId ? activeThread : null;
  const adventure =
    thread?.kind === "adventure" ? (thread.adventure ?? null) : null;
  const preciseAvailable = settingsState.imageProvider === "novelai";
  const preciseEffective =
    preciseAvailable &&
    (usePrecise ?? adventure?.use_precise_reference ?? false);

  // 3D モデル(VRM)。バックエンドが解決したモデル(明示 → 同梱 → run → 名前一致)があり、
  // 読込に失敗していなければ立ち絵の代わりに置く
  const avatarUrl = thread?.avatar?.url ?? null;
  const latestCharacterMessage =
    [...(thread?.messages ?? [])]
      .reverse()
      .find((message) => message.role === "character") ?? null;
  const voiceBusy = voice.status === "loading" || voice.status === "playing";
  const avatarGestureKey =
    voice.enabled && voice.canSpeak
      ? voiceBusy
        ? voice.currentKey
        : null
      : latestCharacterMessage
        ? voiceKey(latestCharacterMessage.id)
        : null;
  const handleAvatarError = useCallback(
    (caught: unknown) => {
      console.warn("character chat avatar load failed", caught);
      setAvatarFailed(true);
      showNotification(
        "warning",
        t("adventure.avatar.loadFailedTitle"),
        t("adventure.avatar.loadFailed"),
      );
    },
    [setAvatarFailed, showNotification, t],
  );
  // 明示的に選んでいたモデルが削除されていたら、自動へ倒したことを知らせる
  const avatarMissing = Boolean(thread?.avatar?.missing);
  useEffect(() => {
    if (!avatarMissing) return;
    showNotification("warning", t("characterChat.room.avatarMissing"));
  }, [avatarMissing, showNotification, t]);
  const stageAvatar =
    avatarUrl && thread?.avatar?.mode !== "live2d" && !avatarFailed
      ? {
          url: avatarUrl,
          // 案内役キャラ(セレナ)だけ、手を体の前で重ねた待機姿勢にする
          restPose:
            thread?.kind === "base"
              ? ("clasped" as const)
              : ("relaxed" as const),
          expression: normalizeAvatarExpression(
            latestCharacterMessage?.meta?.expression ?? null,
          ),
          gesture: normalizeAvatarGesture(
            latestCharacterMessage?.meta?.gesture ?? null,
          ),
          gestureKey: avatarGestureKey,
          getVoiceLevel: voice.getLevel,
          getVisemeFrame: voice.getMouthFrame,
          onError: handleAvatarError,
        }
      : null;

  const handleSelectAppearance = async (
    selection: AdventureSourceSelection,
  ) => {
    setPickerOpen(false);
    const ok = await setAppearanceFromSource(selection);
    // 「立ち絵を生成する」が ON なら、選んだ画像を参照に外見タグから描き直す
    if (ok && generatePortrait) await regeneratePortrait();
  };

  const runRedrawFromScene = useCallback(
    (precise: boolean) =>
      void regeneratePortrait(threadId, {
        reference: "scene",
        use_precise_reference: precise,
      }),
    [regeneratePortrait, threadId],
  );
  const handleRedrawFromScene = () => {
    setAppearanceOpen(false);
    if (
      preciseEffective &&
      !readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)
    ) {
      // 精密参照は Anlas を消費するため、抑止チェック付きの確認を挟む
      setPendingRedraw(true);
      return;
    }
    runRedrawFromScene(preciseEffective);
  };

  const handleConfirmDelete = async () => {
    setDeleting(true);
    const ok = await deleteThread(threadId);
    setDeleting(false);
    if (ok) navigate(ROUTES.CHARACTER_CHAT);
  };

  // 一覧へは常に戻れる。シナリオ由来で run が生きていれば、シナリオへ戻る導線も並べる
  // (Adventure の「トーク」からも、一覧からも来るため、どちらにも戻れるようにする)
  const scenarioRunId =
    thread?.kind === "adventure" && adventure?.available
      ? (thread.source_run_id ?? null)
      : null;
  const handleBack = () => navigate(ROUTES.CHARACTER_CHAT);
  const handleBackToScenario = () => {
    if (scenarioRunId) navigate(`${ROUTES.ADVENTURE}/${scenarioRunId}`);
  };

  const deleteIcon = (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        fill="currentColor"
        d="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9zm4 2v8h2v-8h-2zm4 0v8h2v-8h-2z"
      />
    </svg>
  );

  return (
    <MainLayout
      rightPanel={
        thread ? (
          <CharacterChatInfoPanel thread={thread} memoryText={memoryText} />
        ) : undefined
      }
      showRightPanel={panelOpen}
      onToggleRightPanel={() => setPanelOpen((prev) => !prev)}
    >
      <div className="character-chat-room">
        {thread && (
          <CharacterChatStage
            thread={thread}
            busy={portraitBusy}
            drawing={
              (sending && phase === "portrait") ||
              portraitBusyKind === "portrait"
            }
            onGenerate={() => void regeneratePortrait()}
            avatar={stageAvatar}
          />
        )}

        <header className="character-chat-room__topbar">
          <button
            type="button"
            className="character-chat-room__back"
            onClick={handleBack}
          >
            ← {t("characterChat.room.back")}
          </button>
          {scenarioRunId && (
            <button
              type="button"
              className="character-chat-room__back"
              onClick={handleBackToScenario}
            >
              {t("characterChat.room.backToScenario")}
            </button>
          )}
          <h1 className="character-chat-room__title">
            {thread?.name ?? t("characterChat.title")}
            {thread && (
              <span
                className={`character-chat__chip character-chat__chip--${thread.kind}`}
              >
                {t(KIND_LABEL_KEY[thread.kind])}
              </span>
            )}
          </h1>
          {thread && (
            <div className="character-chat-room__actions">
              <CharacterChatAppearanceMenu
                open={appearanceOpen}
                onToggleOpen={() => setAppearanceOpen((prev) => !prev)}
                busy={portraitBusy || sending}
                canReset={Boolean(thread.can_reset_appearance)}
                generatePortrait={generatePortrait}
                onGeneratePortraitChange={setGeneratePortrait}
                onChangeAppearance={() => {
                  setAppearanceOpen(false);
                  setPickerOpen(true);
                }}
                onRegenerate={() => {
                  setAppearanceOpen(false);
                  void regeneratePortrait();
                }}
                onReset={() => {
                  setAppearanceOpen(false);
                  void resetAppearance();
                }}
                adventure={adventure}
                onAdventureMode={(mode) => {
                  setAppearanceOpen(false);
                  void setAdventureAppearance(mode);
                }}
                avatar={thread.avatar ?? null}
                onAvatarChange={(mode, avatarId) => {
                  setAppearanceOpen(false);
                  void setAvatar(mode, avatarId);
                }}
                onRedrawFromScene={handleRedrawFromScene}
                preciseAvailable={preciseAvailable && Boolean(adventure)}
                usePrecise={preciseEffective}
                onUsePreciseChange={setUsePrecise}
              />
              <CharacterChatSoundControl
                open={soundOpen}
                onToggleOpen={() => setSoundOpen((prev) => !prev)}
                voice={{
                  available: settingsState.ttsEnabled,
                  enabled: voice.enabled,
                  volume: voice.volume,
                  speed: voice.speed,
                  status: voice.status,
                  onEnabledChange: voice.setEnabled,
                  onVolumeChange: voice.setVolume,
                  onSpeedChange: voice.setSpeed,
                  onStop: voice.stop,
                }}
              />
              <button
                type="button"
                className="character-chat__delete"
                aria-label={t("characterChat.hub.delete")}
                title={t("characterChat.hub.delete")}
                onClick={() => setDeleteOpen(true)}
              >
                {deleteIcon}
              </button>
            </div>
          )}
        </header>

        {error && (
          <div
            className="character-chat__error character-chat-room__error"
            role="alert"
          >
            <span>{error}</span>
            <button type="button" onClick={clearError}>
              ✕
            </button>
          </div>
        )}

        {!thread && loaded && !threadLoading && (
          <p className="character-chat-room__notice">
            {t("characterChat.room.notFound")}
          </p>
        )}
        {!thread && (threadLoading || !loaded) && (
          <div className="character-chat-room__notice">
            <span className="character-chat__progress" role="status">
              <span />
              {t("characterChat.hub.loading")}
            </span>
          </div>
        )}

        {thread && (
          <>
            {messageWindowHidden && (
              <div className="character-chat-room__window-restore">
                <button
                  ref={showWindowRef}
                  type="button"
                  aria-controls="character-chat-message-window"
                  onClick={toggleMessageWindow}
                >
                  {t("characterChat.room.showWindow")}
                </button>
              </div>
            )}
            <div
              id="character-chat-message-window"
              hidden={messageWindowHidden}
            >
              <CharacterChatMessageBox
                thread={thread}
                draft={draft}
                pendingInput={pendingInput}
                phase={phase}
                voice={threadVoice}
                actions={
                  <>
                    <button
                      type="button"
                      className={`character-chat-room__window-button${logOpen ? " is-on" : ""}`}
                      aria-pressed={logOpen}
                      onClick={() => setLogOpen((prev) => !prev)}
                    >
                      {t("characterChat.room.log")}
                    </button>
                    <button
                      ref={hideWindowRef}
                      type="button"
                      className="character-chat-room__window-button character-chat-room__window-hide"
                      aria-controls="character-chat-message-window"
                      aria-label={t("characterChat.room.hideWindow")}
                      title={t("characterChat.room.hideWindow")}
                      onClick={toggleMessageWindow}
                    >
                      ✕
                    </button>
                  </>
                }
              >
                <CharacterChatInput
                  value={input}
                  onChange={setInput}
                  onSubmit={() => void handleSubmit()}
                  name={thread.name}
                  busy={sending}
                  speech={{
                    supported: speechInput.supported,
                    listening: speechInput.listening,
                    autoSend: speechInput.prefs.autoSend,
                    error: speechInput.error,
                    onToggleListening: speechInput.listening
                      ? speechInput.stopListening
                      : speechInput.startListening,
                    onToggleAutoSend: speechInput.toggleAutoSend,
                  }}
                />
              </CharacterChatMessageBox>
            </div>
            <CharacterChatLogDrawer
              open={logOpen}
              thread={thread}
              draft={draft}
              pendingInput={pendingInput}
              phase={phase}
              voice={threadVoice}
              onClose={() => setLogOpen(false)}
            />
          </>
        )}
      </div>

      {pickerOpen && (
        <AdventureSessionPickerModal
          title={t("characterChat.room.appearancePickerTitle")}
          selected={null}
          onSelect={handleSelectAppearance}
          onClose={() => setPickerOpen(false)}
          allowPromptExpander={settingsState.experimentalPromptExpanderEnabled}
        />
      )}

      <AnlasConfirmDialog
        open={pendingRedraw}
        body={t("characterChat.room.adventureAnlasBody")}
        checkboxId="character-chat-anlas-suppress"
        onConfirm={(suppress) => {
          if (suppress)
            writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
          setPendingRedraw(false);
          runRedrawFromScene(true);
        }}
        onCancel={() => setPendingRedraw(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title={t("characterChat.hub.deleteTitle")}
        confirmLabel={t("characterChat.hub.deleteConfirm")}
        cancelLabel={t("characterChat.hub.cancel")}
        busy={deleting}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setDeleteOpen(false)}
      >
        {t("characterChat.hub.deleteBody", { name: thread?.name ?? "" })}
      </ConfirmDialog>
    </MainLayout>
  );
}
