import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  ADVENTURE_IMAGE_MODEL_CHOICES,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import ConfirmDialog from "../ui/ConfirmDialog";

const DEFAULT_MODEL = "default";

function modelLabel(model: string): string {
  return (
    ADVENTURE_IMAGE_MODEL_CHOICES.find((choice) => choice.value === model)
      ?.label ?? model
  );
}

/** 設定タブ: 姿を生成する画像モデル(透過のしかたの説明つき)と、世界の削除 */
export default function HakoniwaSettingsTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const { world, busy, setImageModel, deleteWorld } = useHakoniwa();
  const modelId = useId();
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!world) return null;
  const usage = settingsState.anlasBalance?.usage;
  const showUsage =
    settingsState.imageProvider === "novelai" &&
    isV5ImageModel(world.image_model_effective) &&
    usage != null;

  return (
    <div className="hakoniwa-settings">
      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-field" htmlFor={modelId}>
          <span>{t("hakoniwa.settings.imageModelHeading")}</span>
          <select
            id={modelId}
            value={world.image_model}
            disabled={busy !== null}
            onChange={(event) => void setImageModel(event.target.value)}
          >
            <option value={DEFAULT_MODEL}>
              {t("hakoniwa.settings.imageModelDefault", {
                model: modelLabel(world.image_model_default),
              })}
            </option>
            {world.image_model_options.map((model) => (
              <option key={model} value={model}>
                {modelLabel(model)}
              </option>
            ))}
          </select>
        </label>
        <p className="hakoniwa-note">
          {world.transparency === "native"
            ? t("hakoniwa.settings.transparencyNative")
            : t("hakoniwa.settings.transparencyRemoval")}
        </p>
        <p className="hakoniwa-note">{t("hakoniwa.settings.providerNote")}</p>
      </section>

      {showUsage && usage && (
        <section className="hakoniwa-settings__section">
          <strong>{t("hakoniwa.settings.usageHeading")}</strong>
          <NovelaiUsageBar usage={usage} compact />
        </section>
      )}

      <section className="hakoniwa-settings__section">
        <strong>{t("hakoniwa.settings.deleteHeading")}</strong>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => setConfirmDelete(true)}
          disabled={busy !== null}
        >
          {t("hakoniwa.settings.deleteWorld")}
        </button>
      </section>

      <ConfirmDialog
        open={confirmDelete}
        title={t("hakoniwa.hub.deleteTitle")}
        confirmLabel={t("hakoniwa.hub.deleteConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        busy={busy === "delete"}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          void deleteWorld(world.id).then(() => {
            setConfirmDelete(false);
            navigate(ROUTES.HAKONIWA);
          });
        }}
      >
        <p>{t("hakoniwa.hub.deleteBody", { name: world.name })}</p>
      </ConfirmDialog>
    </div>
  );
}
