import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";
import { usePersistedState } from "../../hooks/usePersistedState";
/**
 * SettingsScreen - 設定画面
 * 007-chat-interactive-ux
 */

import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import type { TranslationKey } from "../../i18n";
import type { HistoryLookbackTarget } from "../../utils/historyLookback";
import MainLayout from "../layout/MainLayout";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import AvatarModelSettings, {
  type AvatarModelSummary,
} from "./AvatarModelSettings";
import CharacterChatRealWorldSettings from "./CharacterChatRealWorldSettings";
import Live2dSettings, { type Live2dCoreStatus } from "./Live2dSettings";
import MemorySettings from "./MemorySettings";
import SelfProfileEditor from "./SelfProfileEditor";
import SettingsChoice from "./SettingsChoice";
import SettingsNav from "./SettingsNav";
import {
  CollapsibleSettingsSection,
  SettingsItem,
  SettingsSection,
  SettingsViewContext,
  type SettingsViewState,
} from "./SettingsView";
import SpeechSynthesisSettings from "./SpeechSynthesisSettings";
import { useSearchHighlight } from "./settingsSearchHighlight";
import {
  buildSearchTexts,
  countMatchesByCategory,
  findMatchingItemIds,
  getItemIdsIn,
  getUnavailableItemIds,
  isSettingsCategoryId,
  type SettingsCategoryId,
  type SettingsItemId,
} from "./settingsSearchIndex";
import "./SettingsScreen.css";

const HISTORY_LOOKBACK_TARGETS: Array<{
  value: HistoryLookbackTarget;
  labelKey: TranslationKey;
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
/** Live2D セクションの開閉。導入済みなら普段は開く必要がないため既定は閉じる */
const SETTINGS_LIVE2D_SECTION_OPEN_KEY = "settings_live2d_section_open";
/** 新しい設定画面で選択中のカテゴリ。同じセッション内で開き直したときだけ復元する */
const SETTINGS_ACTIVE_CATEGORY_KEY = "settings_active_category";

export default function SettingsScreen() {
  const { t } = useTranslation();
  const [avatarSectionOpen, setAvatarSectionOpen] = usePersistedState<boolean>(
    SETTINGS_AVATAR_SECTION_OPEN_KEY,
    false,
    {
      serialize: (open) => (open ? "1" : "0"),
      deserialize: (raw) => raw === "1",
    },
  );
  const [avatarSummary, setAvatarSummary] = useState<AvatarModelSummary | null>(
    null,
  );
  const toggleAvatarSection = useCallback(() => {
    setAvatarSectionOpen((current) => !current);
  }, [setAvatarSectionOpen]);
  const [live2dSectionOpen, setLive2dSectionOpen] = usePersistedState<boolean>(
    SETTINGS_LIVE2D_SECTION_OPEN_KEY,
    false,
    {
      serialize: (open) => (open ? "1" : "0"),
      deserialize: (raw) => raw === "1",
    },
  );
  const [live2dStatus, setLive2dStatus] = useState<Live2dCoreStatus | null>(
    null,
  );
  const toggleLive2dSection = useCallback(() => {
    setLive2dSectionOpen((current) => !current);
  }, [setLive2dSectionOpen]);
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
    setAdventureEnabled,
    setExperimentalPromptExpanderEnabled,
    setExperimentalCharacterChatEnabled,
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
    setNewSettingsScreenEnabled,
    resetSettings,
  } = useSettings();

  const isV2 = state.newSettingsScreenEnabled;
  const [activeCategory, setActiveCategory] =
    usePersistedState<SettingsCategoryId>(
      SETTINGS_ACTIVE_CATEGORY_KEY,
      "game",
      {
        storage: "session",
        serialize: (category) => category,
        deserialize: (raw) => {
          if (!isSettingsCategoryId(raw)) {
            throw new Error(`Unknown settings category: ${raw}`);
          }
          return raw;
        },
      },
    );
  const [query, setQuery] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);

  const searchTexts = useMemo(() => buildSearchTexts((key) => t(key)), [t]);
  const unavailableIds = useMemo(
    () => getUnavailableItemIds({ state, isNovelaiV5Active }),
    [state, isNovelaiV5Active],
  );
  const matchedIds = useMemo(
    () =>
      isV2 ? findMatchingItemIds(query, searchTexts, unavailableIds) : null,
    [isV2, query, searchTexts, unavailableIds],
  );
  const matchCounts = useMemo(
    () => (matchedIds === null ? null : countMatchesByCategory(matchedIds)),
    [matchedIds],
  );
  const view = useMemo<SettingsViewState>(
    () => ({
      mode: isV2 ? "v2" : "classic",
      activeCategory,
      matchedIds,
      unavailableIds,
    }),
    [isV2, activeCategory, matchedIds, unavailableIds],
  );

  const handleQueryChange = useCallback((next: string) => {
    setQuery(next);
    contentRef.current?.scrollTo({ top: 0 });
  }, []);
  const handleSelectCategory = useCallback(
    (category: SettingsCategoryId) => {
      setQuery("");
      setActiveCategory(category);
      contentRef.current?.scrollTo({ top: 0 });
    },
    [setActiveCategory],
  );
  useSearchHighlight(contentRef, isV2 ? query : "");

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

  const itemNodes: Record<SettingsItemId, ReactNode> = {
    difficulty: (
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.difficulty")}
          </span>
        </div>
        <SettingsChoice
          name="difficulty"
          label={t("settings.difficulty")}
          value={state.difficulty}
          options={difficultyOptions}
          onChange={setDifficulty}
        />
      </div>
    ),
    bloomCalcMethod: (
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.bloomCalcMethod")}
          </span>
          <span className="settings-screen__item-desc">
            {t("settings.bloomCalcMethodDesc")}
          </span>
        </div>
        <SettingsChoice
          name="bloomCalcMethod"
          label={t("settings.bloomCalcMethod")}
          value={state.bloomCalcMethod}
          options={bloomCalcMethodOptions}
          onChange={setBloomCalcMethod}
        />
      </div>
    ),
    feelingMode: (
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.feelingMode")}
            <span className="feature-chip-new" data-feature-version="v0.7.0">
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
        <SettingsChoice
          name="feelingMode"
          label={t("settings.feelingMode")}
          value={state.feelingMode}
          options={feelingModeOptions}
          onChange={setFeelingMode}
        />
      </div>
    ),
    genderCongruenceLlm: (
      <div className="settings-screen__item">
        <label
          className="settings-screen__toggle"
          style={
            state.feelingMode !== "gender_aware" ? { opacity: 0.55 } : undefined
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
            onChange={(e) => setGenderCongruenceLlmEnabled(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    nsfwMode: (
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
    ),
    language: (
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.language")}
          </span>
        </div>
        <SettingsChoice
          name="language"
          label={t("settings.language")}
          value={state.language}
          options={languageOptions}
          onChange={setLanguage}
        />
      </div>
    ),
    adventureEnabled: (
      <div className="settings-screen__item">
        <label className="settings-screen__toggle">
          <div className="settings-screen__toggle-info">
            <span className="settings-screen__item-label">
              {t("settings.adventureEnabled")}
            </span>
            <span className="settings-screen__item-desc">
              {t("settings.adventureEnabledDesc")}
            </span>
          </div>
          <input
            type="checkbox"
            checked={state.adventureEnabled}
            onChange={(e) => setAdventureEnabled(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    adventureCompositeScene: (
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
            onChange={(e) => setAdventureEnableCompositeScene(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    fontFamily: (
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
    ),
    confirmFavoriteRemove: (
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
    ),
    imageProvider: (
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
          {state.imageProvider === "openrouter" && t("settings.openrouter")}
          {state.imageProvider === "novelai" && t("settings.novelai")}
        </div>
      </div>
    ),
    novelaiImageModelNsfw: (
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
            <option value="nai-diffusion-5-full-medium">
              {t("settings.novelaiImageModelV5FullEconomy")}
            </option>
          </select>
        </div>
      </div>
    ),
    novelaiImageModelSfw: (
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
            onChange={(e) => setNovelaiCuratedImageModel(e.target.value)}
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
    ),
    novelaiUsage: state.anlasBalance?.usage && (
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
    ),
    selfProfile: <SelfProfileEditor />,
    memory: <MemorySettings />,
    speech: <SpeechSynthesisSettings />,
    achievementNotify: (
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
            onChange={(e) => setShowAchievementNotifications(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    realityAttributeNotify: (
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
    ),
    promptExpander: (
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
    ),
    characterChat: (
      <div className="settings-screen__item">
        <label className="settings-screen__toggle">
          <div className="settings-screen__toggle-info">
            <span className="settings-screen__item-label">
              {t("settings.experimentalCharacterChat")}
              <span
                className="feature-chip-experimental"
                data-feature-version="v0.9.0"
                style={{ marginLeft: "0.5rem" }}
              >
                Experimental
              </span>
            </span>
            <span className="settings-screen__item-desc">
              {t("settings.experimentalCharacterChatDesc")}
            </span>
          </div>
          <input
            type="checkbox"
            checked={state.experimentalCharacterChatEnabled}
            onChange={(e) =>
              setExperimentalCharacterChatEnabled(e.target.checked)
            }
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    characterChatRealWorld: <CharacterChatRealWorldSettings />,
    surroundings: (
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
    ),
    surroundingsPeople: (
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
            onChange={(e) => setSurroundingsIncludePeople(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    clothingColor: (
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
            onChange={(e) => setClothingColorConsistency(e.target.checked)}
            className="settings-screen__toggle-input"
          />
          <span className="settings-screen__toggle-switch" />
        </label>
      </div>
    ),
    respectClothingLayers: (
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
    ),
    historyLookbackCount: (
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
    ),
    historyLookbackTargets: (
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
              <label key={target.value} className="settings-screen__checkbox">
                <input
                  type="checkbox"
                  checked={state.historyLookbackTargets[target.value]}
                  onChange={(event) =>
                    setHistoryLookbackTarget(target.value, event.target.checked)
                  }
                />
                <span>{t(target.labelKey)}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    ),
    enableMultiplePeople: (
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
    ),
    novelaiTextModel: (
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
            <option value="glm-4-6">{t("settings.novelaiTextModelGlm")}</option>
            <option value="xialong-v1">
              {t("settings.novelaiTextModelXialong")}
            </option>
          </select>
        </div>
      </div>
    ),
    linkChatToImage: (
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
    ),
    playMemory: (
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
            onChange={(event) => setPlayMemoryEnabled(event.target.checked)}
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
    ),
    avatarModels: <AvatarModelSettings onSummaryChange={setAvatarSummary} />,
    live2d: <Live2dSettings onStatusChange={setLive2dStatus} />,
    reset: (
      <div className="settings-screen__item">
        <button
          type="button"
          className="settings-screen__reset-btn"
          onClick={handleReset}
        >
          {t("settings.reset")}
        </button>
        <p className="settings-screen__item-desc">{t("settings.resetDesc")}</p>
      </div>
    ),
  };

  const layout = isV2 ? "v2" : "classic";
  const renderItems = (category: SettingsCategoryId) =>
    getItemIdsIn(category, layout).map((id) => (
      <SettingsItem key={id} id={id}>
        {itemNodes[id]}
      </SettingsItem>
    ));

  const sections = (
    <>
      {/* ゲーム設定 */}
      <SettingsSection category="game" title={t("settings.gameSection")}>
        {renderItems("game")}
      </SettingsSection>

      {/* TSFシナリオ(v0.9.0 で Experimental から昇格。既定 ON) */}
      <SettingsSection
        category="adventure"
        title={t("settings.adventureSection")}
      >
        {renderItems("adventure")}
      </SettingsSection>

      {/* 表示設定 */}
      <SettingsSection category="display" title={t("settings.displaySection")}>
        {renderItems("display")}
      </SettingsSection>

      {/* 画像生成設定 */}
      <SettingsSection category="image" title={t("settings.imageSection")}>
        {renderItems("image")}
      </SettingsSection>

      {/* 自分自身モード キャラ設定 */}
      <SettingsSection
        category="selfProfile"
        title={t("settings.selfProfile.sectionTitle")}
      >
        {renderItems("selfProfile")}
      </SettingsSection>

      {/* メモリ機能 */}
      <SettingsSection
        category="memory"
        title={
          <>
            {t("settings.memory.sectionTitle")}
            <span
              className="feature-chip-new"
              data-feature-version="v0.6.0"
              style={{ marginLeft: "0.5rem" }}
            >
              New
            </span>
          </>
        }
      >
        {renderItems("memory")}
      </SettingsSection>

      {/* 音声合成 */}
      <SettingsSection
        category="speech"
        title={
          <>
            {t("settings.speech.sectionTitle")}
            <span
              className="feature-chip-experimental"
              data-feature-version="v0.6.0"
              style={{ marginLeft: "0.5rem" }}
            >
              Experimental
            </span>
          </>
        }
      >
        {renderItems("speech")}
      </SettingsSection>

      {/* 通知設定 */}
      <SettingsSection category="notify" title={t("settings.notifySection")}>
        {renderItems("notify")}
      </SettingsSection>

      {/* 実験的機能(新しい設定画面では、役割に合うカテゴリへ移す項目がある) */}
      <SettingsSection
        category="experimental"
        title={t("settings.experimentalSection")}
      >
        {renderItems("experimental")}
      </SettingsSection>

      {/* 3Dモデル(VRM): TSFシナリオの対面会話モードで使う。モデルが増えると
    一覧が長くなるため既定で閉じ、最下部(リセットの手前)に置く。閉じて
    いる間も中身は DOM に残し(hidden)、見出しの要約(件数)を出す */}
      <CollapsibleSettingsSection
        category="avatar"
        title={
          <>
            {t("settings.avatar.sectionTitle")}
            <span
              className="feature-chip-experimental"
              data-feature-version="v0.7.0"
              style={{ marginLeft: "0.5rem" }}
            >
              Experimental
            </span>
          </>
        }
        summary={
          avatarSummary === null
            ? null
            : avatarSummary.total === 0
              ? t("settings.avatar.summaryEmpty")
              : t("settings.avatar.summary", {
                  total: avatarSummary.total,
                  characters: avatarSummary.characters,
                })
        }
        open={avatarSectionOpen}
        onToggle={toggleAvatarSection}
        bodyId="settings-avatar-section"
        toggleTestId="settings-avatar-toggle"
      >
        {renderItems("avatar")}
      </CollapsibleSettingsSection>

      {/* Live2D: 案内役キャラの Live2D 表示に必要な Cubism Core は同梱して
    いないため、入手先と配置先を案内する。3Dモデル(VRM)と同じく既定で
    閉じ、見出しの要約に配置状況を出す */}
      <CollapsibleSettingsSection
        category="live2d"
        title={
          <>
            {t("settings.live2d.sectionTitle")}
            <span
              className="feature-chip-experimental"
              data-feature-version="v0.9.0"
              style={{ marginLeft: "0.5rem" }}
            >
              Experimental
            </span>
          </>
        }
        summary={
          live2dStatus === null
            ? null
            : live2dStatus === "ready"
              ? t("settings.live2d.statusReady")
              : t("settings.live2d.statusMissing")
        }
        open={live2dSectionOpen}
        onToggle={toggleLive2dSection}
        bodyId="settings-live2d-section"
        toggleTestId="settings-live2d-toggle"
      >
        {renderItems("live2d")}
      </CollapsibleSettingsSection>

      {/* リセット */}
      <SettingsSection
        category="data"
        className="settings-screen__section--danger"
        title={t("settings.dataSection")}
      >
        {renderItems("data")}
      </SettingsSection>
    </>
  );

  return (
    <MainLayout>
      <SettingsViewContext.Provider value={view}>
        <div
          className={
            isV2 ? "settings-screen settings-screen--v2" : "settings-screen"
          }
        >
          <header className="settings-screen__header">
            <h1 className="settings-screen__title">{t("settings.title")}</h1>
            <label className="settings-screen__toggle settings-screen__header-toggle">
              <span className="settings-screen__item-label">
                {t("settings.newSettingsScreen")}
                <span
                  className="feature-chip-new"
                  data-feature-version="v0.9.0"
                >
                  New
                </span>
              </span>
              <input
                type="checkbox"
                checked={isV2}
                onChange={(e) => setNewSettingsScreenEnabled(e.target.checked)}
                className="settings-screen__toggle-input"
              />
              <span className="settings-screen__toggle-switch" />
            </label>
          </header>

          {isV2 ? (
            <div className="settings-v2">
              <SettingsNav
                query={query}
                onQueryChange={handleQueryChange}
                activeCategory={activeCategory}
                onSelectCategory={handleSelectCategory}
                matchCounts={matchCounts}
              />
              <div
                ref={contentRef}
                className="settings-screen__content settings-v2__content"
              >
                {matchedIds !== null && matchedIds.size === 0 && (
                  <div className="settings-v2__empty" role="status">
                    <p className="settings-v2__empty-text">
                      {t("settings.searchNoResults", { query: query.trim() })}
                    </p>
                    <button
                      type="button"
                      className="settings-v2__empty-clear"
                      onClick={() => handleQueryChange("")}
                    >
                      {t("settings.searchClear")}
                    </button>
                  </div>
                )}
                {sections}
              </div>
            </div>
          ) : (
            <div className="settings-screen__content">{sections}</div>
          )}
        </div>
      </SettingsViewContext.Provider>
    </MainLayout>
  );
}
