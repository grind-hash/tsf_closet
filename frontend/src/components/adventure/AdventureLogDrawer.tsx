import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useAdventure } from "../../contexts/AdventureContext";
import type { AdventureStageFrame } from "../../utils/adventureFrames";

interface AdventureLogDrawerProps {
  open: boolean;
  onClose: () => void;
  frames: AdventureStageFrame[];
  /** ステージで閲覧中のフレーム。null は最新 */
  selectedFrameIndex: number | null;
  onGoToFrame: (index: number) => void;
}

/**
 * ログドロワー(全文の読み返しとターンストリップ)。
 * 閉じている間も ref だけ保持し、開いた時に末尾へスクロールする。
 */
export default function AdventureLogDrawer({
  open,
  onClose,
  frames,
  selectedFrameIndex,
  onGoToFrame,
}: AdventureLogDrawerProps) {
  const { t } = useTranslation();
  const { activeRun } = useAdventure();
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const turnStripEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    transcriptEndRef.current?.scrollIntoView({ block: "end" });
  }, [open]);

  useEffect(() => {
    if (frames.length === 0) return;
    turnStripEndRef.current?.scrollIntoView({
      block: "nearest",
      inline: "end",
    });
  }, [frames.length]);

  if (!open || !activeRun) return null;

  return (
    <div className="adventure-log">
      <button
        type="button"
        className="adventure-log__backdrop"
        aria-label={t("adventure.log.close")}
        onClick={onClose}
      />
      <aside
        className="adventure-log__panel"
        role="dialog"
        aria-modal="true"
        aria-label={t("adventure.log.title")}
      >
        <header className="adventure-log__header">
          <h2>{t("adventure.log.title")}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("adventure.log.close")}
          >
            ×
          </button>
        </header>
        <div className="adventure-log__body">
          <div className="adventure-transcript">
            <article className="adventure-transcript__entry is-opening">
              <span>{t("adventure.openingScene")}</span>
              <p>{activeRun.opening_narrative}</p>
            </article>
            {activeRun.turns.map((turn) => (
              <article className="adventure-transcript__entry" key={turn.id}>
                <div className="adventure-transcript__action">
                  <span>
                    {t("adventure.turn", { number: turn.turn_number })}
                  </span>
                  <p>{turn.user_input}</p>
                </div>
                <p>{turn.narrative}</p>
              </article>
            ))}
          </div>
          <div ref={transcriptEndRef} />
        </div>
        {frames.length > 1 && (
          <div className="adventure-turn-strip">
            {frames.map((frame, index) => {
              const isActive =
                selectedFrameIndex === index ||
                (selectedFrameIndex === null && index === frames.length - 1);
              return (
                <button
                  type="button"
                  key={frame.key}
                  className={`adventure-turn-strip__item${isActive ? " is-active" : ""}`}
                  onClick={() => {
                    onGoToFrame(index);
                    onClose();
                  }}
                  aria-current={isActive ? "true" : undefined}
                  title={
                    frame.turnNumber === 0
                      ? t("adventure.turnStrip.opening")
                      : t("adventure.turnNumber", {
                          number: frame.turnNumber,
                        })
                  }
                >
                  <img
                    src={frame.imageUrl}
                    alt={t("adventure.turnStrip.thumbAlt", {
                      number: frame.turnNumber,
                    })}
                    className="adventure-turn-strip__thumb"
                  />
                  <span className="adventure-turn-strip__badge">
                    {frame.turnNumber === 0
                      ? t("adventure.turnStrip.opening")
                      : frame.turnNumber}
                  </span>
                </button>
              );
            })}
            <div ref={turnStripEndRef} />
          </div>
        )}
      </aside>
    </div>
  );
}
