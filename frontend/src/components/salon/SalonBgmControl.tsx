import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSalon } from "../../contexts/SalonContext";
import type { UseAdventureBgmResult } from "../../hooks/useAdventureBgm";

interface SalonBgmControlProps {
  bgm: UseAdventureBgmResult;
}

/**
 * サロンの BGM と効果音の ON/OFF・音量(♪ パネル)。どちらも TSF シナリオとは別の設定で、
 * 初回はミュート(utils/bgmPreferences の salon / salon_se)。
 * 曲も効果音も置かれていなければ出さず、置かれている方の欄だけを出す。
 */
export default function SalonBgmControl({ bgm }: SalonBgmControlProps) {
  const { t } = useTranslation();
  const { soundEffects: se } = useSalon();
  const [open, setOpen] = useState(false);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  if (!bgm.playable && !se.available) return null;
  const allMuted = (!bgm.playable || bgm.muted) && (!se.available || se.muted);
  return (
    <div className="salon-bgm">
      <button
        type="button"
        className={`salon-bgm__button${allMuted ? " is-muted" : ""}`}
        aria-label={t("salon.bgm.settings")}
        title={t("salon.bgm.settings")}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        ♪
      </button>
      {open && (
        <div id={panelId} className="salon-bgm__panel">
          {bgm.playable && (
            <div className="salon-bgm__section">
              <label className="salon-toggle">
                <span className="salon-toggle__info">
                  <strong>{t("salon.bgm.enable")}</strong>
                  <small>{t("salon.bgm.enableHint")}</small>
                </span>
                <input
                  type="checkbox"
                  className="salon-toggle__input"
                  checked={!bgm.muted}
                  onChange={(event) => bgm.setMuted(!event.target.checked)}
                />
                <span className="salon-toggle__switch" aria-hidden />
              </label>
              <div className="salon-bgm__volume">
                <span>{t("salon.bgm.volume")}</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={bgm.volume}
                  aria-label={t("salon.bgm.bgmVolume")}
                  onChange={(event) =>
                    bgm.setVolume(Number(event.target.value))
                  }
                />
                <span className="salon-bgm__value">
                  {Math.round(bgm.volume * 100)}%
                </span>
              </div>
              {bgm.autoplayBlocked && !bgm.muted && (
                <p className="salon-bgm__hint">
                  {t("salon.bgm.autoplayBlocked")}
                </p>
              )}
            </div>
          )}
          {se.available && (
            <div className="salon-bgm__section">
              <label className="salon-toggle">
                <span className="salon-toggle__info">
                  <strong>{t("salon.bgm.seEnable")}</strong>
                  <small>{t("salon.bgm.seEnableHint")}</small>
                </span>
                <input
                  type="checkbox"
                  className="salon-toggle__input"
                  checked={!se.muted}
                  onChange={(event) => se.setMuted(!event.target.checked)}
                />
                <span className="salon-toggle__switch" aria-hidden />
              </label>
              <div className="salon-bgm__volume">
                <span>{t("salon.bgm.volume")}</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={se.volume}
                  aria-label={t("salon.bgm.seVolume")}
                  onChange={(event) => se.setVolume(Number(event.target.value))}
                />
                <span className="salon-bgm__value">
                  {Math.round(se.volume * 100)}%
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
