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
import {
  LookControls,
  type LookRequest,
  lookRequest,
} from "./HakoniwaRulesTab";
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
    lookTarget,
    lookProgress,
    generateLook,
    applyMemoLook,
    playbackQueue,
  } = useHakoniwa();
  const [confirmMemoLook, setConfirmMemoLook] = useState<LookRequest | null>(
    null,
  );
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
        {savedMemo && (
          <MemoLookStatus
            planning={
              lookTarget === "memo" && lookProgress === null && busy === "look"
            }
            locked={busy !== null || playbackQueue.length > 0}
            onCheck={() => void applyMemoLook(world.id)}
            onRequest={(request) => setConfirmMemoLook(request)}
          />
        )}
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
        open={confirmMemoLook !== null}
        title={t("hakoniwa.rules.lookConfirmTitle")}
        confirmLabel={t("hakoniwa.rules.lookConfirm", {
          count: confirmMemoLook?.count ?? 0,
        })}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmMemoLook(null)}
        onConfirm={() => {
          if (confirmMemoLook) {
            generateLook(confirmMemoLook.target, confirmMemoLook.regenerate);
          }
          setConfirmMemoLook(null);
        }}
      >
        <p>
          {t(
            confirmMemoLook?.regenerate
              ? "hakoniwa.rules.lookConfirmRedraw"
              : "hakoniwa.rules.lookConfirmBody",
            {
              label: confirmMemoLook?.label ?? "",
              count: confirmMemoLook?.count ?? 0,
            },
          )}
        </p>
      </ConfirmDialog>
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

/**
 * 世界のメモが住民全員に与える姿の状態。姿に関わるかを確かめている間はスピナー、
 * 関わるなら見た目のタグと生成状況、関わらないならその旨を出す
 */
function MemoLookStatus({
  planning,
  locked,
  onCheck,
  onRequest,
}: {
  planning: boolean;
  locked: boolean;
  onCheck: () => void;
  onRequest: (request: LookRequest) => void;
}) {
  const { t } = useTranslation();
  const { world } = useHakoniwa();
  if (!world) return null;
  const memoLook = world.memo_look ?? null;
  if (planning) {
    return (
      <div className="hakoniwa-progress" role="status">
        <span className="hakoniwa-spinner" aria-hidden />
        {t("hakoniwa.settings.memoLookPlanning")}
      </div>
    );
  }
  if (memoLook) {
    const label = t("hakoniwa.settings.memoLookLabel");
    return (
      <div className="hakoniwa-settings__memo-look">
        <strong>{t("hakoniwa.settings.memoLookHeading")}</strong>
        <p className="hakoniwa-note">
          {memoLook.tags
            ? t("hakoniwa.settings.memoLookTags", { tags: memoLook.tags })
            : t("hakoniwa.settings.memoLookBodyOnly")}
          {memoLook.body_gender &&
            ` ${t("hakoniwa.settings.memoLookBody", {
              gender: t(`hakoniwa.gender.${memoLook.body_gender}`),
            })}`}
        </p>
        <LookControls
          status={memoLook}
          target="memo"
          disabled={locked}
          onRequest={() => onRequest(lookRequest("memo", label, memoLook))}
        />
      </div>
    );
  }
  if (world.memo_look_planned) {
    return (
      <p className="hakoniwa-note">{t("hakoniwa.settings.memoLookNone")}</p>
    );
  }
  return (
    <div className="hakoniwa-settings__memo-look">
      <p className="hakoniwa-note">
        {t("hakoniwa.settings.memoLookUnchecked")}
      </p>
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--ghost"
        onClick={onCheck}
        disabled={locked}
      >
        {t("hakoniwa.settings.memoLookCheck")}
      </button>
    </div>
  );
}
