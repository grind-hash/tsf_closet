import { useCallback, useState } from "react";
/**
 * SettingsScreen - 設定画面
 * 007-chat-interactive-ux
 */

import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import type { HistoryLookbackTarget } from "../../utils/historyLookback";
import MainLayout from "../layout/MainLayout";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import AvatarModelSettings, {
  type AvatarModelSummary,
} from "./AvatarModelSettings";
import MemorySettings from "./MemorySettings";
import SelfProfileEditor from "./SelfProfileEditor";
import SpeechSynthesisSettings from "./SpeechSynthesisSettings";
import "./SettingsScreen.css";

const HISTORY_LOOKBACK_TARGETS: Array<{
  value: HistoryLookbackTarget;
  labelKey: string;
}> = [
  { value: "action", labelKey: "settings.historyLookbackTargetAction" },
  {
    value: "conversation",
    labelKey: "settings.historyLookbackTargetConversation",
  },
  { value: "dress_up", labelKey: "settings.historyLookbackTargetDressUp" },
  {
    value: "reality_alter",
    labelKey: "settings.historyLookbackTargetRealityAlter",
  },
];

/** 3Dモデルセクションの開閉。モデルが増えると長くなるため既定は閉じる */
const SETTINGS_AVATAR_SECTION_OPEN_KEY = "settings_avatar_section_open";

function readAvatarSectionOpen(): boolean {
  try {
    return (
      window.localStorage.getItem(SETTINGS_AVATAR_SECTION_OPEN_KEY) === "1"
    );
  } catch {
    return false;
  }
}

export default function SettingsScreen() {
  const { t } = useTranslation();
  const [avatarSectionOpen, setAvatarSectionOpen] = useState(
    readAvatarSectionOpen,
  );
  const [avatarSummary, setAvatarSummary] = useState<AvatarModelSummary | null>(
    null,
  );
  const toggleAvatarSection = useCallback(() => {
    setAvatarSectionOpen((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(
          SETTINGS_AVATAR_SECTION_OPEN_KEY,
          next ? "1" : "0",
        );
      } catch {
        // 保存できなくても開閉は続行する
      }
      return next;
    });
  }, []);
  const {
    state,
    setDifficulty,
    setBloomCalcMethod,
    setFeelingMode,
    setGenderCongruenceLlmEnabled,
    setLanguage,
    setNsfwMode,
    setShowAchievementNotifications,
    setShowRealityAttributeNotification,
    setExperimentalEndingEnabled,
    setExperimentalAdventureEnabled,
    setExperimentalPromptExpanderEnabled,
    setAdventureEnableCompositeScene,
    setPlayMemoryEnabled,
    setEnableSurroundingsImage,
    setSurroundingsIncludePeople,
    setClothingColorConsistency,
    setRespectClothingLayers,
    setFontFamily,
    setConfirmFavoriteRemove,
    setLinkChatToImage,
    setEnableMultiplePeople,
    setNovelaiTextModel,
    setNovelaiImageModel,
    setNovelaiCuratedImageModel,
    isNovelaiV5Active,
    setHistoryLookbackCount,
    setHistoryLookbackTarget,
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

  const feelingModeOptions = [
    {
      id: "legacy" as const,
      label: t("settings.feelingModeLegacy"),
      description: t("settings.feelingModeLegacyDesc"),
    },
    {
      id: "gender_aware" as const,
      label: t("settings.feelingModeGenderAware"),
      description: t("settings.feelingModeGenderAwareDesc"),
    },
  ];

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
              <div className="settings-screen__item-header">
                <span className="settings-screen__item-label">
                  {t("settings.feelingMode")}
                  <span
                    className="feature-chip-new"
                    data-feature-version="v0.7.0"
                  >
                    New
                  </span>
                  <span
                    className="feature-chip-experimental"
                    data-feature-version="v0.7.0"
                  >
                    Experimental
                  </span>
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.feelingModeDesc")}
                </span>
              </div>
              <div className="settings-screen__radio-group">
                {feelingModeOptions.map((option) => (
                  <label key={option.id} className="settings-screen__radio">
                    <input
                      type="radio"
                      name="feelingMode"
                      value={option.id}
                      checked={state.feelingMode === option.id}
                      onChange={() => setFeelingMode(option.id)}
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
              <label
                className="settings-screen__toggle"
                style={
                  state.feelingMode !== "gender_aware"
                    ? { opacity: 0.55 }
                    : undefined
                }
              >
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.genderCongruenceLlm")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.genderCongruenceLlmDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.genderCongruenceLlmEnabled}
                  disabled={state.feelingMode !== "gender_aware"}
                  onChange={(e) =>
                    setGenderCongruenceLlmEnabled(e.target.checked)
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

            <div className="settings-screen__item">
              <label className="settings-screen__toggle">
                <div className="settings-screen__toggle-info">
                  <span className="settings-screen__item-label">
                    {t("settings.confirmFavoriteRemove")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.confirmFavoriteRemoveDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.confirmFavoriteRemove}
                  onChange={(e) => setConfirmFavoriteRemove(e.target.checked)}
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
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

            {state.imageProvider === "novelai" && (
              <>
                <div className="settings-screen__item">
                  <div className="settings-screen__toggle-info">
                    <span className="settings-screen__item-label">
                      {t("settings.novelaiImageModelNsfw")}
                      <span
                        className="feature-chip-experimental"
                        data-feature-version="v0.7.0"
                        style={{ marginLeft: "0.5rem" }}
                      >
                        Experimental
                      </span>
                    </span>
                    <span className="settings-screen__item-desc">
                      {t("settings.novelaiImageModelNsfwDesc")}
                    </span>
                  </div>
                  <div className="settings-screen__select-wrapper">
                    <select
                      className="settings-screen__select"
                      value={state.novelaiImageModel}
                      onChange={(e) => setNovelaiImageModel(e.target.value)}
                    >
                      <option value="nai-diffusion-4-5-full">
                        {t("settings.novelaiImageModelV45Full")}
                      </option>
                      <option value="nai-diffusion-5-full">
                        {t("settings.novelaiImageModelV5Full")}
                      </option>
                    </select>
                  </div>
                </div>

                <div className="settings-screen__item">
                  <div className="settings-screen__toggle-info">
                    <span className="settings-screen__item-label">
                      {t("settings.novelaiImageModelSfw")}
                      <span
                        className="feature-chip-experimental"
                        data-feature-version="v0.7.0"
                        style={{ marginLeft: "0.5rem" }}
                      >
                        Experimental
                      </span>
                    </span>
                    <span className="settings-screen__item-desc">
                      {t("settings.novelaiImageModelSfwDesc")}
                    </span>
                  </div>
                  <div className="settings-screen__select-wrapper">
                    <select
                      className="settings-screen__select"
                      value={state.novelaiCuratedImageModel}
                      onChange={(e) =>
                        setNovelaiCuratedImageModel(e.target.value)
                      }
                    >
                      <option value="nai-diffusion-4-5-curated">
                        {t("settings.novelaiImageModelV45Curated")}
                      </option>
                      <option value="nai-diffusion-5-curated">
                        {t("settings.novelaiImageModelV5Curated")}
                      </option>
                    </select>
                  </div>
                </div>

                {isNovelaiV5Active && state.anlasBalance?.usage && (
                  <div className="settings-screen__item">
                    <div className="settings-screen__toggle-info">
                      <span className="settings-screen__item-label">
                        {t("settings.novelaiUsageTitle")}
                      </span>
                      <span className="settings-screen__item-desc">
                        {t("settings.novelaiUsageDesc")}
                      </span>
                    </div>
                    <NovelaiUsageBar usage={state.anlasBalance.usage} />
                  </div>
                )}
              </>
            )}
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
                    {t("settings.experimentalAdventure")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalAdventureDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.experimentalAdventureEnabled}
                  onChange={(e) =>
                    setExperimentalAdventureEnabled(e.target.checked)
                  }
                  className="settings-screen__toggle-input"
                />
                <span className="settings-screen__toggle-switch" />
              </label>
            </div>

            {state.experimentalAdventureEnabled && (
              <div className="settings-screen__item">
                <label className="settings-screen__toggle">
                  <div className="settings-screen__toggle-info">
                    <span className="settings-screen__item-label">
                      {t("settings.adventureEnableCompositeScene")}
                    </span>
                    <span className="settings-screen__item-desc">
                      {t("settings.adventureEnableCompositeSceneDesc")}
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={state.adventureEnableCompositeScene}
                    onChange={(e) =>
                      setAdventureEnableCompositeScene(e.target.checked)
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
                    {t("settings.experimentalPromptExpander")}
                    <span
                      className="feature-chip-experimental"
                      data-feature-version="v0.8.0"
                      style={{ marginLeft: "0.5rem" }}
                    >
                      Experimental
                    </span>
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.experimentalPromptExpanderDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.experimentalPromptExpanderEnabled}
                  onChange={(e) =>
                    setExperimentalPromptExpanderEnabled(e.target.checked)
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
                    {t("settings.respectClothingLayers")}
                  </span>
                  <span className="settings-screen__item-desc">
                    {t("settings.respectClothingLayersDesc")}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={state.respectClothingLayers}
                  onChange={(e) => setRespectClothingLayers(e.target.checked)}
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
              <fieldset className="settings-screen__checkbox-fieldset">
                <legend className="settings-screen__item-label">
                  {t("settings.historyLookbackTargets")}
                </legend>
                <p className="settings-screen__item-desc">
                  {t("settings.historyLookbackTargetsDesc")}
                </p>
                <div className="settings-screen__checkbox-group">
                  {HISTORY_LOOKBACK_TARGETS.map((target) => (
                    <label
                      key={target.value}
                      className="settings-screen__checkbox"
                    >
                      <input
                        type="checkbox"
                        checked={state.historyLookbackTargets[target.value]}
                        onChange={(event) =>
                          setHistoryLookbackTarget(
                            target.value,
                            event.target.checked,
                          )
                        }
                      />
                      <span>{t(target.labelKey)}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
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

          {/* 3Dモデル(VRM): TSFシナリオの対面会話モードで使う。モデルが増えると
              一覧が長くなるため既定で閉じ、最下部(リセットの手前)に置く。閉じて
              いる間も中身は DOM に残し(hidden)、見出しの要約(件数)を出す */}
          <section
            className={`settings-screen__section settings-screen__section--collapsible${
              avatarSectionOpen ? " is-open" : " is-collapsed"
            }`}
          >
            <h2 className="settings-screen__section-title">
              <button
                type="button"
                className="settings-screen__section-toggle"
                aria-expanded={avatarSectionOpen}
                aria-controls="settings-avatar-section"
                data-testid="settings-avatar-toggle"
                onClick={toggleAvatarSection}
              >
                <span className="settings-screen__section-chevron" aria-hidden>
                  ▾
                </span>
                {t("settings.avatar.sectionTitle")}
                <span
                  className="feature-chip-experimental"
                  data-feature-version="v0.7.0"
                  style={{ marginLeft: "0.5rem" }}
                >
                  Experimental
                </span>
                {avatarSummary !== null && (
                  <span className="settings-screen__section-summary">
                    {avatarSummary.total === 0
                      ? t("settings.avatar.summaryEmpty")
                      : t("settings.avatar.summary", {
                          total: avatarSummary.total,
                          characters: avatarSummary.characters,
                        })}
                  </span>
                )}
              </button>
            </h2>
            <div id="settings-avatar-section" hidden={!avatarSectionOpen}>
              <AvatarModelSettings onSummaryChange={setAvatarSummary} />
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
