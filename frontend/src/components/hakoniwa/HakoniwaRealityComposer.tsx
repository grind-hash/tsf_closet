import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaResident } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

/** 改変の文の長さと、1人あたりの件数(バックエンドの HAKONIWA_REALITY_TEXT_MAX / HAKONIWA_REALITIES_MAX) */
const REALITY_TEXT_MAX = 300;
const REALITIES_MAX = 5;

interface HakoniwaRealityComposerProps {
  resident: HakoniwaResident;
}

/**
 * 住民パネルの「改変」: その住民についての世界の常識を書き換える。
 * 変身と違い、本人も周りも昔からそうだと受け止める。「姿も変える」なら姿も1枚生成する。
 */
export default function HakoniwaRealityComposer({
  resident,
}: HakoniwaRealityComposerProps) {
  const { t } = useTranslation();
  const { busy, playbackQueue, alterReality, removeReality } = useHakoniwa();
  const inputId = useId();
  const lookId = useId();
  const listId = useId();
  // 住民を切り替えても書きかけを残す
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [changeLook, setChangeLook] = useState(true);

  const draft = drafts[resident.id] ?? "";
  const realities = resident.realities ?? [];
  const full = realities.length >= REALITIES_MAX;
  const locked = busy !== null || playbackQueue.length > 0;

  const handleRun = () => {
    const instruction = draft.trim();
    if (!instruction || full) return;
    alterReality(resident.id, instruction, changeLook);
  };

  return (
    <>
      <label htmlFor={inputId}>
        <strong>{t("hakoniwa.panel.realityHeading")}</strong>
      </label>
      <textarea
        id={inputId}
        rows={3}
        maxLength={REALITY_TEXT_MAX}
        value={draft}
        placeholder={t("hakoniwa.panel.realityPlaceholder")}
        onChange={(event) =>
          setDrafts((current) => ({
            ...current,
            [resident.id]: event.target.value,
          }))
        }
      />
      <p className="hakoniwa-note">{t("hakoniwa.panel.realityNote")}</p>
      <label className="hakoniwa-toggle" htmlFor={lookId}>
        <span>
          {t("hakoniwa.panel.realityChangeLook")}
          <small className="hakoniwa-toggle__hint">
            {t("hakoniwa.panel.realityChangeLookHint")}
          </small>
        </span>
        <input
          id={lookId}
          type="checkbox"
          className="hakoniwa-toggle__input"
          checked={changeLook}
          onChange={(event) => setChangeLook(event.target.checked)}
        />
        <span className="hakoniwa-toggle__switch" aria-hidden />
      </label>
      {full && (
        <p className="hakoniwa-note hakoniwa-note--warning">
          {t("hakoniwa.panel.realityLimit", { max: REALITIES_MAX })}
        </p>
      )}
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--primary"
        onClick={handleRun}
        disabled={!draft.trim() || full || locked}
      >
        {busy === "reality" ? (
          <>
            <span className="hakoniwa-spinner" aria-hidden />
            {t("hakoniwa.panel.realityRunning")}
          </>
        ) : (
          t("hakoniwa.panel.reality")
        )}
      </button>
      {realities.length > 0 && (
        <div className="hakoniwa-reality">
          <span id={listId} className="hakoniwa-resident__subheading">
            {t("hakoniwa.panel.realityListHeading")}
          </span>
          <ul className="hakoniwa-reality__list" aria-labelledby={listId}>
            {realities.map((item) => (
              <li key={item.id} className="hakoniwa-reality__item">
                <span className="hakoniwa-reality__text">{item.text}</span>
                <button
                  type="button"
                  className="hakoniwa-icon-button"
                  aria-label={t("hakoniwa.panel.realityRemove")}
                  title={t("hakoniwa.panel.realityRemove")}
                  onClick={() => void removeReality(resident.id, item.id)}
                  disabled={locked}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
