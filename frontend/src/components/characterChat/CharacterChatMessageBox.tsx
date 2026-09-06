import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  CharacterChatMessage,
  CharacterChatPhase,
  CharacterChatThread,
} from "../../apis/characterChat";
import type { TranslationKey } from "../../i18n";

export interface CharacterChatMessageBoxVoice {
  canSpeak: boolean;
  activeMessageId: string | null;
  onReplay: (message: CharacterChatMessage) => void;
}

interface CharacterChatMessageBoxProps {
  thread: CharacterChatThread;
  draft: string;
  pendingInput: string | null;
  phase: CharacterChatPhase | "idle";
  voice: CharacterChatMessageBoxVoice;
  /** 入力欄。メッセージ窓の下端にドッキングする */
  children: ReactNode;
}

const LOOKUP_KINDS = [
  "recent_sessions",
  "session_detail",
  "search_sessions",
  "tendencies",
  "recent_adventures",
] as const;
type LookupKind = (typeof LOOKUP_KINDS)[number];

function isLookupKind(value: string): value is LookupKind {
  return (LOOKUP_KINDS as readonly string[]).includes(value);
}

/**
 * ADV 風のメッセージ窓。最新の 1 往復(自分の発言 + キャラの返答)だけを出し、
 * 送信中はストリーミング中の返答とスピナー付きの進捗を出す。過去分はログドロワー。
 */
export default function CharacterChatMessageBox({
  thread,
  draft,
  pendingInput,
  phase,
  voice,
  children,
}: CharacterChatMessageBoxProps) {
  const { t } = useTranslation();
  const messages = thread.messages ?? [];
  const latestReplyIndex = messages.map((m) => m.role).lastIndexOf("character");
  const latestReply = latestReplyIndex >= 0 ? messages[latestReplyIndex] : null;
  const latestUser =
    latestReplyIndex > 0 && messages[latestReplyIndex - 1]?.role === "user"
      ? messages[latestReplyIndex - 1]
      : null;
  const streaming = pendingInput !== null;
  const userLine = streaming ? pendingInput : (latestUser?.content ?? null);
  const bodyText = streaming ? draft : (latestReply?.content ?? "");
  const lookups = (latestReply?.meta?.lookups ?? []).filter(isLookupKind);
  const phaseKey: TranslationKey | null =
    phase === "idle" ? null : `characterChat.thread.phase.${phase}`;
  const showProgress =
    streaming && phaseKey !== null && (phase !== "reply" || !draft);
  const replaying =
    latestReply !== null && voice.activeMessageId === latestReply.id;

  return (
    <div className="character-chat-room__messagebox">
      <div className="character-chat-room__meta">
        <span className="character-chat-room__speaker">{thread.name}</span>
        {!streaming && latestReply && lookups.length > 0 && (
          <span className="character-chat-room__meta-note">
            {t("characterChat.thread.lookups", {
              kinds: lookups
                .map((kind) => t(`characterChat.thread.lookupKind.${kind}`))
                .join(" / "),
            })}
          </span>
        )}
        {!streaming && latestReply?.meta?.portrait_filename && (
          <span className="character-chat__badge">
            {t("characterChat.thread.appearanceChanged")}
          </span>
        )}
        {!streaming && latestReply && voice.canSpeak && (
          <button
            type="button"
            className={`character-chat__replay${replaying ? " is-active" : ""}`}
            aria-pressed={replaying}
            aria-label={t("characterChat.room.voiceReplay")}
            title={t("characterChat.room.voiceReplayHint")}
            onClick={() => voice.onReplay(latestReply)}
          >
            🔊
          </button>
        )}
        {userLine && (
          <span className="character-chat-room__user-line" title={userLine}>
            {t("characterChat.thread.you")}「{userLine}」
          </span>
        )}
      </div>
      <div className="character-chat-room__text" aria-live="polite">
        {bodyText ? (
          <p>
            {bodyText}
            {streaming && <span className="character-chat__caret" />}
          </p>
        ) : (
          !streaming && (
            <p className="character-chat-room__hint">
              {t("characterChat.thread.emptyHint", { name: thread.name })}
            </p>
          )
        )}
        {showProgress && phaseKey && (
          <div className="character-chat__progress" role="status">
            <span />
            {t(phaseKey)}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}
