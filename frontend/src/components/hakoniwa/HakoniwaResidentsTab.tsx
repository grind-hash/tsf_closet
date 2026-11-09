import { useState } from "react";
import { useTranslation } from "react-i18next";
import { type HakoniwaResident, hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaCharacterAdder from "./HakoniwaCharacterAdder";
import HakoniwaPortrait from "./HakoniwaPortrait";
import HakoniwaResidentModal from "./HakoniwaResidentModal";
import HakoniwaResidentPanel from "./HakoniwaResidentPanel";
import { moodLevel } from "./hakoniwaLabels";

const MAX_RESIDENTS = 10;

/** 住民タブ: 選んだ住民の詳細と、住民の一覧・迎え入れ */
export default function HakoniwaResidentsTab() {
  const { t } = useTranslation();
  const {
    world,
    busy,
    selectedResidentId,
    selectResident,
    addCharacterResident,
    generateMissingAvatars,
    avatarBatch,
  } = useHakoniwa();
  const [editing, setEditing] = useState<HakoniwaResident | "new" | null>(null);
  const [confirmAvatars, setConfirmAvatars] = useState(false);

  if (!world) return null;
  const selected =
    world.residents.find((resident) => resident.id === selectedResidentId) ??
    null;
  const full = world.residents.length >= MAX_RESIDENTS;
  const missing = world.residents.filter((resident) => !resident.avatar_url);

  return (
    <div className="hakoniwa-residents">
      {selected ? (
        <HakoniwaResidentPanel
          resident={selected}
          onEdit={() => setEditing(selected)}
        />
      ) : (
        <p className="hakoniwa-note">{t("hakoniwa.residents.selectHint")}</p>
      )}

      <ul className="hakoniwa-residents__list">
        {world.residents.map((resident) => (
          <li key={resident.id}>
            <button
              type="button"
              className={`hakoniwa-resident-row${
                resident.id === selectedResidentId ? " is-selected" : ""
              }`}
              aria-pressed={resident.id === selectedResidentId}
              onClick={() =>
                selectResident(
                  resident.id === selectedResidentId ? null : resident.id,
                )
              }
            >
              {resident.display_avatar_url ? (
                <HakoniwaPortrait
                  src={hakoniwaMediaUrl(resident.display_avatar_url)}
                  alt=""
                  className="hakoniwa-resident-row__face"
                />
              ) : (
                <span className="hakoniwa-resident-row__face hakoniwa-resident-row__face--empty">
                  {Array.from(resident.name)[0] ?? "?"}
                </span>
              )}
              <span className="hakoniwa-resident-row__text">
                <strong>{resident.name}</strong>
                <span>
                  {t(`hakoniwa.gender.${resident.gender}`)}・
                  {t(
                    `hakoniwa.residents.moodLabels.${moodLevel(resident.mood)}`,
                  )}
                </span>
              </span>
              <span className="hakoniwa-badge">
                {t(`hakoniwa.source.${resident.source}`)}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {(missing.length > 0 || avatarBatch) && (
        <div className="hakoniwa-residents__batch">
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || avatarBatch !== null}
            onClick={() => setConfirmAvatars(true)}
          >
            {avatarBatch ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.residents.batchProgress", {
                  done: avatarBatch.done,
                  total: avatarBatch.total,
                })}
              </>
            ) : (
              t("hakoniwa.residents.batchGenerate", { count: missing.length })
            )}
          </button>
          <p className="hakoniwa-note">{t("hakoniwa.residents.batchNote")}</p>
        </div>
      )}

      <div className="hakoniwa-residents__add">
        <button
          type="button"
          className="hakoniwa-button"
          onClick={() => setEditing("new")}
          disabled={full || busy !== null}
        >
          {t("hakoniwa.residents.addCustom")}
        </button>
        <HakoniwaCharacterAdder
          excludeIds={world.residents
            .map((resident) => resident.character_preset_id)
            .filter((id): id is string => Boolean(id))}
          onAdd={(picked) =>
            void addCharacterResident({
              character_preset_id: picked.character_preset_id,
              gender: picked.gender,
            })
          }
          disabled={full || busy !== null}
        />
      </div>

      <ConfirmDialog
        open={confirmAvatars}
        title={t("hakoniwa.residents.batchConfirmTitle")}
        confirmLabel={t("hakoniwa.residents.batchConfirm", {
          count: missing.length,
        })}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmAvatars(false)}
        onConfirm={() => {
          setConfirmAvatars(false);
          generateMissingAvatars();
        }}
      >
        <p>
          {t("hakoniwa.residents.batchConfirmBody", {
            names: missing
              .map((resident) => resident.name)
              .join(t("hakoniwa.residents.nameSeparator")),
            count: missing.length,
          })}
        </p>
      </ConfirmDialog>

      {editing && (
        <HakoniwaResidentModal
          resident={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
