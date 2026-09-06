import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type {
  CharacterChatMessage,
  CharacterChatPhase,
  CharacterChatThread as CharacterChatThreadModel,
} from "../../apis/characterChat";
import type { TranslationKey } from "../../i18n";

export interface CharacterChatThreadVoice {
  canSpeak: boolean;
  activeMessageId: string | null;
  onReplay: (message: CharacterChatMessage) => void;
}

interface CharacterChatThreadProps {
  thread: CharacterChatThreadModel;
  draft: string;
  pendingInput: string | null;
  phase: CharacterChatPhase | "idle";
  voice: CharacterChatThreadVoice;
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

/** 会話スレッド。常に末尾(最新の返答)を見せる */
export default function CharacterChatThread({
  thread,
  draft,
  pendingInput,
  phase,
  voice,
}: CharacterChatThreadProps) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);
  const messages = thread.messages ?? [];
  const messageCount = messages.length;
  // biome-ignore lint/correctness/useExhaustiveDependencies: メッセージ件数と下書きの変化で末尾へスクロールする
  useEffect(() => {
    const node = listRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messageCount, draft, pendingInput, phase]);

  const phaseKey: TranslationKey | null =
    phase === "idle" ? null : `characterChat.thread.phase.${phase}`;
  const showProgress = pendingInput !== null && phaseKey !== null;

  return (
    <div className="character-chat__thread" ref={listRef} aria-live="polite">
      {messages.length === 0 && pendingInput === null && (
        <p className="character-chat__empty">
          {t("characterChat.thread.emptyHint", { name: thread.name })}
        </p>
      )}
      {messages.map((message) => {
        const lookups = (message.meta?.lookups ?? []).filter(isLookupKind);
        const replaying = voice.activeMessageId === message.id;
        return (
          <div
            key={message.id}
            className={`character-chat__message character-chat__message--${message.role}`}
          >
            <span className="character-chat__speaker">
              {message.role === "user"
                ? t("characterChat.thread.you")
                : thread.name}
            </span>
            <div className="character-chat__bubble">
              <p>{message.content}</p>
              {message.role === "character" &&
                (lookups.length > 0 || message.meta?.portrait_filename) && (
                  <div className="character-chat__message-meta">
                    {lookups.length > 0 && (
                      <span>
                        {t("characterChat.thread.lookups", {
                          kinds: lookups
                            .map((kind) =>
                              t(`characterChat.thread.lookupKind.${kind}`),
                            )
                            .join(" / "),
                        })}
                      </span>
                    )}
                    {message.meta?.portrait_filename && (
                      <span className="character-chat__badge">
                        {t("characterChat.thread.appearanceChanged")}
                      </span>
                    )}
                  </div>
                )}
            </div>
            {message.role === "character" && voice.canSpeak && (
              <button
                type="button"
                className={`character-chat__replay${replaying ? " is-active" : ""}`}
                aria-pressed={replaying}
                aria-label={t("characterChat.room.voiceReplay")}
                title={t("characterChat.room.voiceReplayHint")}
                onClick={() => voice.onReplay(message)}
              >
                🔊
              </button>
            )}
          </div>
        );
      })}
      {pendingInput !== null && (
        <>
          <div className="character-chat__message character-chat__message--user">
            <span className="character-chat__speaker">
              {t("characterChat.thread.you")}
            </span>
            <div className="character-chat__bubble">
              <p>{pendingInput}</p>
            </div>
          </div>
          {draft ? (
            <div className="character-chat__message character-chat__message--character">
              <span className="character-chat__speaker">{thread.name}</span>
              <div className="character-chat__bubble">
                <p>
                  {draft}
                  <span className="character-chat__caret" />
                </p>
              </div>
            </div>
          ) : (
            showProgress &&
            phaseKey && (
              <div className="character-chat__progress" role="status">
                <span />
                {t(phaseKey)}
              </div>
            )
          )}
          {draft && phase !== "reply" && phaseKey && (
            <div className="character-chat__progress" role="status">
              <span />
              {t(phaseKey)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
