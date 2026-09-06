import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { CharacterChatMessage } from "../../apis/characterChat";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureSpeechInput } from "../../hooks/useAdventureSpeechInput";
import { useAdventureVoice } from "../../hooks/useAdventureVoice";
import { useCharacterChatPortraitPreference } from "../../hooks/useCharacterChatPortraitPreference";
import { usePersistedState } from "../../hooks/usePersistedState";
import { ROUTES } from "../../routes";
import { stripStageDirections } from "../../utils/adventureDialogue";
import { textToVoiceSegments } from "../../utils/adventureVoiceSegments";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import MainLayout from "../layout/MainLayout";
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

/**
 * 会話画面。Adventure の対面会話モードと同じ ADV 風の構成:
 * 全画面のステージ中央にキャラクターを大きく置き、下端にメッセージ窓と入力欄、
 * 上端に薄いバー(戻る / 名前 / 操作)。過去ログと情報は右のドロワー。
 */
export default function CharacterChatRoom({
  threadId,
}: CharacterChatRoomProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState, loadMemoryText } = useSettings();
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
    deleteThread,
    submitMessage,
    setAppearanceFromSource,
    regeneratePortrait,
    resetAppearance,
    takePendingPortrait,
  } = useCharacterChat();
  const [input, setInput] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [soundOpen, setSoundOpen] = useState(false);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [panelOpen, setPanelOpen] = usePersistedState<boolean>(
    INFO_PANEL_OPEN_KEY,
    true,
  );
  const [generatePortrait, setGeneratePortrait] =
    useCharacterChatPortraitPreference();
  const [logOpen, setLogOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false);
    setLogOpen(false);
    setAppearanceOpen(false);
    void loadThread(threadId).then((thread) => {
      setLoaded(true);
      // Hub で「立ち絵を生成する」を ON にして作った直後は、開いた時点で描く
      if (thread && takePendingPortrait(threadId)) {
        void regeneratePortrait(threadId);
      }
    });
  }, [threadId, loadThread, takePendingPortrait, regeneratePortrait]);

  // 右パネルのユーザーメモリ。設定画面を開いていない起動直後は未取得のことがある
  const memoryText = settingsState.memoryText;
  useEffect(() => {
    if (memoryText === null) void loadMemoryText();
  }, [memoryText, loadMemoryText]);

  // 返答の読み上げ(AivisSpeech)。設定画面の TTS が有効なときだけ動く。既定 OFF
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
      const key = voiceKey(message.id);
      voice.speakSegments(
        textToVoiceSegments(stripStageDirections(message.content), key),
        key,
      );
    },
    [voice],
  );

  const handleSubmit = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || sending) return;
      setInput("");
      const reply = await submitMessage(content);
      if (reply && voice.enabled && voice.canSpeak) speakMessage(reply);
    },
    [
      input,
      sending,
      submitMessage,
      voice.enabled,
      voice.canSpeak,
      speakMessage,
    ],
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

  const handleSelectAppearance = async (
    selection: AdventureSourceSelection,
  ) => {
    setPickerOpen(false);
    const ok = await setAppearanceFromSource(selection);
    // 「立ち絵を生成する」が ON なら、選んだ画像を参照に外見タグから描き直す
    if (ok && generatePortrait) await regeneratePortrait();
  };

  const handleConfirmDelete = async () => {
    setDeleting(true);
    const ok = await deleteThread(threadId);
    setDeleting(false);
    if (ok) navigate(ROUTES.CHARACTER_CHAT);
  };

  const thread = activeThread?.id === threadId ? activeThread : null;
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
          />
        )}

        <header className="character-chat-room__topbar">
          <button
            type="button"
            className="character-chat-room__back"
            onClick={() => navigate(ROUTES.CHARACTER_CHAT)}
          >
            ← {t("characterChat.room.back")}
          </button>
          <h1 className="character-chat-room__title">
            {thread?.name ?? t("characterChat.title")}
            {thread && (
              <span
                className={`character-chat__chip character-chat__chip--${thread.kind}`}
              >
                {t(
                  thread.kind === "base"
                    ? "characterChat.hub.kindBase"
                    : "characterChat.hub.kindSession",
                )}
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
                className={`character-chat-room__action${logOpen ? " is-on" : ""}`}
                aria-pressed={logOpen}
                onClick={() => setLogOpen((prev) => !prev)}
              >
                {t("characterChat.room.log")}
              </button>
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
            <CharacterChatMessageBox
              thread={thread}
              draft={draft}
              pendingInput={pendingInput}
              phase={phase}
              voice={threadVoice}
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
