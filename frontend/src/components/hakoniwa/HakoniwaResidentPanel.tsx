import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { type HakoniwaResident, hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaPortrait from "./HakoniwaPortrait";
import { affinityLevel, moodLevel } from "./hakoniwaLabels";

const TRANSFORM_MAX = 500;

interface HakoniwaResidentPanelProps {
  resident: HakoniwaResident;
  onEdit: () => void;
}

/** 選んだ住民の詳細: 話しかける・その場で変身・姿の生成・編集 */
export default function HakoniwaResidentPanel({
  resident,
  onEdit,
}: HakoniwaResidentPanelProps) {
  const { t } = useTranslation();
  const {
    world,
    busy,
    greet,
    greetingResidentId,
    transform,
    clearTransform,
    reapplyTransform,
    generateAvatar,
    removeResident,
    selectResident,
    playbackQueue,
  } = useHakoniwa();
  const transformId = useId();
  // 住民を切り替えても書きかけの指定を残す
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [confirmRemove, setConfirmRemove] = useState(false);

  if (!world) return null;
  const draft = drafts[resident.id] ?? "";
  const names = Object.fromEntries(
    world.residents.map((item) => [item.id, item.name]),
  );
  const locked = busy !== null || playbackQueue.length > 0;
  const swappedName = resident.swapped_with
    ? names[resident.swapped_with]
    : null;
  const relations = Object.entries(resident.affinities)
    .filter(([id]) => names[id])
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

  const handleTransform = () => {
    const instruction = draft.trim();
    if (!instruction) return;
    transform(resident.id, instruction);
  };

  return (
    <section className="hakoniwa-resident" aria-label={resident.name}>
      <div className="hakoniwa-resident__head">
        <div className="hakoniwa-resident__look">
          {resident.display_avatar_url ? (
            <HakoniwaPortrait
              src={hakoniwaMediaUrl(resident.display_avatar_url)}
              alt={t("hakoniwa.panel.lookPreview", { name: resident.name })}
              className="hakoniwa-resident__portrait"
            />
          ) : (
            <span className="hakoniwa-resident__portrait hakoniwa-resident__portrait--empty">
              {t("hakoniwa.residents.noAvatar")}
            </span>
          )}
        </div>
        <div className="hakoniwa-resident__summary">
          <div className="hakoniwa-resident__title">
            <h3>{resident.name}</h3>
            <button
              type="button"
              className="hakoniwa-icon-button"
              aria-label={t("hakoniwa.panel.close")}
              title={t("hakoniwa.panel.close")}
              onClick={() => selectResident(null)}
            >
              ×
            </button>
          </div>
          <p className="hakoniwa-resident__meta">
            {t(`hakoniwa.gender.${resident.gender}`)}・{resident.age}・
            {resident.job}
          </p>
          <p className="hakoniwa-resident__meta">
            {t("hakoniwa.residents.mood")}:{" "}
            {t(`hakoniwa.residents.moodLabels.${moodLevel(resident.mood)}`)}（
            {resident.mood}）
          </p>
          <ul className="hakoniwa-resident__states">
            {swappedName && (
              <li className="hakoniwa-badge hakoniwa-badge--accent">
                {t("hakoniwa.residents.swappedWith", { name: swappedName })}
              </li>
            )}
            {resident.transformation && (
              <li className="hakoniwa-badge hakoniwa-badge--accent">
                {t("hakoniwa.residents.transformed")}
              </li>
            )}
            {resident.display_kind === "dress" && (
              <li className="hakoniwa-badge">
                {t("hakoniwa.residents.dressed")}
              </li>
            )}
          </ul>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--primary"
            onClick={() => void greet(resident.id)}
            disabled={greetingResidentId !== null || locked}
          >
            {greetingResidentId === resident.id ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.panel.talking")}
              </>
            ) : (
              t("hakoniwa.panel.talk")
            )}
          </button>
        </div>
      </div>

      <dl className="hakoniwa-resident__details">
        <dt>{t("hakoniwa.panel.personality")}</dt>
        <dd>{resident.personality}</dd>
        {relations.length > 0 && (
          <>
            <dt>{t("hakoniwa.panel.relations")}</dt>
            <dd>
              <ul className="hakoniwa-resident__relations">
                {relations.map(([id, value]) => (
                  <li key={id}>
                    <span>{names[id]}</span>
                    <span className="hakoniwa-resident__relation-level">
                      {t(
                        `hakoniwa.residents.affinityLabels.${affinityLevel(value)}`,
                      )}
                      （{value}）
                    </span>
                  </li>
                ))}
              </ul>
            </dd>
          </>
        )}
      </dl>

      <div className="hakoniwa-resident__block">
        <label htmlFor={transformId}>
          <strong>{t("hakoniwa.panel.transformHeading")}</strong>
        </label>
        <textarea
          id={transformId}
          rows={3}
          maxLength={TRANSFORM_MAX}
          value={draft}
          placeholder={t("hakoniwa.panel.transformPlaceholder")}
          onChange={(event) =>
            setDrafts((current) => ({
              ...current,
              [resident.id]: event.target.value,
            }))
          }
        />
        <p className="hakoniwa-note">{t("hakoniwa.panel.transformNote")}</p>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--primary"
          onClick={handleTransform}
          disabled={!draft.trim() || locked}
        >
          {busy === "transform" ? (
            <>
              <span className="hakoniwa-spinner" aria-hidden />
              {t("hakoniwa.panel.transforming")}
            </>
          ) : (
            t("hakoniwa.panel.transform")
          )}
        </button>
        {resident.transformation && (
          <div className="hakoniwa-resident__current">
            <p>
              {t("hakoniwa.panel.currentTransform", {
                description: resident.transformation.description,
              })}
            </p>
            <button
              type="button"
              className="hakoniwa-button"
              onClick={() => void clearTransform(resident.id)}
              disabled={locked}
            >
              {t("hakoniwa.panel.clearTransform")}
            </button>
          </div>
        )}
        {resident.transformation_history.length > 0 && (
          <>
            <p className="hakoniwa-resident__subheading">
              {t("hakoniwa.panel.historyHeading")}
            </p>
            <ul className="hakoniwa-resident__history">
              {[...resident.transformation_history].reverse().map((entry) => (
                <li key={entry.image}>
                  <HakoniwaPortrait
                    src={hakoniwaMediaUrl(entry.image_url)}
                    alt=""
                    className="hakoniwa-resident__history-face"
                  />
                  <span className="hakoniwa-resident__history-text">
                    {entry.description}
                  </span>
                  <button
                    type="button"
                    className="hakoniwa-button hakoniwa-button--ghost"
                    onClick={() =>
                      void reapplyTransform(resident.id, entry.image)
                    }
                    disabled={
                      locked || resident.transformation?.image === entry.image
                    }
                  >
                    {t("hakoniwa.panel.reapply")}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="hakoniwa-resident__block">
        <strong>{t("hakoniwa.panel.avatarHeading")}</strong>
        <p className="hakoniwa-note">{t("hakoniwa.panel.avatarNote")}</p>
        <div className="hakoniwa-resident__buttons">
          <button
            type="button"
            className="hakoniwa-button"
            onClick={() => generateAvatar(resident.id, "base")}
            disabled={locked}
          >
            {busy === "avatar" ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.panel.generating")}
              </>
            ) : (
              t("hakoniwa.panel.generateBase")
            )}
          </button>
          <button
            type="button"
            className="hakoniwa-button"
            onClick={() => generateAvatar(resident.id, "dress")}
            disabled={locked}
          >
            {t("hakoniwa.panel.generateDress")}
          </button>
        </div>
      </div>

      <div className="hakoniwa-resident__buttons">
        <button
          type="button"
          className="hakoniwa-button"
          onClick={onEdit}
          disabled={locked}
        >
          {t("hakoniwa.panel.edit")}
        </button>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => setConfirmRemove(true)}
          disabled={locked || world.residents.length <= 2}
        >
          {t("hakoniwa.panel.remove")}
        </button>
      </div>

      <ConfirmDialog
        open={confirmRemove}
        title={t("hakoniwa.panel.removeTitle")}
        confirmLabel={t("hakoniwa.panel.removeConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmRemove(false)}
        onConfirm={() => {
          setConfirmRemove(false);
          selectResident(null);
          void removeResident(resident.id);
        }}
      >
        <p>{t("hakoniwa.panel.removeBody", { name: resident.name })}</p>
      </ConfirmDialog>
    </section>
  );
}
