import { useTranslation } from "react-i18next";

/**
 * Adventure プレイ画面の BGM 操作 UI。
 * ステージ右上の丸ボタンと、ミュートトグル + 音量スライダーのポップオーバーを描く。
 * 再生ロジックそのものは useAdventureBgm が担い、ここは表示と操作の中継だけを行う。
 */
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
}

export default function AdventureBgmControl({
  muted,
  volume,
  autoplayBlocked,
  open,
  onToggleOpen,
  onMutedChange,
  onVolumeChange,
}: AdventureBgmControlProps) {
  const { t } = useTranslation();
  return (
    <>
      <button
        type="button"
        className={`adventure-stage__bgm${
          muted ? " adventure-stage__bgm--muted" : ""
        }`}
        onClick={onToggleOpen}
        title={t("adventure.bgm.settings")}
        aria-label={t("adventure.bgm.settings")}
        aria-expanded={open}
      >
        ♪
      </button>
      {open && (
        <div className="adventure-bgm-popover">
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
        </div>
      )}
    </>
  );
}
