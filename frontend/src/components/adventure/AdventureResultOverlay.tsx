import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { PORTRAIT_ALPHA_OPTIONS } from "../../constants/adventure";
import { useAdventure } from "../../contexts/AdventureContext";
import { useTransparentImage } from "../../hooks/useTransparentImage";

interface AdventureResultOverlayProps {
  /** 閉じた後は run を開き直すまで再表示しない */
  dismissed: boolean;
  onDismiss: () => void;
  /** 「ログを読む」: 閉じてからログドロワーを開く */
  onReadLog: () => void;
  isCompositeMode: boolean;
  isEpilogue: boolean;
  completedMilestones: Set<string>;
}

/** 終了時のリザルトカード。進行中・閉じた後は何も描かない */
export default function AdventureResultOverlay({
  dismissed,
  onDismiss,
  onReadLog,
  isCompositeMode,
  isEpilogue,
  completedMilestones,
}: AdventureResultOverlayProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeRun, streaming, startEpilogue } = useAdventure();
  const { url: transparentResultUrl } = useTransparentImage(
    activeRun?.enable_composite_scene ? null : activeRun?.portrait_image_url,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  if (!activeRun || activeRun.status === "active" || dismissed) return null;
  const resultImageUrl = isCompositeMode
    ? (activeRun.current_image_url ?? activeRun.portrait_image_url)
    : (transparentResultUrl ?? activeRun.current_image_url);

  return (
    <div className={`adventure-result is-${activeRun.status}`}>
      <div
        className="adventure-result__card"
        role="dialog"
        aria-modal="true"
        aria-label={activeRun.ending_title ?? activeRun.title}
      >
        {resultImageUrl && (
          <img
            className="adventure-result__image"
            src={resultImageUrl}
            alt={t("adventure.portraitAlt")}
          />
        )}
        <div className="adventure-result__body">
          <span className="adventure-result__badge">
            {t(`adventure.status.${activeRun.status}`)}
          </span>
          <h2>{activeRun.ending_title ?? activeRun.title}</h2>
          <p className="adventure-result__summary">
            {activeRun.ending_summary}
          </p>
          <dl className="adventure-result__stats">
            <div>
              <dt>{t("adventure.result.turns")}</dt>
              <dd>
                {activeRun.turn_count}
                <i>/{activeRun.max_turns}</i>
              </dd>
            </div>
            <div>
              <dt>{t("adventure.milestones")}</dt>
              <dd>
                {completedMilestones.size}
                <i>/{activeRun.milestones.length}</i>
              </dd>
            </div>
            <div>
              <dt>{t("adventure.clues")}</dt>
              <dd>{activeRun.clues.length}</dd>
            </div>
          </dl>
          {activeRun.milestones.length > 0 && (
            <ul className="adventure-result__milestones">
              {activeRun.milestones.map((milestone) => {
                const done = completedMilestones.has(milestone.id);
                return (
                  <li key={milestone.id} className={done ? "is-done" : ""}>
                    <span aria-hidden>{done ? "✓" : "・"}</span>
                    {milestone.label}
                  </li>
                );
              })}
            </ul>
          )}
          <div className="adventure-result__actions">
            <button type="button" onClick={onReadLog}>
              {t("adventure.result.readLog")}
            </button>
            <button
              type="button"
              onClick={() =>
                navigate("/adventure", {
                  state: { replayRunId: activeRun.id },
                })
              }
            >
              {t("adventure.result.replay")}
            </button>
            <button type="button" onClick={() => navigate("/adventure")}>
              {t("adventure.result.backToHub")}
            </button>
            <button
              type="button"
              disabled={streaming}
              onClick={() => {
                onDismiss();
                if (!isEpilogue) void startEpilogue();
              }}
            >
              {t("adventure.result.continueEpilogue")}
            </button>
          </div>
          <button
            type="button"
            className="adventure-result__close"
            onClick={onDismiss}
          >
            {t("adventure.result.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
