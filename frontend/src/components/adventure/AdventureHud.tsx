import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { AdventureBgmKey } from "../../apis/adventure";
import { canActOnRun } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { AnlasBalance } from "../../types";
import { speechStyleLabel } from "../../utils/adventureFormat";
import type { AdventureSceneView } from "../../utils/adventureSceneView";
import AdventureInventoryPanel from "./AdventureInventoryPanel";

export type AdventureHudPanel =
  | "milestones"
  | "clues"
  | "realityRules"
  | "speechStyle"
  | "bgm"
  | "inventory";

/**
 * romance HUD の共通タイル。
 * 4段(ラベル/値/ゲージ/バッジ)を常に描画し、Day・好感度・所持金の高さを揃える。
 * 値の無い段は visibility を落として枠だけ残す。
 */
function HudTile({
  className,
  title,
  label,
  value,
  gaugeRatio,
  badge,
  badgeClassName,
}: {
  className?: string;
  title?: string;
  label: ReactNode;
  value: ReactNode;
  gaugeRatio: number | null;
  badge: ReactNode | null;
  badgeClassName?: string;
}) {
  return (
    <div
      className={`adventure-hud__tile${className ? ` ${className}` : ""}`}
      title={title}
    >
      <span className="adventure-hud__tile-label">{label}</span>
      <strong className="adventure-hud__tile-value">{value}</strong>
      <span
        className={`adventure-hud__gauge${gaugeRatio === null ? " is-empty" : ""}`}
        aria-hidden
      >
        <i style={{ width: `${gaugeRatio ?? 0}%` }} />
      </span>
      <em
        className={`adventure-hud__tile-badge${badge === null ? " is-empty" : ""}${
          badgeClassName ? ` ${badgeClassName}` : ""
        }`}
      >
        {badge ?? "-"}
      </em>
    </div>
  );
}

interface AdventureHudProps {
  scene: AdventureSceneView;
  hudPanel: AdventureHudPanel | null;
  onToggleHudPanel: (panel: AdventureHudPanel) => void;
  onCloseHudPanel: () => void;
  /** 表示中フレームのBGMキーと選曲理由 */
  currentBgm: { key: AdventureBgmKey; reason: string | null } | null;
  /** 今ステージに映っている場面の枠(過去閲覧中はそのフレームに追従) */
  stageDaySlot: { day: number; slot: "day" | "night" };
  /** 表示中フレームがエピローグ期か */
  stageEpilogue: boolean;
  isEpilogue: boolean;
  isCompanion: boolean;
  turnRatio: number;
  anlasBalance: AnlasBalance | null;
  /** run のモデル上書きを含めた実効モデルが V5 か */
  runIsV5: boolean;
  viewingPast: boolean;
  protagonistDockOpen: boolean;
  /** 白抜き済みの最新の主人公立ち絵(チップのサムネイル) */
  protagonistThumbUrl: string | null;
  onToggleProtagonistDock: () => void;
  onOpenSpeechStyle: () => void;
  onOpenAttributes: () => void;
}

/** 画面上部の HUD。メトリクス・チップ列と、チップで開くポップオーバー */
export default function AdventureHud({
  scene,
  hudPanel,
  onToggleHudPanel,
  onCloseHudPanel,
  currentBgm,
  stageDaySlot,
  stageEpilogue,
  isEpilogue,
  isCompanion,
  turnRatio,
  anlasBalance,
  runIsV5,
  viewingPast,
  protagonistDockOpen,
  protagonistThumbUrl,
  onToggleProtagonistDock,
  onOpenSpeechStyle,
  onOpenAttributes,
}: AdventureHudProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeRun } = useAdventure();
  const { state: settingsState } = useSettings();
  if (!activeRun) return null;
  const {
    sim,
    activeLocation,
    completedMilestones,
    realityRules,
    inventory,
    inventoryCount,
  } = scene;
  // HUD の V5 利用上限表示(実効モデルが V5 のときのみ)
  const hudUsage = runIsV5 ? (anlasBalance?.usage ?? null) : null;
  const hudUsageExhausted =
    hudUsage != null && (hudUsage.percent <= 0 || hudUsage.isNegative);
  const hudUsagePercent =
    hudUsage != null ? Math.max(0, Math.min(100, hudUsage.percent)) : 0;

  return (
    <div className={`adventure-hud${sim ? " adventure-hud--romance" : ""}`}>
      <button
        type="button"
        className="adventure-hud__back"
        onClick={() => navigate("/adventure")}
        aria-label={t("adventure.back")}
      >
        ←
      </button>
      <div className="adventure-hud__title">
        <p>{activeRun.title}</p>
        <h1 title={activeRun.objective}>
          <b>{t("adventure.goal")}</b>
          <span>{activeRun.objective}</span>
        </h1>
      </div>
      {(activeLocation || currentBgm) && (
        <div className="adventure-hud__location-stack">
          {activeLocation && (
            <span className="adventure-hud__location" title={activeLocation}>
              <b>{t("adventure.currentLocation")}</b>
              <span>{activeLocation}</span>
            </span>
          )}
          {currentBgm && (
            <button
              type="button"
              className={`adventure-hud__bgm-chip${
                hudPanel === "bgm" ? " is-open" : ""
              }`}
              aria-expanded={hudPanel === "bgm"}
              title={t("adventure.bgm.chipHint")}
              onClick={() => onToggleHudPanel("bgm")}
            >
              <span aria-hidden>♪</span>
              <span>{currentBgm.key}</span>
            </button>
          )}
        </div>
      )}
      <div className="adventure-hud__metrics">
        {sim && isCompanion ? (
          // 対面会話モード: 昼夜の枠が無いのでターン数(1ターン=1往復)を出す
          <HudTile
            className="adventure-hud__day is-day"
            title={
              stageEpilogue
                ? t("adventure.epilogueTurnsHint")
                : t("adventure.companion.turnCounterHint", {
                    turn: activeRun.turn_count,
                    max: activeRun.max_turns,
                  })
            }
            label={t("adventure.companion.turnLabel")}
            value={
              stageEpilogue ? (
                t("adventure.epilogueLabel")
              ) : (
                <>
                  {activeRun.turn_count}
                  <i>/{activeRun.max_turns}</i>
                </>
              )
            }
            gaugeRatio={stageEpilogue ? null : turnRatio}
            badge={
              stageEpilogue
                ? null
                : t("adventure.companion.turnsLeft", {
                    count: activeRun.remaining_turns,
                  })
            }
            badgeClassName="adventure-hud__slot is-day"
          />
        ) : sim ? (
          // エピローグでは期限が無いため「N日目」の開放表示に切り替え、
          // 残りターンのゲージも出さない
          <HudTile
            className={`adventure-hud__day is-${stageDaySlot.slot}`}
            title={
              stageEpilogue
                ? t("adventure.romance.dayCounterEpilogueHint")
                : t("adventure.romance.dayCounterHint", {
                    day: sim.day,
                    total: sim.total_days,
                    slot: t(`adventure.romance.slot.${sim.slot}`),
                  })
            }
            label={t("adventure.romance.day")}
            value={
              stageEpilogue ? (
                t("adventure.romance.dayOpen", { day: stageDaySlot.day })
              ) : (
                <>
                  {stageDaySlot.day}
                  <i>/{sim.total_days}</i>
                </>
              )
            }
            gaugeRatio={stageEpilogue ? null : turnRatio}
            badge={t(`adventure.romance.slot.${stageDaySlot.slot}`)}
            badgeClassName={`adventure-hud__slot is-${stageDaySlot.slot}`}
          />
        ) : isEpilogue ? (
          <div
            className="adventure-hud__turns"
            title={t("adventure.epilogueTurnsHint")}
          >
            <span>{t("adventure.epilogueLabel")}</span>
            <strong>
              {t("adventure.epilogueTurns", {
                turn: activeRun.turn_count,
              })}
            </strong>
          </div>
        ) : (
          <div
            className="adventure-hud__turns"
            title={t("adventure.remaining")}
          >
            <span>{t("adventure.remaining")}</span>
            <strong>
              {activeRun.remaining_turns}
              <i>/{activeRun.max_turns}</i>
            </strong>
            <span className="adventure-hud__gauge" aria-hidden>
              <i style={{ width: `${turnRatio}%` }} />
            </span>
          </div>
        )}
        {sim && (
          <>
            <HudTile
              className={`adventure-hud__affection is-${sim.stage}`}
              title={t(`adventure.romance.stages.${sim.stage}`)}
              label={t("adventure.romance.affection")}
              value={
                <>
                  <svg
                    className="adventure-hud__heart"
                    viewBox="0 0 24 24"
                    aria-hidden
                  >
                    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                  </svg>
                  {sim.affection}
                  <i>/100</i>
                </>
              }
              gaugeRatio={sim.affection}
              badge={t(`adventure.romance.stages.${sim.stage}`)}
              badgeClassName="adventure-hud__stage"
            />
            <HudTile
              className="adventure-hud__money"
              title={t("adventure.romance.money")}
              label={t("adventure.romance.money")}
              value={sim.money.toLocaleString()}
              gaugeRatio={null}
              badge={t("adventure.romance.moneyUnit")}
            />
          </>
        )}
        {/* V5 利用上限。通常ゲームHUDと同じく Anlas の左隣に置く */}
        {hudUsage &&
          (sim ? (
            <HudTile
              className={`adventure-hud__usage-tile${
                hudUsageExhausted ? " is-warning" : ""
              }`}
              title={t("gameplay.novelaiUsageTooltip", {
                percent: hudUsage.percent,
              })}
              label={t("gameplay.novelaiUsageLabel")}
              value={
                hudUsageExhausted
                  ? t("gameplay.novelaiUsageExhausted")
                  : `${hudUsage.percent}%`
              }
              gaugeRatio={hudUsagePercent}
              badge={null}
            />
          ) : (
            <div
              className={`adventure-hud__usage${
                hudUsageExhausted ? " is-warning" : ""
              }`}
              title={t("gameplay.novelaiUsageTooltip", {
                percent: hudUsage.percent,
              })}
            >
              <span>{t("gameplay.novelaiUsageLabel")}</span>
              <strong>
                {hudUsageExhausted
                  ? t("gameplay.novelaiUsageExhausted")
                  : `${hudUsage.percent}%`}
              </strong>
              <span className="adventure-hud__gauge" aria-hidden>
                <i style={{ width: `${hudUsagePercent}%` }} />
              </span>
            </div>
          ))}
        {(activeRun.use_precise_reference || runIsV5) &&
          anlasBalance &&
          (sim ? (
            // romance では他のメトリクスと同じ共通タイルで並べる。
            // 精密参照ON時 / V5実効時だけ出るので、バッジで理由を示す
            <HudTile
              className="adventure-hud__anlas-tile"
              title={t("adventure.anlasDetail", {
                fixed: anlasBalance.fixedAnlas.toLocaleString(),
                purchased: anlasBalance.purchasedAnlas.toLocaleString(),
              })}
              label="Anlas"
              value={anlasBalance.totalAnlas.toLocaleString()}
              gaugeRatio={null}
              badge={
                runIsV5
                  ? t("adventure.anlasBadgeV5")
                  : t("adventure.anlasBadge")
              }
            />
          ) : (
            <div
              className="adventure-hud__anlas"
              title={t("adventure.anlasDetail", {
                fixed: anlasBalance.fixedAnlas.toLocaleString(),
                purchased: anlasBalance.purchasedAnlas.toLocaleString(),
              })}
            >
              <span>Anlas</span>
              <strong>{anlasBalance.totalAnlas.toLocaleString()}</strong>
            </div>
          ))}
        {/* OpenRouter利用時は従量課金なので累計API料金を常時見せる。
            通常ゲーム画面のコストバーと同じ累計値(SettingsContext)を表示する */}
        {settingsState.showCost &&
          (sim ? (
            <HudTile
              className="adventure-hud__cost-tile"
              title={t("gameplay.apiCost")}
              label={t("gameplay.apiCost")}
              value={`$${settingsState.totalCost.toFixed(4)}`}
              gaugeRatio={null}
              badge={null}
            />
          ) : (
            <div className="adventure-hud__cost" title={t("gameplay.apiCost")}>
              <span>{t("gameplay.apiCost")}</span>
              <strong>${settingsState.totalCost.toFixed(4)}</strong>
            </div>
          ))}
        {activeRun.milestones.length > 0 && (
          <button
            type="button"
            className={`adventure-hud__chip${hudPanel === "milestones" ? " is-open" : ""}`}
            aria-expanded={hudPanel === "milestones"}
            onClick={() => onToggleHudPanel("milestones")}
          >
            <span>{t("adventure.milestones")}</span>
            <strong>
              {completedMilestones.size}
              <i>/{activeRun.milestones.length}</i>
            </strong>
          </button>
        )}
        <button
          type="button"
          className={`adventure-hud__chip${hudPanel === "clues" ? " is-open" : ""}`}
          aria-expanded={hudPanel === "clues"}
          disabled={activeRun.clues.length === 0}
          onClick={() => onToggleHudPanel("clues")}
        >
          <span>{t(sim ? "adventure.romance.hints" : "adventure.clues")}</span>
          <strong>{activeRun.clues.length}</strong>
        </button>
        {realityRules.length > 0 && (
          <button
            type="button"
            className={`adventure-hud__chip${hudPanel === "realityRules" ? " is-open" : ""}`}
            aria-expanded={hudPanel === "realityRules"}
            onClick={() => onToggleHudPanel("realityRules")}
          >
            <span>
              {t(
                sim
                  ? "adventure.romance.grantedAttributes"
                  : "adventure.realityRules",
              )}
            </span>
            <strong>{realityRules.length}</strong>
          </button>
        )}
        {inventory && (
          <button
            type="button"
            className={`adventure-hud__chip adventure-hud__chip--inventory${
              hudPanel === "inventory" ? " is-open" : ""
            }`}
            aria-expanded={hudPanel === "inventory"}
            onClick={() => onToggleHudPanel("inventory")}
          >
            <span>{t("adventure.inventory")}</span>
            <strong>{inventoryCount}</strong>
          </button>
        )}
        <button
          type="button"
          className={`adventure-hud__chip adventure-hud__chip--speech${
            hudPanel === "speechStyle" ? " is-open" : ""
          }`}
          aria-expanded={hudPanel === "speechStyle"}
          onClick={() => onToggleHudPanel("speechStyle")}
        >
          <span>{t("adventure.speechStyleChip")}</span>
          {/* 自由入力の全文はポップオーバーで読めるため、チップは分類名だけ出す */}
          <strong>
            {t(`adventure.speechStyles.${activeRun.player_speech_style}`)}
          </strong>
        </button>
        <button
          type="button"
          className={`adventure-hud__chip adventure-hud__chip--protagonist${
            protagonistDockOpen ? " is-open" : ""
          }`}
          aria-pressed={protagonistDockOpen}
          title={t("adventure.protagonistToggleHint")}
          disabled={!protagonistThumbUrl && !activeRun.visual_state}
          onClick={onToggleProtagonistDock}
        >
          <span>{t("adventure.protagonist")}</span>
          {protagonistThumbUrl ? (
            <img
              className="adventure-hud__chip-thumb"
              src={protagonistThumbUrl}
              alt=""
            />
          ) : (
            <strong>-</strong>
          )}
        </button>
      </div>
      {hudPanel && (
        <div
          className="adventure-hud__popover"
          role="dialog"
          aria-label={t(
            // adventure.bgm は i18n 上オブジェクトのため専用キーを使う
            hudPanel === "bgm"
              ? "adventure.bgm.panelTitle"
              : `adventure.${hudPanel}`,
          )}
        >
          {hudPanel === "inventory" ? (
            <AdventureInventoryPanel
              onClose={onCloseHudPanel}
              viewingPast={viewingPast}
            />
          ) : hudPanel === "speechStyle" ? (
            <>
              <p className="adventure-hud__note">
                {t("adventure.speechStyleHint")}
              </p>
              <dl className="adventure-hud__facts">
                <div>
                  <dt>{t("adventure.protagonist")}</dt>
                  <dd>
                    {speechStyleLabel(
                      activeRun.player_speech_style,
                      activeRun.player_speech_custom,
                      t,
                    )}
                  </dd>
                </div>
                {sim && (
                  <div>
                    <dt>{sim.partner_name}</dt>
                    <dd>
                      {sim.partner_speech_style ||
                        t("adventure.romance.partnerSpeechStyleAuto")}
                    </dd>
                  </div>
                )}
              </dl>
              <button
                type="button"
                className="adventure-hud__panel-action"
                disabled={!canActOnRun(activeRun)}
                onClick={() => {
                  onCloseHudPanel();
                  onOpenSpeechStyle();
                }}
              >
                {t("adventure.speechStyleManager.manage")}
              </button>
            </>
          ) : hudPanel === "bgm" ? (
            <>
              <p className="adventure-hud__bgm-key">
                <span aria-hidden>♪</span>
                <strong>{currentBgm?.key ?? "daily"}</strong>
              </p>
              <p className="adventure-hud__note">
                {t("adventure.bgm.reasonLabel")}
              </p>
              <p className="adventure-hud__bgm-reason">
                {currentBgm?.reason ?? t("adventure.bgm.noReason")}
              </p>
            </>
          ) : hudPanel === "milestones" ? (
            <ul className="adventure-hud__milestones">
              {activeRun.milestones.map((milestone) => {
                const done = completedMilestones.has(milestone.id);
                return (
                  <li key={milestone.id} className={done ? "is-done" : ""}>
                    <span aria-hidden>{done ? "✓" : "・"}</span>
                    {milestone.label}
                    {done && <em>{t("adventure.milestoneDone")}</em>}
                  </li>
                );
              })}
            </ul>
          ) : hudPanel === "realityRules" ? (
            <>
              <p className="adventure-hud__note">
                {t(
                  sim
                    ? "adventure.romance.grantedAttributesHint"
                    : "adventure.realityRulesHint",
                )}
              </p>
              <ul className="adventure-hud__clues">
                {realityRules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              <button
                type="button"
                className="adventure-hud__panel-action"
                disabled={!canActOnRun(activeRun)}
                onClick={() => {
                  onCloseHudPanel();
                  onOpenAttributes();
                }}
              >
                {t(
                  sim
                    ? "adventure.romance.attribute.manage"
                    : "adventure.realityRuleManager.manage",
                )}
              </button>
            </>
          ) : (
            <ul className="adventure-hud__clues">
              {activeRun.clues.map((clue) => (
                <li key={clue}>{clue}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
