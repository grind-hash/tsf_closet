import { useTranslation } from "react-i18next";
import type {
  CharacterChatPhase,
  CharacterChatThread as CharacterChatThreadModel,
} from "../../apis/characterChat";
import CharacterChatThread, {
  type CharacterChatThreadVoice,
} from "./CharacterChatThread";

interface CharacterChatLogDrawerProps {
  open: boolean;
  thread: CharacterChatThreadModel;
  draft: string;
  pendingInput: string | null;
  phase: CharacterChatPhase | "idle";
  voice: CharacterChatThreadVoice;
  onClose: () => void;
}

/** 会話ログのドロワー。全文の読み返し(🔊 再読み上げ付き)をステージの右側に重ねて出す */
export default function CharacterChatLogDrawer({
  open,
  thread,
  draft,
  pendingInput,
  phase,
  voice,
  onClose,
}: CharacterChatLogDrawerProps) {
  const { t } = useTranslation();
  if (!open) return null;
  return (
    <aside
      className="character-chat-room__log"
      role="dialog"
      aria-label={t("characterChat.room.logTitle")}
    >
      <header className="character-chat-room__log-header">
        <h2>{t("characterChat.room.logTitle")}</h2>
        <button
          type="button"
          className="character-chat__icon-button"
          onClick={onClose}
          aria-label={t("characterChat.room.close")}
          title={t("characterChat.room.close")}
        >
          ✕
        </button>
      </header>
      <CharacterChatThread
        thread={thread}
        draft={draft}
        pendingInput={pendingInput}
        phase={phase}
        voice={voice}
      />
    </aside>
  );
}
