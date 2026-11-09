import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { HakoniwaTheme } from "../../apis/hakoniwa";
import {
  ADVENTURE_IMAGE_MODEL_CHOICES,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaThemePicker, { normalizeTheme } from "./HakoniwaThemePicker";

const DEFAULT_MODEL = "default";
const MEMO_MAX = 1000;

function modelLabel(model: string): string {
  return (
    ADVENTURE_IMAGE_MODEL_CHOICES.find((choice) => choice.value === model)
      ?.label ?? model
  );
}

/** 設定タブ: 姿を生成する画像モデル(透過のしかたの説明つき)、世界の違和感、世界の削除 */
export default function HakoniwaSettingsTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const {
    world,
    busy,
    setImageModel,
    setDissonanceEnabled,
    setWorldMemo,
    setExperimentTheme,
    deleteWorld,
  } = useHakoniwa();
  const modelId = useId();
  const dissonanceId = useId();
  const memoId = useId();
  const savedMemo = world?.world_memo ?? "";
  const [memo, setMemo] = useState(savedMemo);

  const savedTheme = world?.experiment_theme ?? null;
  const savedThemeKey = JSON.stringify(savedTheme);
  const [themeDraft, setThemeDraft] = useState<HakoniwaTheme | null>(
    savedTheme,
  );

  // 別の世界を開いたり保存したりしたら、欄を保存済みの内容にそろえる
  useEffect(() => {
    setMemo(savedMemo);
  }, [savedMemo]);
  useEffect(() => {
    setThemeDraft(JSON.parse(savedThemeKey) as HakoniwaTheme | null);
  }, [savedThemeKey]);
  const themeChanged =
    JSON.stringify(normalizeTheme(themeDraft)) !== savedThemeKey;
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

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-field" htmlFor={memoId}>
          <span>{t("hakoniwa.settings.memoHeading")}</span>
          <textarea
            id={memoId}
            rows={5}
            value={memo}
            maxLength={MEMO_MAX}
            placeholder={t("hakoniwa.settings.memoPlaceholder")}
            onChange={(event) => setMemo(event.target.value)}
          />
        </label>
        <div className="hakoniwa-settings__memo-actions">
          <span className="hakoniwa-note">
            {t("hakoniwa.settings.memoCount", {
              count: memo.length,
              max: MEMO_MAX,
            })}
          </span>
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || memo.trim() === savedMemo}
            onClick={() => void setWorldMemo(memo.trim())}
          >
            {t("hakoniwa.settings.memoSave")}
          </button>
        </div>
        <p className="hakoniwa-note">{t("hakoniwa.settings.memoNote")}</p>
      </section>

      <section className="hakoniwa-settings__section">
        <HakoniwaThemePicker
          key={savedThemeKey}
          value={savedTheme}
          onChange={setThemeDraft}
          disabled={busy !== null}
        />
        <div className="hakoniwa-settings__memo-actions">
          <span />
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || !themeChanged}
            onClick={() => void setExperimentTheme(normalizeTheme(themeDraft))}
          >
            {t("hakoniwa.theme.save")}
          </button>
        </div>
      </section>

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-toggle" htmlFor={dissonanceId}>
          <span>{t("hakoniwa.settings.dissonanceToggle")}</span>
          <input
            id={dissonanceId}
            type="checkbox"
            className="hakoniwa-toggle__input"
            checked={world.dissonance.enabled}
            disabled={busy !== null}
            onChange={(event) =>
              void setDissonanceEnabled(event.target.checked)
            }
          />
          <span className="hakoniwa-toggle__switch" aria-hidden />
        </label>
        <p className="hakoniwa-note">{t("hakoniwa.settings.dissonanceNote")}</p>
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
