import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { UseAdventureBgmResult } from "../../hooks/useAdventureBgm";

interface SalonBgmControlProps {
  bgm: UseAdventureBgmResult;
}

/**
 * サロンの BGM の ON/OFF と音量。設定は TSF シナリオ・BGM テスト画面と共通
 * (utils/bgmPreferences)。曲がまだ置かれていなければ出さない。
 */
export default function SalonBgmControl({ bgm }: SalonBgmControlProps) {
  const { t } = useTranslation();
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

  if (!bgm.playable) return null;
  return (
    <div className="salon-bgm">
      <button
        type="button"
        className={`salon-bgm__button${bgm.muted ? " is-muted" : ""}`}
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
              aria-label={t("salon.bgm.volume")}
              onChange={(event) => bgm.setVolume(Number(event.target.value))}
            />
            <span className="salon-bgm__value">
              {Math.round(bgm.volume * 100)}%
            </span>
          </div>
          {bgm.autoplayBlocked && !bgm.muted && (
            <p className="salon-bgm__hint">{t("salon.bgm.autoplayBlocked")}</p>
          )}
        </div>
      )}
    </div>
  );
}
