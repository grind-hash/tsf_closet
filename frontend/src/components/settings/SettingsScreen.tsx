/**
 * SettingsScreen - 設定画面
 * 007-chat-interactive-ux
 */

import MainLayout from "../layout/MainLayout";
import { useSettings } from "../../contexts/SettingsContext";
import { useTranslation } from "react-i18next";
import SelfProfileEditor from "./SelfProfileEditor";
import MemorySettings from "./MemorySettings";
import SpeechSynthesisSettings from "./SpeechSynthesisSettings";
import "./SettingsScreen.css";

export default function SettingsScreen() {
  const { t } = useTranslation();
  const {
    state,
    setDifficulty,
    setBloomCalcMethod,
    setLanguage,
    setNsfwMode,
    setShowAchievementNotifications,
    setShowRealityAttributeNotification,
    setExperimentalEndingEnabled,
    setPlayMemoryEnabled,
    setEnableSurroundingsImage,
    setSurroundingsIncludePeople,
    setClothingColorConsistency,
    setFontFamily,
    setLinkChatToImage,
    setEnableMultiplePeople,
    setNovelaiTextModel,
    setHistoryLookbackCount,
    resetSettings,
  } = useSettings();

  const difficultyOptions = [
    {
      id: "easy",
      label: t("settings.easy"),
      description: t("settings.easyDesc"),
    },
    {
      id: "normal",
      label: t("settings.normal"),
      description: t("settings.normalDesc"),
    },
    {
      id: "hard",
      label: t("settings.hard"),
      description: t("settings.hardDesc"),
    },
  ] as const;

  const bloomCalcMethodOptions = [
    {
      id: "legacy",
      label: t("settings.bloomCalcLegacy"),
      description: t("settings.bloomCalcLegacyDesc"),
    },
    {
      id: "new",
      label: t("settings.bloomCalcNew"),
      description: t("settings.bloomCalcNewDesc"),
    },
  ] as const;

  const languageOptions = [
    { id: "ja", label: t("settings.ja"), description: t("settings.jaDesc") },
    {
      id: "en",
      label: t("settings.en"),
      description: t("settings.enDesc"),
    },
  ] as const;

  const fontOptions = [
    {
      id: "system",
      label: t("settings.fontSystem"),
      description: t("settings.fontSystemDesc"),
    },
    {
      id: "browser-default",
      label: t("settings.fontBrowserDefault"),
      description: t("settings.fontBrowserDefaultDesc"),
    },
    {
      id: "noto-sans-jp",
      label: "Noto Sans JP",
      description: t("settings.fontNotoSansJPDesc"),
    },
    {
      id: "biz-udgothic",
      label: "BIZ UDGothic",
      description: t("settings.fontBizUDGothicDesc"),
    },
    {
      id: "biz-udmincho",
      label: "BIZ UDMincho",
      description: t("settings.fontBizUDMinchoDesc"),
    },
    {
      id: "inter",
      label: "Inter",
      description: t("settings.fontInterDesc"),
    },
    {
      id: "roboto-mono",
      label: "Roboto Mono",
      description: t("settings.fontRobotoMonoDesc"),
    },
  ] as const;

  const handleReset = () => {
    if (confirm(t("settings.resetConfirm"))) {
      resetSettings();
    }
  };

  return (
    <MainLayout>
      <div className="settings-screen">
        <header className="settings-screen__header">
          <h1 className="settings-screen__title">{t("settings.title")}</h1>
        </header>

        <div className="settings-screen__content">
          {/* ゲーム設定 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.gameSection")}
            </h2>

            <div className="settings-screen__item">
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.difficulty")}
                </span>
              </div>
              <div className="settings-screen__radio-group">
                {difficultyOptions.map((option) => (
                  <label key={option.id} className="settings-screen__radio">
                    <input
                      type="radio"
                      name="difficulty"
                      value={option.id}
                      checked={state.difficulty === option.id}
                      onChange={() => setDifficulty(option.id)}
                    />
                    <div className="settings-screen__radio-content">
                      <span className="settings-screen__radio-label">
                        {option.label}
                      </span>
                      <span className="settings-screen__radio-desc">
                        {option.description}
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="settings-screen__item">
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.bloomCalcMethod")}
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.bloomCalcMethodDesc")}
                </span>
              </div>
              <div className="settings-screen__radio-group">
                {bloomCalcMethodOptions.map((option) => (
                  <label key={option.id} className="settings-screen__radio">
                    <input
                      type="radio"
                      name="bloomCalcMethod"
                      value={option.id}
                      checked={state.bloomCalcMethod === option.id}
                      onChange={() => setBloomCalcMethod(option.id)}
                    />
                    <div className="settings-screen__radio-content">
                      <span className="settings-screen__radio-label">
                        {option.label}
                      </span>
                      <span className="settings-screen__radio-desc">
                        {option.description}
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.nsfwMode")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.nsfwDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.nsfwMode}
                  onChange={(e) => setNsfwMode(e.target.checked)}
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            <div className="settings-screen__item">
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.language")}
                </span>
              </div>
              <div className="settings-screen__radio-group">
                {languageOptions.map((option) => (
                  <label key={option.id} className="settings-screen__radio">
                    <input
                      type="radio"
                      name="language"
                      value={option.id}
                      checked={state.language === option.id}
                      onChange={() => setLanguage(option.id)}
                    />
                    <div className="settings-screen__radio-content">
                      <span className="settings-screen__radio-label">
                        {option.label}
                      </span>
                      <span className="settings-screen__radio-desc">
                        {option.description}
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </section>

          {/* 表示設定 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.displaySection")}
            </h2>

            <div className="settings-screen__item">
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.fontFamily")}
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.fontFamilyDesc")}
                </span>
              </div>
              <div className="settings-screen__select-wrapper">
                <select
                  className="settings-screen__select"
                  value={state.fontFamily}
                  onChange={(e) => setFontFamily(e.target.value)}
                >
                  {fontOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <p className="settings-screen__font-preview">
                {t("settings.fontPreview")}
              </p>
            </div>
          </section>

          {/* 画像生成設定 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.imageSection")}
            </h2>

            <div className="settings-screen__item">
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.imageProvider")}
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.providerReadonly")}
                </span>
              </div>
              <div className="settings-screen__readonly-value">
                {state.imageProvider === "selfhost" && t("settings.selfhost")}
                {state.imageProvider === "openrouter" &&
                  t("settings.openrouter")}
                {state.imageProvider === "novelai" && t("settings.novelai")}
              </div>
            </div>
          </section>

          {/* 自分自身モード キャラ設定 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.selfProfile.sectionTitle")}
            </h2>
            <SelfProfileEditor />
          </section>

          {/* メモリ機能 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.memory.sectionTitle")}
              <span
                className="feature-chip-new"
                data-feature-version="v0.6.0"
                style={{ marginLeft: "0.5rem" }}
              >
                New
              </span>
            </h2>
            <MemorySettings />
          </section>

          {/* 音声合成 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.speech.sectionTitle")}
              <span
                className="feature-chip-experimental"
                data-feature-version="v0.6.0"
                style={{ marginLeft: "0.5rem" }}
              >
                Experimental
              </span>
            </h2>
            <SpeechSynthesisSettings />
          </section>

          {/* 通知設定 */}
          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.notifySection")}
            </h2>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.achievementNotify")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.achievementNotifyDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.showAchievementNotifications}
                  onChange={(e) =>
                    setShowAchievementNotifications(e.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.realityAttributeNotify")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.realityAttributeNotifyDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.showRealityAttributeNotification}
                  onChange={(e) =>
                    setShowRealityAttributeNotification(e.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>
          </section>

          <section className="settings-screen__section">
            <h2 className="settings-screen__section-title">
              {t("settings.experimentalSection")}
            </h2>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.experimentalEnding")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalEndingDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.experimentalEndingEnabled}
                  onChange={(e) =>
                    setExperimentalEndingEnabled(e.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.experimentalSurroundings")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalSurroundingsDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.enableSurroundingsImage}
                  onChange={(e) => setEnableSurroundingsImage(e.target.checked)}
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            {state.enableSurroundingsImage && (
              <div className="settings-screen__item">
                <label className="settings-screen__toggle">
                  <div className="settings-screen__toggle-info">
                    <span className="settings-screen__item-label">
                      {t("settings.experimentalSurroundingsPeople")}
                    </span>
                    <span className="settings-screen__item-desc">
                      {t("settings.experimentalSurroundingsPeopleDesc")}
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={state.surroundingsIncludePeople}
                    onChange={(e) =>
                      setSurroundingsIncludePeople(e.target.checked)
                    }
                    className="settings-screen__toggle-input"
                  />
                  <span className="settings-screen__toggle-switch" />
                </label>
              </div>
            )}

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.experimentalClothingColor")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalClothingColorDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.clothingColorConsistency}
                  onChange={(e) =>
                    setClothingColorConsistency(e.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.historyLookbackCount")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.historyLookbackCountDesc")}
                  </span>
                </div>
                <input
                  type="number"
                  min={5}
                  max={20}
                  step={1}
                  value={state.historyLookbackCount}
                  onChange={(e) => {
                    const v = Number.parseInt(e.target.value, 10);
                    if (!Number.isNaN(v)) {
                      setHistoryLookbackCount(v);
                    }
                  }}
                  className="settings-screen__number-input"
                  aria-label={t("settings.historyLookbackCount")}
                />
              </label>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.enableMultiplePeople")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.enableMultiplePeopleDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.enableMultiplePeople}
                  onChange={(e) => setEnableMultiplePeople(e.target.checked)}
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            {state.imageProvider === "novelai" && state.novelaiTier === 3 && (
              <div className="settings-screen__item">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.novelaiTextModel")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.novelaiTextModelDesc")}
                  </span>
                </div>
                <div className="settings-screen__select-wrapper">
                  <select
                    className="settings-screen__select"
                    value={state.novelaiTextModel}
                    onChange={(e) => setNovelaiTextModel(e.target.value)}
                  >
                    <option value="glm-4-6">
                      {t("settings.novelaiTextModelGlm")}
                    </option>
                    <option value="xialong-v1">
                      {t("settings.novelaiTextModelXialong")}
                    </option>
                  </select>
                </div>
              </div>
            )}

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.linkChatToImage")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.linkChatToImageDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.linkChatToImage}
                  onChange={(e) => setLinkChatToImage(e.target.checked)}
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.experimentalPlayMemory")}
                    <span
                      className="feature-chip-new"
                      data-feature-version="v0.6.0"
                      style={{ marginLeft: "0.5rem" }}
                    >
                      New
                    </span>
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalPlayMemoryDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.playMemoryEnabled}
                  onChange={(event) =>
                    setPlayMemoryEnabled(event.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
              {state.playMemoryEnabled && (
                <p className="settings-screen__play-memory-warning">
                  {t("settings.experimentalPlayMemoryWarning")}
                </p>
              )}
            </div>
          </section>

          {/* リセット */}
          <section className="settings-screen__section settings-screen__section--danger">
            <h2 className="settings-screen__section-title">
              {t("settings.dataSection")}
            </h2>

            <div className="settings-screen__item">
              <button
                type="button"
                className="settings-screen__reset-btn"
                onClick={handleReset}
              >
                {t("settings.reset")}
              </button>
              <p className="settings-screen__item-desc">
                {t("settings.resetDesc")}
              </p>
            </div>
          </section>
        </div>
      </div>
    </MainLayout>
  );
}
