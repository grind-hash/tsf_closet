/**
 * SettingsScreen - 設定画面
 * 007-chat-interactive-ux
 */

import MainLayout from "../layout/MainLayout";
import { useSettings } from "../../contexts/SettingsContext";
import { useTranslation } from "react-i18next";
import SelfProfileEditor from "./SelfProfileEditor";
import "./SettingsScreen.css";

export default function SettingsScreen() {
  const { t } = useTranslation();
  const {
    state,
    setDifficulty,
    setLanguage,
    setNsfwMode,
    setShowAchievementNotifications,
    setExperimentalEndingEnabled,
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

  const languageOptions = [
    { id: "ja", label: t("settings.ja"), description: t("settings.jaDesc") },
    {
      id: "en",
      label: t("settings.en"),
      description: t("settings.enDesc"),
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
