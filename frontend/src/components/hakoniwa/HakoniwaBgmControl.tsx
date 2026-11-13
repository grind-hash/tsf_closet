import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  useId,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { UseAdventureBgmResult } from "../../hooks/useAdventureBgm";

interface HakoniwaBgmControlProps {
  bgm: UseAdventureBgmResult;
  /** パネルを開く向き。ADV のメッセージ窓の中では上へ開く */
  placement?: "down" | "up";
}

/**
 * AI箱庭の BGM の ON/OFF・音量(♪ パネル)。TSF シナリオ・サロンとは別の設定で、初回はミュート
 * (utils/bgmPreferences の hakoniwa)。
 * ADV の中にも置くため、クリックとキー操作は外へ伝えない(場面が進んだり ADV が閉じたりしない)。
 */
export default function HakoniwaBgmControl({
  bgm,
  placement = "down",
}: HakoniwaBgmControlProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // 上へ開くとき(ADV のメッセージ窓)は窓のスクロール領域で切れないよう、画面基準の位置に置く
  const [panelStyle, setPanelStyle] = useState<CSSProperties | undefined>();
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const panelId = useId();

  if (!bgm.playable) return null;
  const stop = (event: MouseEvent) => event.stopPropagation();
  const toggle = () => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!open && placement === "up" && rect) {
      setPanelStyle({
        right: Math.max(8, window.innerWidth - rect.right),
        bottom: window.innerHeight - rect.top + 8,
      });
    }
    setOpen(!open);
  };
  const handleKeyDown = (event: KeyboardEvent) => {
    // パネルを開いている間の Esc はパネルだけを閉じる
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    }
  };
  return (
    <div
      className={`hakoniwa-bgm hakoniwa-bgm--${placement}`}
      role="group"
      aria-label={t("hakoniwa.bgm.settings")}
      onClick={stop}
      onKeyDown={handleKeyDown}
    >
      <button
        ref={buttonRef}
        type="button"
        className={`hakoniwa-bgm__button${bgm.muted ? " is-muted" : ""}`}
        aria-label={t("hakoniwa.bgm.settings")}
        title={t("hakoniwa.bgm.settings")}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
      >
        ♪
      </button>
      {open && (
        <div
          id={panelId}
          className="hakoniwa-bgm__panel"
          style={placement === "up" ? panelStyle : undefined}
        >
          <label className="hakoniwa-toggle">
            <span>
              <strong>{t("hakoniwa.bgm.enable")}</strong>
              <small className="hakoniwa-toggle__hint">
                {t("hakoniwa.bgm.enableHint")}
              </small>
            </span>
            <input
              type="checkbox"
              className="hakoniwa-toggle__input"
              checked={!bgm.muted}
              onChange={(event) => bgm.setMuted(!event.target.checked)}
            />
            <span className="hakoniwa-toggle__switch" aria-hidden />
          </label>
          <div className="hakoniwa-bgm__volume">
            <span>{t("hakoniwa.bgm.volume")}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={bgm.volume}
              aria-label={t("hakoniwa.bgm.volume")}
              onChange={(event) => bgm.setVolume(Number(event.target.value))}
            />
            <span className="hakoniwa-bgm__value">
              {Math.round(bgm.volume * 100)}%
            </span>
          </div>
          {bgm.autoplayBlocked && !bgm.muted && (
            <p className="hakoniwa-note">{t("hakoniwa.bgm.autoplayBlocked")}</p>
          )}
        </div>
      )}
    </div>
  );
}
