import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { readStorageFlag, writeStorageFlag } from "../../utils/storage";

const DISMISSED_KEY_PREFIX = "hakoniwa.introDismissed.";

/**
 * はじまりの案内。1日目で出来事がまだ無い世界だけ、右パネルのタブの上に出す
 * (部屋に重ねると、案内が勧める住民のクリックを覆ってしまうため)。
 * 「畳む」で細い帯になり、帯の ✕ で閉じるとその世界では出さない(世界ごとに記録)。
 */
export default function HakoniwaIntro() {
  const { t } = useTranslation();
  const { world, busy, playbackQueue, advanceDay, setPanelTab } = useHakoniwa();
  const worldId = world?.id ?? "";
  const [folded, setFolded] = useState(false);
  // 閉じた世界の id(この画面で閉じたもの)。保存できない環境でも、開いている間は閉じたままにする
  const [dismissedId, setDismissedId] = useState<string | null>(null);

  if (!world) return null;
  const eligible = world.day === 1 && world.events.length === 0;
  const dismissed =
    dismissedId === worldId ||
    readStorageFlag("local", `${DISMISSED_KEY_PREFIX}${worldId}`);
  if (!eligible || dismissed) return null;

  const openRules = () => setPanelTab("rules");
  const startDay = () => void advanceDay();
  const dismiss = () => {
    writeStorageFlag("local", `${DISMISSED_KEY_PREFIX}${worldId}`, true);
    setDismissedId(worldId);
  };
  const actions = (
    <>
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--ghost"
        onClick={openRules}
      >
        {t("hakoniwa.intro.openRules")}
      </button>
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--primary"
        onClick={startDay}
        disabled={busy !== null || playbackQueue.length > 0}
      >
        {t("hakoniwa.intro.advance")}
      </button>
    </>
  );

  if (folded) {
    return (
      <div
        className="hakoniwa-intro hakoniwa-intro--strip"
        role="region"
        aria-label={t("hakoniwa.intro.title")}
      >
        <strong className="hakoniwa-intro__label">
          {t("hakoniwa.intro.title")}
        </strong>
        <div className="hakoniwa-intro__actions">
          {actions}
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost"
            onClick={() => setFolded(false)}
          >
            {t("hakoniwa.intro.open")}
          </button>
          <button
            type="button"
            className="hakoniwa-icon-button"
            aria-label={t("hakoniwa.intro.dismiss")}
            title={t("hakoniwa.intro.dismiss")}
            onClick={dismiss}
          >
            ×
          </button>
        </div>
      </div>
    );
  }

  return (
    <section
      className="hakoniwa-intro"
      aria-label={t("hakoniwa.intro.title")}
      data-testid="hakoniwa-intro"
    >
      <div className="hakoniwa-intro__head">
        <strong>{t("hakoniwa.intro.title")}</strong>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => setFolded(true)}
        >
          {t("hakoniwa.intro.fold")}
        </button>
      </div>
      {/* 文だけをスクロールさせ、操作のボタンは常に見えるようにする */}
      <div className="hakoniwa-intro__body">
        <p>{t("hakoniwa.intro.lead")}</p>
        <ol className="hakoniwa-intro__steps">
          <li>{t("hakoniwa.intro.stepRules")}</li>
          <li>{t("hakoniwa.intro.stepClick")}</li>
          <li>{t("hakoniwa.intro.stepAdvance")}</li>
        </ol>
        {world.dissonance.enabled && (
          <p className="hakoniwa-note">{t("hakoniwa.intro.noteDissonance")}</p>
        )}
      </div>
      <div className="hakoniwa-intro__actions">{actions}</div>
    </section>
  );
}
