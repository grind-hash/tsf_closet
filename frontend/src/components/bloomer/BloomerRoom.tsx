import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getBloomerImageUrl } from "../../apis/bloomer";
import { useBloomer } from "../../contexts/BloomerContext";
import MainLayout from "../layout/MainLayout";
import MilestoneModal from "./MilestoneModal";
import StatRadarChart from "./StatRadarChart";
import WardrobePanel from "./WardrobePanel";
import "./BloomerScreen.css";

const AXIS_KEYS = [
  "allure",
  "technique",
  "depravity",
  "sensitivity",
  "endurance",
  "composure",
] as const;

function GaugeBar({
  value,
  label,
  color,
  delta,
}: {
  value: number;
  label: string;
  color: string;
  delta?: number;
}) {
  return (
    <div className="bloomer-gauge">
      <span className="bloomer-gauge__label">{label}</span>
      <div className="bloomer-gauge__track">
        <div
          className="bloomer-gauge__fill"
          style={{ width: `${value}%`, backgroundColor: color }}
        />
      </div>
      <span className="bloomer-gauge__value">
        {value}
        {delta != null && delta !== 0 && (
          <span
            className={`bloomer-gauge__delta ${delta > 0 ? "bloomer-gauge__delta--up" : "bloomer-gauge__delta--down"}`}
          >
            {delta > 0 ? `+${delta}` : delta}
          </span>
        )}
      </span>
    </div>
  );
}

export default function BloomerRoom() {
  const { t } = useTranslation();
  const {
    activeRun,
    catalog,
    actionLoading,
    imageGenerating,
    error,
    lastAdvance,
    lastActionResult,
    backToHub,
    doAction,
    doAdvanceDay,
    doEquipOutfit,
    generateImage,
    clearError,
  } = useBloomer();

  const [showWardrobe, setShowWardrobe] = useState(false);
  const [showMilestone, setShowMilestone] = useState(false);
  const [pendingAdvance, setPendingAdvance] = useState(false);
  const [talkText, setTalkText] = useState("");
  const [talkOpen, setTalkOpen] = useState(false);
  const talkInputRef = useRef<HTMLTextAreaElement>(null);

  const statDelta = useMemo(() => {
    const before = lastActionResult?.stat_before;
    const after = lastActionResult?.stat_after;
    if (!before || !after) return null;
    return {
      mood: after.mood - before.mood,
      stamina: after.stamina - before.stamina,
      trust: after.trust - before.trust,
    };
  }, [lastActionResult]);

  const displayAxes = useMemo(() => {
    const next = {} as Record<(typeof AXIS_KEYS)[number], number>;
    if (!activeRun) {
      for (const key of AXIS_KEYS) next[key] = 0;
      return next;
    }
    for (const key of AXIS_KEYS) {
      next[key] = Math.min(
        100,
        (activeRun.axes[key] ?? 0) + (activeRun.growth[key] ?? 0),
      );
    }
    return next;
  }, [activeRun]);

  const axisLabels = useMemo(
    () =>
      Object.fromEntries(
        AXIS_KEYS.map((key) => [key, t(`bloomer.axes.${key}`)]),
      ) as Record<(typeof AXIS_KEYS)[number], string>,
    [t],
  );

  if (!activeRun) return null;

  const isEnded = activeRun.status === "ended";
  const noActions = activeRun.actions_left <= 0;
  const imageUrl = activeRun.current_image_path
    ? getBloomerImageUrl(activeRun.current_image_path)
    : null;

  const handleAdvanceDay = async () => {
    setPendingAdvance(true);
    try {
      const result = await doAdvanceDay();
      if (result.milestone_pending) {
        setShowMilestone(true);
      }
    } finally {
      setPendingAdvance(false);
    }
  };

  const handleTalkSubmit = async () => {
    if (!talkText.trim()) return;
    await doAction("talk", talkText.trim());
    setTalkText("");
    setTalkOpen(false);
  };

  const handleActionClick = (key: string) => {
    if (key === "talk") {
      setTalkOpen(true);
      setTimeout(() => talkInputRef.current?.focus(), 50);
      return;
    }
    doAction(key);
  };

  const availableActions = catalog
    ? Object.entries(catalog.actions).filter(([, def]) => {
        if (activeRun.mood < def.req_mood) return false;
        if (activeRun.trust < def.req_trust) return false;
        if (activeRun.nsfw_stage < def.req_nsfw_stage) return false;
        return true;
      })
    : [];

  return (
    <MainLayout>
      <div className="bloomer-room">
        {error && (
          <div className="bloomer-room__error" role="alert">
            {error}
            <button type="button" onClick={clearError}>
              ×
            </button>
          </div>
        )}

        {/* ヘッダー */}
        <div className="bloomer-room__header">
          <button
            type="button"
            className="bloomer-room__back-btn"
            onClick={backToHub}
            aria-label={t("bloomer.room.back")}
          >
            ←
          </button>
          <h2 className="bloomer-room__name">{activeRun.name}</h2>
          <span className="bloomer-room__day">
            {t("bloomer.room.dayLabel", {
              day: activeRun.day,
              max: activeRun.max_days,
            })}
          </span>
          <span className="bloomer-room__stage">
            {t("bloomer.room.stageLabel", { stage: activeRun.stage })}
          </span>
          <span className="bloomer-room__actions-left">
            {t("bloomer.room.actionsLeft", { n: activeRun.actions_left })}
          </span>
        </div>

        {/* ポートレート + ナレーション */}
        <div className="bloomer-room__top">
          <div className="bloomer-room__portrait-area">
            {imageUrl ? (
              <img
                src={imageUrl}
                alt={activeRun.name}
                className="bloomer-room__portrait"
              />
            ) : (
              <div className="bloomer-room__portrait-placeholder">
                {activeRun.name}
              </div>
            )}
            <button
              type="button"
              className="bloomer-room__regen-btn"
              onClick={generateImage}
              disabled={imageGenerating || isEnded}
            >
              {imageGenerating
                ? t("bloomer.room.generating")
                : t("bloomer.room.regenImage")}
            </button>
          </div>

          {/* ナレーションエリア */}
          <div className="bloomer-room__narration-area">
            {lastActionResult?.narration ? (
              <div
                className={`bloomer-room__narration ${lastActionResult.refused ? "bloomer-room__narration--refused" : ""}`}
              >
                <p>{lastActionResult.narration}</p>
              </div>
            ) : (
              <div className="bloomer-room__narration bloomer-room__narration--idle">
                <p>{t("bloomer.room.waitingNarration")}</p>
              </div>
            )}

            {/* 夜の総括・ステージアップ */}
            {lastAdvance?.nightly_narration && (
              <div className="bloomer-room__nightly">
                <p>{lastAdvance.nightly_narration}</p>
              </div>
            )}
            {lastAdvance?.stage_narration && (
              <div className="bloomer-room__stage-up">
                <strong>
                  {t("bloomer.room.stageUp", { stage: lastAdvance.stage_up })}
                </strong>
                <p>{lastAdvance.stage_narration}</p>
              </div>
            )}
          </div>
        </div>

        {/* ゲージ */}
        <div className="bloomer-room__gauges">
          <GaugeBar
            value={activeRun.mood}
            label={t("bloomer.room.mood")}
            color="#e8906a"
            delta={statDelta?.mood}
          />
          <GaugeBar
            value={activeRun.stamina}
            label={t("bloomer.room.stamina")}
            color="#6abbe8"
            delta={statDelta?.stamina}
          />
          <GaugeBar
            value={activeRun.trust}
            label={t("bloomer.room.trust")}
            color="#8ade8a"
            delta={statDelta?.trust}
          />
        </div>

        {/* 6軸レーダー + 数値 */}
        <div className="bloomer-room__axes-panel">
          <StatRadarChart
            series={[
              {
                axes: displayAxes,
                color: "rgba(232, 144, 106, 0.45)",
                label: activeRun.name,
              },
            ]}
            size={200}
            axisLabels={axisLabels}
          />
          <div className="bloomer-room__axes">
            {AXIS_KEYS.map((k) => (
              <div key={k} className="bloomer-room__axis">
                <span className="bloomer-room__axis-label">
                  {t(`bloomer.axes.${k}`)}
                </span>
                <span className="bloomer-room__axis-value">
                  {displayAxes[k]}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* エンディング */}
        {isEnded && (
          <div className="bloomer-room__ending">
            <h3>{t("bloomer.room.ended")}</h3>
            {lastAdvance?.ending_narration && (
              <p className="bloomer-room__ending-narration">
                {lastAdvance.ending_narration}
              </p>
            )}
            <p className="bloomer-room__ending-key">{activeRun.ending_key}</p>
          </div>
        )}

        {/* アクション */}
        {!isEnded && (
          <div className="bloomer-room__actions-panel">
            {/* 会話テキスト入力 */}
            {talkOpen && (
              <div className="bloomer-room__talk-input">
                <textarea
                  ref={talkInputRef}
                  className="bloomer-room__talk-textarea"
                  value={talkText}
                  onChange={(e) => setTalkText(e.target.value)}
                  placeholder={t("bloomer.room.talkPlaceholder")}
                  rows={2}
                  maxLength={200}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleTalkSubmit();
                    }
                    if (e.key === "Escape") {
                      setTalkOpen(false);
                      setTalkText("");
                    }
                  }}
                />
                <div className="bloomer-room__talk-controls">
                  <button
                    type="button"
                    className="bloomer-room__talk-cancel"
                    onClick={() => {
                      setTalkOpen(false);
                      setTalkText("");
                    }}
                  >
                    {t("bloomer.room.cancel")}
                  </button>
                  <button
                    type="button"
                    className="bloomer-room__talk-send"
                    onClick={handleTalkSubmit}
                    disabled={!talkText.trim() || actionLoading}
                  >
                    {actionLoading
                      ? t("bloomer.room.sending")
                      : t("bloomer.room.send")}
                  </button>
                </div>
              </div>
            )}

            {!talkOpen && (
              <div className="bloomer-room__action-buttons">
                {availableActions.map(([key, def]) => (
                  <button
                    key={key}
                    type="button"
                    className={`bloomer-room__action-btn bloomer-room__action-btn--${def.kind}`}
                    onClick={() => handleActionClick(key)}
                    disabled={actionLoading || noActions}
                  >
                    {t(`bloomer.actions.${key}`, { defaultValue: key })}
                  </button>
                ))}
              </div>
            )}

            <div className="bloomer-room__day-controls">
              <button
                type="button"
                className="bloomer-room__wardrobe-btn"
                onClick={() => setShowWardrobe(true)}
                disabled={actionLoading}
              >
                {t("bloomer.room.wardrobe")}
              </button>
              {noActions && (
                <button
                  type="button"
                  className="bloomer-room__advance-btn"
                  onClick={handleAdvanceDay}
                  disabled={actionLoading || pendingAdvance}
                >
                  {pendingAdvance
                    ? t("bloomer.room.advancing")
                    : t("bloomer.room.advanceDay")}
                </button>
              )}
            </div>
          </div>
        )}

        {/* 衣装パネル */}
        {showWardrobe && (
          <WardrobePanel
            run={activeRun}
            catalog={catalog}
            onEquip={(key) => {
              doEquipOutfit(key);
              setShowWardrobe(false);
            }}
            onClose={() => setShowWardrobe(false)}
          />
        )}

        {/* 節目モーダル */}
        {showMilestone && (
          <MilestoneModal
            run={activeRun}
            catalog={catalog}
            onClose={() => setShowMilestone(false)}
          />
        )}
      </div>
    </MainLayout>
  );
}
