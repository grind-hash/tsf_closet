import { useTranslation } from "react-i18next";
import { VOICE_SPEED_OPTIONS } from "../../utils/voicePreferences";
import type { AdventureVoiceControlProps } from "../adventure/AdventureBgmControl";

interface CharacterChatSoundControlProps {
  open: boolean;
  onToggleOpen: () => void;
  voice: AdventureVoiceControlProps;
}

/**
 * 🔊 ボタンとポップオーバー。返答の読み上げ(AivisSpeech)の ON/OFF・音量・速度・状態。
 * TTS が無効でもトグルは隠さず、有効化の導線を文言で示す。
 */
export default function CharacterChatSoundControl({
  open,
  onToggleOpen,
  voice,
}: CharacterChatSoundControlProps) {
  const { t } = useTranslation();
  const busy = voice.status === "loading" || voice.status === "playing";
  return (
    <div className="character-chat__sound">
      <button
        type="button"
        className={`character-chat__icon-button${voice.enabled && voice.available ? " is-on" : ""}`}
        onClick={onToggleOpen}
        title={t("characterChat.room.sound")}
        aria-label={t("characterChat.room.sound")}
        aria-expanded={open}
      >
        🔊
      </button>
      {open && (
        <div className="character-chat__popover" role="dialog">
          <label className="character-chat__switch-row">
            <span className="character-chat__switch-info">
              <strong>{t("characterChat.room.voiceEnable")}</strong>
              <small>
                {t(
                  voice.available
                    ? "characterChat.room.voiceEnableHint"
                    : "adventure.voice.disabledHint",
                )}
              </small>
            </span>
            <input
              type="checkbox"
              className="character-chat__switch-input"
              checked={voice.enabled && voice.available}
              disabled={!voice.available}
              onChange={(event) => voice.onEnabledChange(event.target.checked)}
            />
            <span className="character-chat__switch" />
          </label>
          <div className="character-chat__range-row">
            <span>{t("adventure.voice.volume")}</span>
            <input
              type="range"
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
            <span>{Math.round(voice.volume * 100)}%</span>
          </div>
          <div className="character-chat__range-row">
            <span>{t("adventure.voice.speed")}</span>
            <select
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
            <div className="character-chat__voice-status" role="status">
              {voice.status === "loading" ? (
                <span className="character-chat__progress">
                  <span />
                  {t("adventure.voice.status.loading")}
                </span>
              ) : (
                <span>{t(`adventure.voice.status.${voice.status}`)}</span>
              )}
              <button type="button" disabled={!busy} onClick={voice.onStop}>
                {t("adventure.voice.stop")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
