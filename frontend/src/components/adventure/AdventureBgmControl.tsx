import { useTranslation } from "react-i18next";

import type { AdventureVoiceStatus } from "../../hooks/useAdventureVoice";
import { VOICE_SPEED_OPTIONS } from "../../utils/voicePreferences";

/**
 * Adventure プレイ画面のサウンド操作 UI(BGM + セリフ読み上げ)。
 * ステージ右上の丸ボタンと、BGM のミュートトグル + 音量、セリフ読み上げの
 * ON/OFF + 音量 + 状態を1つのポップオーバーに置く。
 * 再生ロジックそのものは useAdventureBgm / useAdventureVoice が担い、
 * ここは表示と操作の中継だけを行う。
 */
export interface AdventureVoiceControlProps {
  /** 設定画面の音声合成(TTS)が有効か。OFF ならトグルを無効化して案内を出す */
  available: boolean;
  enabled: boolean;
  /** 0.0〜1.0 */
  volume: number;
  /** 再生速度の倍率。1.0 が等速 */
  speed: number;
  status: AdventureVoiceStatus;
  onEnabledChange: (next: boolean) => void;
  onVolumeChange: (next: number) => void;
  onSpeedChange: (next: number) => void;
  onStop: () => void;
}

interface AdventureBgmControlProps {
  muted: boolean;
  /** マスター音量 0.0〜1.0。表示は 0〜100% に換算する */
  volume: number;
  /** autoplay 制限で再生待機中のときに案内文を出す */
  autoplayBlocked: boolean;
  open: boolean;
  onToggleOpen: () => void;
  onMutedChange: (next: boolean) => void;
  onVolumeChange: (next: number) => void;
  /** セリフ読み上げ。未指定ならBGMだけを出す */
  voice?: AdventureVoiceControlProps;
}

export default function AdventureBgmControl({
  muted,
  volume,
  autoplayBlocked,
  open,
  onToggleOpen,
  onMutedChange,
  onVolumeChange,
  voice,
}: AdventureBgmControlProps) {
  const { t } = useTranslation();
  const voiceBusy = voice?.status === "loading" || voice?.status === "playing";
  return (
    <>
      <button
        type="button"
        className={`adventure-stage__bgm${
          muted ? " adventure-stage__bgm--muted" : ""
        }`}
        onClick={onToggleOpen}
        title={t("adventure.sound.settings")}
        aria-label={t("adventure.sound.settings")}
        aria-expanded={open}
      >
        ♪
      </button>
      {open && (
        <div className="adventure-bgm-popover">
          <h3 className="adventure-bgm-popover__section">
            {t("adventure.bgm.panelTitle")}
          </h3>
          <label className="adventure-precise-toggle">
            <span className="adventure-precise-toggle__info">
              <strong>{t("adventure.bgm.enable")}</strong>
              <small>{t("adventure.bgm.enableHint")}</small>
            </span>
            <input
              type="checkbox"
              className="adventure-precise-toggle__input"
              checked={!muted}
              onChange={(event) => onMutedChange(!event.target.checked)}
            />
            <span className="adventure-precise-toggle__switch" />
          </label>
          <div className="adventure-bgm-popover__volume">
            <span className="adventure-bgm-popover__volume-label">
              {t("adventure.bgm.volume")}
            </span>
            <input
              type="range"
              className="adventure-bgm-popover__slider"
              min={0}
              max={1}
              step={0.01}
              value={volume}
              onChange={(event) => onVolumeChange(Number(event.target.value))}
              aria-label={t("adventure.bgm.volume")}
            />
            <span className="adventure-bgm-popover__volume-value">
              {Math.round(volume * 100)}%
            </span>
          </div>
          {autoplayBlocked && !muted && (
            <p className="adventure-bgm-popover__hint">
              {t("adventure.bgm.autoplayBlockedHint")}
            </p>
          )}
          {voice && (
            <>
              <h3 className="adventure-bgm-popover__section">
                {t("adventure.voice.title")}
              </h3>
              {/* TTS が無効でもトグルは隠さず、有効化の導線を文言で示す */}
              <label className="adventure-precise-toggle">
                <span className="adventure-precise-toggle__info">
                  <strong>{t("adventure.voice.enable")}</strong>
                  <small>
                    {t(
                      voice.available
                        ? "adventure.voice.enableHint"
                        : "adventure.voice.disabledHint",
                    )}
                  </small>
                </span>
                <input
                  type="checkbox"
                  className="adventure-precise-toggle__input"
                  checked={voice.enabled && voice.available}
                  disabled={!voice.available}
                  onChange={(event) =>
                    voice.onEnabledChange(event.target.checked)
                  }
                />
                <span className="adventure-precise-toggle__switch" />
              </label>
              <div className="adventure-bgm-popover__volume">
                <span className="adventure-bgm-popover__volume-label">
                  {t("adventure.voice.volume")}
                </span>
                <input
                  type="range"
                  className="adventure-bgm-popover__slider"
                  min={0}
                  max={1}
                  step={0.01}
                  value={voice.volume}
                  disabled={!voice.available}
                  onChange={(event) =>
                    voice.onVolumeChange(Number(event.target.value))
                  }
                  aria-label={t("adventure.voice.volume")}
                />
                <span className="adventure-bgm-popover__volume-value">
                  {Math.round(voice.volume * 100)}%
                </span>
              </div>
              <div className="adventure-bgm-popover__volume">
                <span className="adventure-bgm-popover__volume-label">
                  {t("adventure.voice.speed")}
                </span>
                <select
                  className="adventure-bgm-popover__speed"
                  value={voice.speed}
                  disabled={!voice.available}
                  onChange={(event) =>
                    voice.onSpeedChange(Number(event.target.value))
                  }
                  aria-label={t("adventure.voice.speed")}
                >
                  {VOICE_SPEED_OPTIONS.map((rate) => (
                    <option key={rate} value={rate}>
                      {rate}x
                    </option>
                  ))}
                </select>
              </div>
              {voice.available && voice.enabled && (
                <div className="adventure-bgm-popover__status" role="status">
                  {voice.status === "loading" ? (
                    <div className="adventure-progress">
                      <span />
                      {t("adventure.voice.status.loading")}
                    </div>
                  ) : (
                    <span>{t(`adventure.voice.status.${voice.status}`)}</span>
                  )}
                  <button
                    type="button"
                    className="adventure-bgm-popover__stop"
                    disabled={!voiceBusy}
                    onClick={voice.onStop}
                  >
                    {t("adventure.voice.stop")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
