import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { AdventureTalkEntry } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";
import { stripTalkHeader } from "../../utils/adventureDialogue";

interface AdventureTalkThreadProps {
  /** 今の手番に紐づく会話(after_turn === turn_count) */
  entries: AdventureTalkEntry[];
  partnerName: string;
  playerDisplayName: string;
}

/** トークモードの会話スレッド。常に末尾(最新の返答)を見せる */
export default function AdventureTalkThread({
  entries,
  partnerName,
  playerDisplayName,
}: AdventureTalkThreadProps) {
  const { t } = useTranslation();
  const { activeRun, talkDraft, pendingTalkInput } = useAdventure();
  const threadRef = useRef<HTMLDivElement>(null);
  const talkLogLength = activeRun?.talk_log?.length ?? 0;
  // biome-ignore lint/correctness/useExhaustiveDependencies: talk_log の件数と下書きの変化で末尾へスクロールする
  useEffect(() => {
    const node = threadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [talkLogLength, talkDraft, pendingTalkInput]);

  return (
    <div className="adventure-talk-thread" ref={threadRef} aria-live="polite">
      {entries.length === 0 && pendingTalkInput === null && (
        <p className="adventure-talk-thread__empty">
          {t("adventure.talk.emptyHint", { name: partnerName })}
        </p>
      )}
      {entries.map((entry) => (
        <p
          key={entry.id}
          className={`adventure-talk-thread__entry adventure-talk-thread__entry--${entry.role}`}
        >
          <span className="adventure-messagebox__speaker">
            {entry.role === "partner" ? partnerName : playerDisplayName}
          </span>
          <span>
            {entry.role === "partner"
              ? stripTalkHeader(entry.text)
              : entry.text}
          </span>
        </p>
      ))}
      {pendingTalkInput !== null && (
        <>
          <p className="adventure-talk-thread__entry adventure-talk-thread__entry--user">
            <span className="adventure-messagebox__speaker">
              {playerDisplayName}
            </span>
            <span>{pendingTalkInput}</span>
          </p>
          {talkDraft ? (
            <p className="adventure-talk-thread__entry adventure-talk-thread__entry--partner">
              <span className="adventure-messagebox__speaker">
                {partnerName}
              </span>
              <span>
                {talkDraft}
                <span className="adventure-transcript__caret" />
              </span>
            </p>
          ) : (
            <div className="adventure-progress">
              <span />
              {t("adventure.talk.pending", { name: partnerName })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
