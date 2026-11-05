/**
 * NovelAI の生成設定の欄。通常プレイの右パネルとサロンの接客画面(⚙)で共有する。
 * どちらも SettingsContext の同じ値を編集する。
 */

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { isEconomyImageModel } from "../../../constants/novelaiImageModels";
import { useSettings } from "../../../contexts/SettingsContext";
import { useInsertAtCaret } from "../../../hooks/useInsertAtCaret";
import {
  FavoritePromptInsertButton,
  FavoritePromptSaveButton,
} from "../../favoritePrompts/FavoritePromptButtons";
import { NovelaiUsageBar } from "../../NovelaiUsageBar";
import "../RightPanel.css";

/** 直接プロンプト・ネガティブプロンプト・i2i 強度・ノイズ */
export function NovelaiPromptFields() {
  const { t } = useTranslation();
  const {
    state: settingsState,
    setInpaintSettings,
    effectiveNovelaiImageModel,
  } = useSettings();
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const negativeRef = useRef<HTMLTextAreaElement>(null);
  const insertIntoPrompt = useInsertAtCaret(
    promptRef,
    settingsState.inpaintSettings.promptOverride,
    (promptOverride) => setInpaintSettings({ promptOverride }),
  );
  const insertIntoNegative = useInsertAtCaret(
    negativeRef,
    settingsState.inpaintSettings.negativePrompt,
    (negativePrompt) => setInpaintSettings({ negativePrompt }),
  );

  return (
    <>
      {/* T014: 直接プロンプト */}
      <div className="right-panel__form-group">
        <div className="right-panel__label-row">
          <label className="right-panel__label">
            {t("rightPanel.directPrompt")}
          </label>
          <span className="favorite-prompt-actions">
            <FavoritePromptInsertButton onInsert={insertIntoPrompt} />
            <FavoritePromptSaveButton
              text={settingsState.inpaintSettings.promptOverride}
            />
          </span>
        </div>
        <textarea
          ref={promptRef}
          className="right-panel__textarea"
          value={settingsState.inpaintSettings.promptOverride}
          onChange={(e) =>
            setInpaintSettings({ promptOverride: e.target.value })
          }
          placeholder={t("rightPanel.directPromptPlaceholder")}
          rows={3}
        />
        <small className="right-panel__hint">
          {t("rightPanel.directPromptHint")}
        </small>
      </div>

      {/* T015: ネガティブプロンプト */}
      <div className="right-panel__form-group">
        <div className="right-panel__label-row">
          <label className="right-panel__label">
            {t("rightPanel.negativePrompt")}
          </label>
          <span className="favorite-prompt-actions">
            <FavoritePromptInsertButton onInsert={insertIntoNegative} />
            <FavoritePromptSaveButton
              text={settingsState.inpaintSettings.negativePrompt}
            />
          </span>
        </div>
        <textarea
          ref={negativeRef}
          className="right-panel__textarea"
          value={settingsState.inpaintSettings.negativePrompt}
          onChange={(e) =>
            setInpaintSettings({ negativePrompt: e.target.value })
          }
          placeholder={t("rightPanel.negativePromptPlaceholder")}
          rows={2}
        />
        <small className="right-panel__hint">
          {isEconomyImageModel(effectiveNovelaiImageModel)
            ? t("rightPanel.negativePromptEconomyHint")
            : t("rightPanel.negativePromptHint")}
        </small>
      </div>

      {/* T016: i2i強度 */}
      <div className="right-panel__form-group">
        <label className="right-panel__label">
          i2i強度: {settingsState.inpaintSettings.i2iStrength.toFixed(2)}
        </label>
        <input
          type="range"
          className="right-panel__slider"
          min={0.05}
          max={0.99}
          step={0.01}
          value={settingsState.inpaintSettings.i2iStrength}
          onChange={(e) =>
            setInpaintSettings({ i2iStrength: parseFloat(e.target.value) })
          }
        />
        <small className="right-panel__hint">
          {t("rightPanel.i2iStrengthHint")}
        </small>
      </div>

      {/* T017: ノイズ */}
      <div className="right-panel__form-group">
        <label className="right-panel__label">
          {t("rightPanel.inpaintNoiseLabel")}:{" "}
          {settingsState.inpaintSettings.inpaintNoise.toFixed(2)}
        </label>
        <input
          type="range"
          className="right-panel__slider"
          min={0.0}
          max={0.5}
          step={0.01}
          value={settingsState.inpaintSettings.inpaintNoise}
          onChange={(e) =>
            setInpaintSettings({ inpaintNoise: parseFloat(e.target.value) })
          }
        />
        <small className="right-panel__hint">
          {t("rightPanel.inpaintNoiseHint")}
        </small>
      </div>
    </>
  );
}

/** NovelAI のテキストモデル(Opus のみ。それ以外のプランでは何も描かない) */
export function NovelaiTextModelField() {
  const { t } = useTranslation();
  const { state: settingsState, setNovelaiTextModel } = useSettings();
  if (settingsState.novelaiTier !== 3) return null;

  return (
    <div className="right-panel__form-group">
      <label className="right-panel__label">
        {t("settings.novelaiTextModel", "NovelAI Text Model")}
        <span
          className="feature-chip-experimental"
          data-feature-version="v0.5.0"
          style={{ marginLeft: "0.5rem" }}
        >
          Experimental
        </span>
      </label>
      <select
        className="right-panel__select"
        value={settingsState.novelaiTextModel}
        onChange={(e) => setNovelaiTextModel(e.target.value)}
      >
        <option value="glm-4-6">
          {t("settings.novelaiTextModelGlm", "GLM 4.6 (Default)")}
        </option>
        <option value="xialong-v1">
          {t("settings.novelaiTextModelXialong", "Xialong v1 (Experimental)")}
        </option>
      </select>
      <small className="right-panel__hint">
        {t(
          "settings.novelaiTextModelDesc",
          "Select the NovelAI model for text generation.",
        )}
      </small>
    </div>
  );
}

/** NovelAI の画像生成モデル(NSFW / 非NSFW)と V5 の利用量 */
export function NovelaiImageModelFields() {
  const { t } = useTranslation();
  const {
    state: settingsState,
    setNovelaiImageModel,
    setNovelaiCuratedImageModel,
    isNovelaiV5Active,
  } = useSettings();

  return (
    <>
      <div className="right-panel__form-group">
        <label className="right-panel__label">
          {t("settings.novelaiImageModelNsfw")}
          <span
            className="feature-chip-experimental"
            data-feature-version="v0.7.0"
            style={{ marginLeft: "0.5rem" }}
          >
            Experimental
          </span>
        </label>
        <select
          className="right-panel__select"
          value={settingsState.novelaiImageModel}
          onChange={(e) => setNovelaiImageModel(e.target.value)}
        >
          <option value="nai-diffusion-4-5-full">
            {t("settings.novelaiImageModelV45Full")}
          </option>
          <option value="nai-diffusion-5-full">
            {t("settings.novelaiImageModelV5Full")}
          </option>
          <option value="nai-diffusion-5-full-medium">
            {t("settings.novelaiImageModelV5FullEconomy")}
          </option>
        </select>
      </div>

      <div className="right-panel__form-group">
        <label className="right-panel__label">
          {t("settings.novelaiImageModelSfw")}
          <span
            className="feature-chip-experimental"
            data-feature-version="v0.7.0"
            style={{ marginLeft: "0.5rem" }}
          >
            Experimental
          </span>
        </label>
        <select
          className="right-panel__select"
          value={settingsState.novelaiCuratedImageModel}
          onChange={(e) => setNovelaiCuratedImageModel(e.target.value)}
        >
          <option value="nai-diffusion-4-5-curated">
            {t("settings.novelaiImageModelV45Curated")}
          </option>
          <option value="nai-diffusion-5-curated">
            {t("settings.novelaiImageModelV5Curated")}
          </option>
        </select>
        {isNovelaiV5Active && settingsState.anlasBalance?.usage && (
          <div className="right-panel__usage-bar">
            <NovelaiUsageBar usage={settingsState.anlasBalance.usage} compact />
          </div>
        )}
      </div>
    </>
  );
}
