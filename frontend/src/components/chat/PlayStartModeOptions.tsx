/**
 * PlayStartModeOptions - プレイを始めるときの自分自身モード・依頼モード・施術の手数。
 *
 * 新規プレイ画面とキャラクター画面のプレイ開始ダイアログで共有する。
 * 値は GameContext が持ち、開始処理(startNewSession 等)がそれを読む。
 */

import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { REQUEST_TURN_LIMIT_CHOICES } from "../../constants/playLimits";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import "./PlayStartModeOptions.css";

export default function PlayStartModeOptions() {
  const { t } = useTranslation();
  const {
    state: gameState,
    setSelfMode,
    setRequestMode,
    setRequestTurnLimit,
  } = useGame();
  const { selfProfile } = useSettings();
  const turnsLabelId = useId();
  // 自分自身モードON + プロフィール未設定
  const selfModeNeedsProfile = gameState.selfMode && !selfProfile;

  return (
    <>
      {/* 自分自身モード (US5) */}
      <div className="play-start-options__mode">
        <label className="play-start-options__label">
          <input
            type="checkbox"
            role="switch"
            aria-checked={gameState.selfMode}
            checked={gameState.selfMode}
            onChange={(e) => setSelfMode(e.target.checked)}
            className="play-start-options__switch"
          />
          <span>{t("chat.welcome.selfMode")}</span>
        </label>
        <p className="play-start-options__desc">
          {t("chat.welcome.selfModeDescription")}
        </p>
        {selfModeNeedsProfile && (
          <p className="play-start-options__warning">
            {t("chat.welcome.selfModeNoProfile")}
            <Link
              to={ROUTES.SETTINGS}
              className="play-start-options__warning-link"
            >
              {t("chat.welcome.selfModeGoSettings")}
            </Link>
          </p>
        )}
      </div>

      {/* 依頼モード(既定 OFF)。自分自身モードでは効かないが、隠さず理由を示す */}
      <div className="play-start-options__mode">
        <label className="play-start-options__label">
          <input
            type="checkbox"
            role="switch"
            aria-checked={gameState.requestMode}
            checked={gameState.requestMode}
            onChange={(e) => setRequestMode(e.target.checked)}
            className="play-start-options__switch"
          />
          <span>{t("chat.request.mode")}</span>
        </label>
        <p className="play-start-options__desc">
          {t("chat.request.modeDescription")}
        </p>
        {/* 施術の手数。依頼モードを OFF にしていても隠さず、何に効くかを文言で示す */}
        <div className="play-start-options__turns">
          <span id={turnsLabelId}>{t("chat.request.turnLimitLabel")}</span>
          <div
            className="play-start-options__segments"
            role="group"
            aria-labelledby={turnsLabelId}
          >
            {REQUEST_TURN_LIMIT_CHOICES.map((value) => (
              <button
                key={value ?? "none"}
                type="button"
                className={
                  gameState.requestTurnLimit === value ? "is-active" : undefined
                }
                aria-pressed={gameState.requestTurnLimit === value}
                onClick={() => setRequestTurnLimit(value)}
              >
                {value === null
                  ? t("chat.request.turnLimitNone")
                  : t("chat.request.turnLimitValue", { count: value })}
              </button>
            ))}
          </div>
          <p className="play-start-options__desc">
            {t("chat.request.turnLimitHint")}
          </p>
        </div>
        {gameState.requestMode && gameState.selfMode && (
          <p className="play-start-options__warning">
            {t("chat.request.modeNoopSelf")}
          </p>
        )}
      </div>
    </>
  );
}

/** 自分自身モードでプロフィールが無いと開始できない(開始ボタンの無効化に使う) */
export function usePlayStartBlocked(): boolean {
  const { state: gameState } = useGame();
  const { selfProfile } = useSettings();
  return gameState.selfMode && !selfProfile;
}
