import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  CharacterChatMessage,
  CharacterChatPhase,
  CharacterChatThread,
} from "../../apis/characterChat";
import type { TranslationKey } from "../../i18n";
import CharacterChatCitations from "./CharacterChatCitations";
import CharacterChatPlayProposalCard from "./CharacterChatPlayProposalCard";
import { toLookupCitations } from "./lookupCitations";
import { toPlayProposal } from "./playProposal";

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
  /** 窓の操作(ログ・隠す)。話者名の行の右端に置く */
  actions?: ReactNode;
  /** 入力欄。メッセージ窓の下端にドッキングする */
  children: ReactNode;
}

/**
 * ADV 風のメッセージ窓。最新の 1 往復(自分の発言 + キャラの返答)だけを出し、
 * 送信中はストリーミング中の返答とスピナー付きの進捗を出す。過去分はログドロワー。
 * 返答の根拠にした調べ物は本文の下に折りたたみの引用として出す。
 */
export default function CharacterChatMessageBox({
  thread,
  draft,
  pendingInput,
  phase,
  voice,
  actions,
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
  const citations = toLookupCitations(latestReply?.meta);
  const proposal = streaming ? null : toPlayProposal(latestReply?.meta);
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
        {(userLine || actions) && (
          <div className="character-chat-room__meta-end">
            {userLine && (
              <span className="character-chat-room__user-line" title={userLine}>
                {t("characterChat.thread.you")}「{userLine}」
              </span>
            )}
            {actions && (
              <div className="character-chat-room__window-actions">
                {actions}
              </div>
            )}
          </div>
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
        {proposal && <CharacterChatPlayProposalCard proposal={proposal} />}
        {!streaming && latestReply && (
          <CharacterChatCitations citations={citations} />
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
