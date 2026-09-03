/**
 * SettingsContext - アプリケーション設定の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
} from "react";
import { fetchAnlasBalance } from "../apis/anlas";
import { getMemoryText as fetchMemoryTextApi } from "../apis/memory";
import type { SelfProfile } from "../apis/settings";
import { getSelfProfile as fetchSelfProfileApi } from "../apis/settings";
import { DEFAULT_LANGUAGE, type UiLanguage } from "../constants/language";
import {
  DEFAULT_NSFW_IMAGE_MODEL,
  DEFAULT_SFW_IMAGE_MODEL,
  isV5ImageModel,
} from "../constants/novelaiImageModels";
import i18n from "../i18n";
import type {
  AnlasBalance,
  InpaintMaskState,
  InpaintSettings,
  InstructionType,
  PreciseReference,
} from "../types";
import { DEFAULT_INPAINT_MASK_STATE, DEFAULT_INPAINT_SETTINGS } from "../types";
import {
  DEFAULT_HISTORY_LOOKBACK_TARGETS,
  type HistoryLookbackTarget,
  type HistoryLookbackTargets,
  normalizeHistoryLookbackTargets,
} from "../utils/historyLookback";

type FeelingMode = "legacy" | "gender_aware";

/** API / 旧値を feelingMode に正規化する */
function normalizeFeelingMode(raw: unknown): FeelingMode {
  if (raw === "gender_aware") {
    return "gender_aware";
  }
  // 誤って保存された new / experimental は gender_aware 扱い
  if (raw === "new" || raw === "experimental") {
    return "gender_aware";
  }
  return "legacy";
}

// 設定状態の型定義
/** 現実世界コンテキストがサーバ側で使える状態か(設定画面の説明の出し分け用) */
export interface RealWorldAvailability {
  promptPreviewEnabled: boolean;
  weatherConfigured: boolean;
  webSearchConfigured: boolean;
}

interface SettingsState {
  // 難易度設定
  difficulty: "easy" | "normal" | "hard";
  // 開花度増分の計算方式 (legacy=従来, new=緩やか)
  bloomCalcMethod: "legacy" | "new";
  // 心境生成方式 (legacy=従来TSF抵抗, gender_aware=性別適合を考慮)
  feelingMode: "legacy" | "gender_aware";
  // 性別適合の高度判定 (LLM)。feelingMode=gender_aware 時のみ有効。デフォルト OFF
  genderCongruenceLlmEnabled: boolean;
  language: UiLanguage;

  // NSFWモード
  nsfwMode: boolean;

  // 画像プロバイダー
  imageProvider: "selfhost" | "openrouter" | "novelai";

  // 補助表示情報
  totalCost: number;
  showCost: boolean;
  anlasBalance: AnlasBalance | null;

  // デフォルトの指示タイプ
  defaultInstructionType: InstructionType;

  // インペイント設定
  inpaintSettings: InpaintSettings;
  inpaintEnabled: boolean; // 007: インペイントトグル
  inpaintMask: InpaintMaskState;

  // 通知設定
  showAchievementNotifications: boolean;
  showRealityAttributeNotification: boolean;
  experimentalEndingEnabled: boolean;
  experimentalAdventureEnabled: boolean;
  experimentalPromptExpanderEnabled: boolean;
  playMemoryEnabled: boolean;
  playMemorySystemEnabled: boolean;
  playMemoryUserEnabled: boolean;

  // お気に入り一覧からの削除時に確認ダイアログを表示する (spec 009)
  confirmFavoriteRemove: boolean;

  // サウンド設定
  soundEnabled: boolean;
  soundVolume: number;

  // UI設定 (007)
  rightPanelOpen: boolean;

  // 精密参照画像 (013)
  preciseReferences: PreciseReference[];

  // Self-profile (US6)
  selfProfile: SelfProfile | null;

  // Seed value for image generation (null = random)
  seed: number | null;

  // US3: Enable surroundings image generation
  enableSurroundingsImage: boolean;
  // Include reactive bystanders in surroundings image
  surroundingsIncludePeople: boolean;

  // Adventureモード: 新規Run作成フォームの「背景と人物を同時に描く」初期値（Run単位で上書き可能）
  adventureEnableCompositeScene: boolean;

  // Font family setting
  fontFamily: string;

  // Clothing color consistency (experimental)
  clothingColorConsistency: boolean;

  // 衣装レイヤーの可視性を考慮する
  respectClothingLayers: boolean;

  // Chat-to-image linking: scroll chat on image navigation
  linkChatToImage: boolean;

  // Multiple people in image generation (experimental)
  enableMultiplePeople: boolean;

  // 【v0.5.0】複数人表示が有効でも、CharacterPanel の multi-character
  // プロンプト注入をバイパスして「いままでどおり」の振る舞いをさせるトグル。
  // true (既定) = SessionCharacters をプロンプトと enable_multiple_people
  // ボディフラグに反映、false = バイパス（単一キャラ JSON 出力）。
  multiCharacterPanelEnabled: boolean;

  // NovelAI text model selection (Opus only)
  novelaiTextModel: string;
  // NovelAI subscription tier (null = unknown)
  novelaiTier: number | null;
  // NovelAI image model selections (backend-persisted)
  novelaiImageModel: string; // NSFW ON 時に使用
  novelaiCuratedImageModel: string; // NSFW OFF 時に使用

  // Text-to-Speech (AivisSpeech)
  ttsEnabled: boolean;
  ttsUseGpu: boolean;
  ttsEngineDir: string;
  /** 音声合成エンジンの待ち受けポート。null なら backend 既定 (10101) を使う */
  ttsEnginePort: number | null;
  ttsModelDir: string;
  ttsSpeakerId: string | null;
  ttsStyleId: string | null;
  ttsOutputFormat: "wav";

  // 現実世界コンテキスト (backend-persisted)。日時・天気と Web 検索は別トグル
  realWorldWeatherEnabled: boolean;
  realWorldSearchEnabled: boolean;
  realWorldAvailability: RealWorldAvailability;

  // spec 004 (US4): プロンプト生成時に参照する履歴遡及件数 (5..20, default 10)
  historyLookbackCount: number;
  historyLookbackTargets: HistoryLookbackTargets;

  // メモリ機能: ユーザーの好み・性的嗜好を保持するテキスト
  memoryText: string | null;
}

// アクション型
type SettingsAction =
  | { type: "SET_DIFFICULTY"; payload: "easy" | "normal" | "hard" }
  | { type: "SET_BLOOM_CALC_METHOD"; payload: "legacy" | "new" }
  | { type: "SET_FEELING_MODE"; payload: "legacy" | "gender_aware" }
  | { type: "SET_GENDER_CONGRUENCE_LLM_ENABLED"; payload: boolean }
  | { type: "SET_LANGUAGE"; payload: UiLanguage }
  | { type: "SET_NSFW_MODE"; payload: boolean }
  | { type: "TOGGLE_NSFW" }
  | {
      type: "SET_IMAGE_PROVIDER";
      payload: "selfhost" | "openrouter" | "novelai";
    }
  | { type: "SET_TOTAL_COST"; payload: number }
  | { type: "ADD_TOTAL_COST"; payload: number }
  | { type: "RESET_TOTAL_COST" }
  | { type: "SET_SHOW_COST"; payload: boolean }
  | { type: "SET_ANLAS_BALANCE"; payload: AnlasBalance | null }
  | { type: "SET_DEFAULT_INSTRUCTION_TYPE"; payload: InstructionType }
  | { type: "SET_INPAINT_SETTINGS"; payload: Partial<InpaintSettings> }
  | { type: "SET_INPAINT_MASK"; payload: InpaintMaskState }
  | { type: "CLEAR_INPAINT_MASK" }
  | { type: "TOGGLE_INPAINT" }
  | { type: "SET_SHOW_ACHIEVEMENT_NOTIFICATIONS"; payload: boolean }
  | { type: "SET_SHOW_REALITY_ATTRIBUTE_NOTIFICATION"; payload: boolean }
  | { type: "SET_EXPERIMENTAL_ENDING_ENABLED"; payload: boolean }
  | { type: "SET_EXPERIMENTAL_ADVENTURE_ENABLED"; payload: boolean }
  | { type: "SET_EXPERIMENTAL_PROMPT_EXPANDER_ENABLED"; payload: boolean }
  | { type: "SET_PLAY_MEMORY_ENABLED"; payload: boolean }
  | { type: "SET_PLAY_MEMORY_SYSTEM_ENABLED"; payload: boolean }
  | { type: "SET_PLAY_MEMORY_USER_ENABLED"; payload: boolean }
  | { type: "SET_CONFIRM_FAVORITE_REMOVE"; payload: boolean }
  | { type: "SET_SOUND_ENABLED"; payload: boolean }
  | { type: "SET_SOUND_VOLUME"; payload: number }
  | { type: "TOGGLE_PANEL" }
  | { type: "SET_PANEL_OPEN"; payload: boolean }
  | { type: "LOAD_SETTINGS"; payload: Partial<SettingsState> }
  | { type: "RESET_SETTINGS" }
  | { type: "ADD_PRECISE_REFERENCE"; payload: PreciseReference }
  | {
      type: "UPDATE_PRECISE_REFERENCE";
      payload: { id: string } & Partial<PreciseReference>;
    }
  | { type: "REMOVE_PRECISE_REFERENCE"; payload: string }
  | { type: "CLEAR_PRECISE_REFERENCES" }
  | { type: "SET_SELF_PROFILE"; payload: SelfProfile | null }
  | { type: "SET_SEED"; payload: number | null }
  | { type: "SET_ENABLE_SURROUNDINGS_IMAGE"; payload: boolean }
  | { type: "SET_SURROUNDINGS_INCLUDE_PEOPLE"; payload: boolean }
  | { type: "SET_ADVENTURE_ENABLE_COMPOSITE_SCENE"; payload: boolean }
  | { type: "SET_FONT_FAMILY"; payload: string }
  | { type: "SET_CLOTHING_COLOR_CONSISTENCY"; payload: boolean }
  | { type: "SET_RESPECT_CLOTHING_LAYERS"; payload: boolean }
  | { type: "SET_LINK_CHAT_TO_IMAGE"; payload: boolean }
  | { type: "SET_ENABLE_MULTIPLE_PEOPLE"; payload: boolean }
  | { type: "SET_MULTI_CHARACTER_PANEL_ENABLED"; payload: boolean }
  | { type: "SET_NOVELAI_TEXT_MODEL"; payload: string }
  | { type: "SET_NOVELAI_TIER"; payload: number | null }
  | { type: "SET_NOVELAI_IMAGE_MODEL"; payload: string }
  | { type: "SET_NOVELAI_CURATED_IMAGE_MODEL"; payload: string }
  | { type: "SET_TTS_ENABLED"; payload: boolean }
  | { type: "SET_TTS_USE_GPU"; payload: boolean }
  | { type: "SET_TTS_ENGINE_DIR"; payload: string }
  | { type: "SET_TTS_ENGINE_PORT"; payload: number | null }
  | { type: "SET_TTS_MODEL_DIR"; payload: string }
  | { type: "SET_TTS_SPEAKER_ID"; payload: string | null }
  | { type: "SET_TTS_STYLE_ID"; payload: string | null }
  | { type: "SET_TTS_OUTPUT_FORMAT"; payload: "wav" }
  | { type: "SET_REAL_WORLD_WEATHER_ENABLED"; payload: boolean }
  | { type: "SET_REAL_WORLD_SEARCH_ENABLED"; payload: boolean }
  | { type: "SET_HISTORY_LOOKBACK_COUNT"; payload: number }
  | {
      type: "SET_HISTORY_LOOKBACK_TARGET";
      payload: { target: HistoryLookbackTarget; enabled: boolean };
    }
  | { type: "SET_MEMORY_TEXT"; payload: string | null };

// デフォルト状態
const defaultState: SettingsState = {
  difficulty: "normal",
  bloomCalcMethod: "legacy",
  feelingMode: "legacy",
  genderCongruenceLlmEnabled: false,
  language: DEFAULT_LANGUAGE,
  nsfwMode: false,
  imageProvider: "selfhost",
  totalCost: 0,
  showCost: false,
  anlasBalance: null,
  defaultInstructionType: "dress_up",
  inpaintSettings: DEFAULT_INPAINT_SETTINGS,
  inpaintEnabled: false,
  inpaintMask: DEFAULT_INPAINT_MASK_STATE,
  showAchievementNotifications: true,
  showRealityAttributeNotification: true,
  experimentalEndingEnabled: false,
  experimentalAdventureEnabled: false,
  experimentalPromptExpanderEnabled: false,
  playMemoryEnabled: false,
  playMemorySystemEnabled: true,
  playMemoryUserEnabled: true,
  confirmFavoriteRemove: true,
  soundEnabled: true,
  soundVolume: 0.5,
  rightPanelOpen: false,
  preciseReferences: [],
  selfProfile: null,
  seed: null,
  enableSurroundingsImage: false,
  surroundingsIncludePeople: false,
  adventureEnableCompositeScene: false,
  fontFamily: "system",
  clothingColorConsistency: false,
  respectClothingLayers: false,
  linkChatToImage: false,
  enableMultiplePeople: false,
  multiCharacterPanelEnabled: true,
  novelaiTextModel: "glm-4-6",
  novelaiTier: null,
  novelaiImageModel: DEFAULT_NSFW_IMAGE_MODEL,
  novelaiCuratedImageModel: DEFAULT_SFW_IMAGE_MODEL,
  ttsEnabled: false,
  ttsUseGpu: false,
  ttsEngineDir: "contrib/AivisSpeech",
  ttsEnginePort: null,
  ttsModelDir: "%APPDATA%\\AivisSpeech-Engine\\Models",
  ttsSpeakerId: null,
  ttsStyleId: null,
  ttsOutputFormat: "wav",
  realWorldWeatherEnabled: false,
  realWorldSearchEnabled: false,
  realWorldAvailability: {
    promptPreviewEnabled: false,
    weatherConfigured: false,
    webSearchConfigured: false,
  },
  historyLookbackCount: 10,
  historyLookbackTargets: { ...DEFAULT_HISTORY_LOOKBACK_TARGETS },
  memoryText: null,
};

// Reducer
function settingsReducer(
  state: SettingsState,
  action: SettingsAction,
): SettingsState {
  switch (action.type) {
    case "SET_DIFFICULTY":
      return { ...state, difficulty: action.payload };
    case "SET_BLOOM_CALC_METHOD":
      return { ...state, bloomCalcMethod: action.payload };
    case "SET_FEELING_MODE":
      return { ...state, feelingMode: action.payload };
    case "SET_GENDER_CONGRUENCE_LLM_ENABLED":
      return { ...state, genderCongruenceLlmEnabled: action.payload };
    case "SET_LANGUAGE":
      return { ...state, language: action.payload };
    case "SET_NSFW_MODE":
      return { ...state, nsfwMode: action.payload };
    case "TOGGLE_NSFW":
      return { ...state, nsfwMode: !state.nsfwMode };
    case "SET_IMAGE_PROVIDER":
      return { ...state, imageProvider: action.payload };
    case "SET_TOTAL_COST":
      return { ...state, totalCost: action.payload };
    case "ADD_TOTAL_COST":
      return { ...state, totalCost: state.totalCost + action.payload };
    case "RESET_TOTAL_COST":
      return { ...state, totalCost: 0 };
    case "SET_SHOW_COST":
      return { ...state, showCost: action.payload };
    case "SET_ANLAS_BALANCE":
      return { ...state, anlasBalance: action.payload };
    case "SET_DEFAULT_INSTRUCTION_TYPE":
      return { ...state, defaultInstructionType: action.payload };
    case "SET_INPAINT_SETTINGS":
      return {
        ...state,
        inpaintSettings: { ...state.inpaintSettings, ...action.payload },
      };
    case "SET_INPAINT_MASK":
      return {
        ...state,
        inpaintMask: action.payload,
      };
    case "CLEAR_INPAINT_MASK":
      return {
        ...state,
        inpaintMask: DEFAULT_INPAINT_MASK_STATE,
      };
    case "TOGGLE_INPAINT":
      if (state.inpaintEnabled) {
        return {
          ...state,
          inpaintEnabled: false,
          inpaintMask: DEFAULT_INPAINT_MASK_STATE,
          inpaintSettings: { ...state.inpaintSettings, enabled: false },
        };
      }
      return {
        ...state,
        inpaintEnabled: true,
        inpaintSettings: { ...state.inpaintSettings, enabled: true },
      };
    case "SET_SHOW_ACHIEVEMENT_NOTIFICATIONS":
      return { ...state, showAchievementNotifications: action.payload };
    case "SET_SHOW_REALITY_ATTRIBUTE_NOTIFICATION":
      return { ...state, showRealityAttributeNotification: action.payload };
    case "SET_EXPERIMENTAL_ENDING_ENABLED":
      return { ...state, experimentalEndingEnabled: action.payload };
    case "SET_EXPERIMENTAL_ADVENTURE_ENABLED":
      return { ...state, experimentalAdventureEnabled: action.payload };
    case "SET_EXPERIMENTAL_PROMPT_EXPANDER_ENABLED":
      return { ...state, experimentalPromptExpanderEnabled: action.payload };
    case "SET_PLAY_MEMORY_ENABLED":
      return { ...state, playMemoryEnabled: action.payload };
    case "SET_PLAY_MEMORY_SYSTEM_ENABLED":
      return { ...state, playMemorySystemEnabled: action.payload };
    case "SET_PLAY_MEMORY_USER_ENABLED":
      return { ...state, playMemoryUserEnabled: action.payload };
    case "SET_CONFIRM_FAVORITE_REMOVE":
      return { ...state, confirmFavoriteRemove: action.payload };
    case "SET_SOUND_ENABLED":
      return { ...state, soundEnabled: action.payload };
    case "SET_SOUND_VOLUME":
      return { ...state, soundVolume: action.payload };
    case "TOGGLE_PANEL":
      return { ...state, rightPanelOpen: !state.rightPanelOpen };
    case "SET_PANEL_OPEN":
      return { ...state, rightPanelOpen: action.payload };
    case "LOAD_SETTINGS":
      return { ...state, ...action.payload };
    case "RESET_SETTINGS":
      return defaultState;
    case "ADD_PRECISE_REFERENCE":
      return {
        ...state,
        preciseReferences: [...state.preciseReferences, action.payload],
      };
    case "UPDATE_PRECISE_REFERENCE":
      return {
        ...state,
        preciseReferences: state.preciseReferences.map((ref) =>
          ref.id === action.payload.id ? { ...ref, ...action.payload } : ref,
        ),
      };
    case "REMOVE_PRECISE_REFERENCE":
      return {
        ...state,
        preciseReferences: state.preciseReferences.filter(
          (ref) => ref.id !== action.payload,
        ),
      };
    case "CLEAR_PRECISE_REFERENCES":
      return { ...state, preciseReferences: [] };
    case "SET_SELF_PROFILE":
      return { ...state, selfProfile: action.payload };
    case "SET_SEED":
      return { ...state, seed: action.payload };
    case "SET_ENABLE_SURROUNDINGS_IMAGE":
      return { ...state, enableSurroundingsImage: action.payload };
    case "SET_SURROUNDINGS_INCLUDE_PEOPLE":
      return { ...state, surroundingsIncludePeople: action.payload };
    case "SET_ADVENTURE_ENABLE_COMPOSITE_SCENE":
      return { ...state, adventureEnableCompositeScene: action.payload };
    case "SET_FONT_FAMILY":
      return { ...state, fontFamily: action.payload };
    case "SET_CLOTHING_COLOR_CONSISTENCY":
      return { ...state, clothingColorConsistency: action.payload };
    case "SET_RESPECT_CLOTHING_LAYERS":
      return { ...state, respectClothingLayers: action.payload };
    case "SET_LINK_CHAT_TO_IMAGE":
      return { ...state, linkChatToImage: action.payload };
    case "SET_ENABLE_MULTIPLE_PEOPLE":
      return { ...state, enableMultiplePeople: action.payload };
    case "SET_MULTI_CHARACTER_PANEL_ENABLED":
      return { ...state, multiCharacterPanelEnabled: action.payload };
    case "SET_NOVELAI_TEXT_MODEL":
      return { ...state, novelaiTextModel: action.payload };
    case "SET_NOVELAI_TIER":
      return { ...state, novelaiTier: action.payload };
    case "SET_NOVELAI_IMAGE_MODEL":
      return { ...state, novelaiImageModel: action.payload };
    case "SET_NOVELAI_CURATED_IMAGE_MODEL":
      return { ...state, novelaiCuratedImageModel: action.payload };
    case "SET_TTS_ENABLED":
      return { ...state, ttsEnabled: action.payload };
    case "SET_TTS_USE_GPU":
      return { ...state, ttsUseGpu: action.payload };
    case "SET_TTS_ENGINE_DIR":
      return { ...state, ttsEngineDir: action.payload };
    case "SET_TTS_ENGINE_PORT":
      return { ...state, ttsEnginePort: action.payload };
    case "SET_TTS_MODEL_DIR":
      return { ...state, ttsModelDir: action.payload };
    case "SET_TTS_SPEAKER_ID":
      return { ...state, ttsSpeakerId: action.payload };
    case "SET_TTS_STYLE_ID":
      return { ...state, ttsStyleId: action.payload };
    case "SET_TTS_OUTPUT_FORMAT":
      return { ...state, ttsOutputFormat: action.payload };
    case "SET_REAL_WORLD_WEATHER_ENABLED":
      return { ...state, realWorldWeatherEnabled: action.payload };
    case "SET_REAL_WORLD_SEARCH_ENABLED":
      return { ...state, realWorldSearchEnabled: action.payload };
    case "SET_HISTORY_LOOKBACK_COUNT":
      return {
        ...state,
        historyLookbackCount: Math.max(5, Math.min(20, action.payload)),
      };
    case "SET_HISTORY_LOOKBACK_TARGET":
      return {
        ...state,
        historyLookbackTargets: {
          ...state.historyLookbackTargets,
          [action.payload.target]: action.payload.enabled,
        },
      };
    case "SET_MEMORY_TEXT":
      return { ...state, memoryText: action.payload };
    default:
      return state;
  }
}

// Context型定義
interface SettingsContextType {
  state: SettingsState;
  setDifficulty: (difficulty: "easy" | "normal" | "hard") => void;
  setBloomCalcMethod: (method: "legacy" | "new") => void;
  setFeelingMode: (mode: "legacy" | "gender_aware") => void;
  setGenderCongruenceLlmEnabled: (enabled: boolean) => void;
  setLanguage: (language: UiLanguage) => void;
  setNsfwMode: (enabled: boolean) => void;
  toggleNsfw: () => void;
  setImageProvider: (provider: "selfhost" | "openrouter" | "novelai") => void;
  setTotalCost: (value: number) => void;
  addTotalCost: (value: number) => void;
  resetTotalCost: () => void;
  setShowCost: (show: boolean) => void;
  setAnlasBalance: (balance: AnlasBalance | null) => void;
  setDefaultInstructionType: (type: InstructionType) => void;
  setInpaintSettings: (settings: Partial<InpaintSettings>) => void;
  setInpaintMask: (
    maskDataUrl: string | null,
    selectedMaskId: string | null,
  ) => void;
  clearInpaintMask: () => void;
  toggleInpaint: () => void;
  setShowAchievementNotifications: (show: boolean) => void;
  setShowRealityAttributeNotification: (show: boolean) => void;
  setExperimentalEndingEnabled: (enabled: boolean) => void;
  setExperimentalAdventureEnabled: (enabled: boolean) => void;
  setExperimentalPromptExpanderEnabled: (enabled: boolean) => void;
  setPlayMemoryEnabled: (enabled: boolean) => void;
  setPlayMemorySystemEnabled: (enabled: boolean) => void;
  setPlayMemoryUserEnabled: (enabled: boolean) => void;
  setConfirmFavoriteRemove: (enabled: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setSoundVolume: (volume: number) => void;
  togglePanel: () => void;
  setPanelOpen: (open: boolean) => void;
  resetSettings: () => void;
  addPreciseReference: (ref: PreciseReference) => void;
  updatePreciseReference: (
    id: string,
    updates: Partial<PreciseReference>,
  ) => void;
  removePreciseReference: (id: string) => void;
  clearPreciseReferences: () => void;
  // US6: Self-profile
  selfProfile: SelfProfile | null;
  setSelfProfile: (profile: SelfProfile | null) => void;
  loadSelfProfile: () => Promise<void>;
  setSeed: (seed: number | null) => void;
  setEnableSurroundingsImage: (enabled: boolean) => void;
  setSurroundingsIncludePeople: (enabled: boolean) => void;
  setAdventureEnableCompositeScene: (enabled: boolean) => void;
  setFontFamily: (fontFamily: string) => void;
  setClothingColorConsistency: (enabled: boolean) => void;
  setLinkChatToImage: (enabled: boolean) => void;
  setRespectClothingLayers: (enabled: boolean) => void;
  setEnableMultiplePeople: (enabled: boolean) => void;
  setMultiCharacterPanelEnabled: (enabled: boolean) => void;
  setNovelaiTextModel: (model: string) => void;
  setNovelaiTier: (tier: number | null) => void;
  setNovelaiImageModel: (model: string) => void;
  setNovelaiCuratedImageModel: (model: string) => void;
  /** 現在のNSFW設定で実際に使われるNovelAI画像モデル */
  effectiveNovelaiImageModel: string;
  /** NovelAIプロバイダーかつ実効モデルがV5系のとき true */
  isNovelaiV5Active: boolean;
  setTtsEnabled: (enabled: boolean) => void;
  setTtsUseGpu: (enabled: boolean) => void;
  setTtsEngineDir: (engineDir: string) => void;
  setTtsEnginePort: (port: number) => void;
  setTtsModelDir: (modelDir: string) => void;
  setTtsSpeakerId: (speakerId: string | null) => void;
  setTtsStyleId: (styleId: string | null) => void;
  setTtsOutputFormat: (format: "wav") => void;
  setRealWorldWeatherEnabled: (enabled: boolean) => void;
  setRealWorldSearchEnabled: (enabled: boolean) => void;
  setHistoryLookbackCount: (count: number) => void;
  setHistoryLookbackTarget: (
    target: HistoryLookbackTarget,
    enabled: boolean,
  ) => void;
  // メモリ機能
  memoryText: string | null;
  setMemoryText: (memoryText: string | null) => void;
  loadMemoryText: () => Promise<void>;
}

// Context作成
const SettingsContext = createContext<SettingsContextType | null>(null);

// localStorage キー
const STORAGE_KEY = "app_settings";

// Lazy initializer: load settings from localStorage synchronously
// to avoid race condition where the save effect overwrites before dispatch is processed
function loadInitialState(initial: SettingsState): SettingsState {
  try {
    // v0.8.0 で削除した「保持する要素」プリセットの残骸を破棄する
    localStorage.removeItem("preserve_presets");
    const saved = localStorage.getItem(STORAGE_KEY);
    const legacyTotalCost = localStorage.getItem("api_total_cost");
    if (saved) {
      const parsed = JSON.parse(saved);
      // imageProviderはバックエンドから取得するため除外
      const { imageProvider: _ignored, ...rest } = parsed;
      // novelaiTextModelとnovelaiTierはバックエンド/API経由のため除外
      // v0.8.0 で削除した「保持する要素」設定は読み込まない
      const {
        novelaiTextModel: _nai,
        novelaiTier: _tier,
        novelaiImageModel: _naiImg,
        novelaiCuratedImageModel: _naiCuratedImg,
        changeSettings: _legacyChangeSettings,
        ...filtered
      } = rest;
      return {
        ...initial,
        ...filtered,
        historyLookbackTargets: normalizeHistoryLookbackTargets(
          filtered.historyLookbackTargets,
        ),
        totalCost:
          typeof rest.totalCost === "number"
            ? rest.totalCost
            : legacyTotalCost
              ? parseFloat(legacyTotalCost)
              : initial.totalCost,
      };
    }

    if (legacyTotalCost) {
      return {
        ...initial,
        totalCost: parseFloat(legacyTotalCost),
      };
    }
  } catch (error) {
    console.error("Failed to load settings from localStorage:", error);
  }
  return initial;
}

// Provider コンポーネント
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(
    settingsReducer,
    defaultState,
    loadInitialState,
  );
  const isInitializedRef = useRef(true);

  // 初回ロード時にバックエンドから画像プロバイダーを取得
  useEffect(() => {
    const fetchImageProvider = async () => {
      try {
        const res = await fetch("/health");
        if (res.ok) {
          const data = await res.json();
          const provider = data.image_provider as
            | "selfhost"
            | "openrouter"
            | "novelai";
          if (
            provider === "openrouter" ||
            provider === "novelai" ||
            provider === "selfhost"
          ) {
            dispatch({ type: "SET_IMAGE_PROVIDER", payload: provider });
          }

          const hasCostProvider =
            data.image_provider === "openrouter" ||
            data.image_description_provider === "openrouter" ||
            data.feeling_provider === "openrouter";
          dispatch({ type: "SET_SHOW_COST", payload: hasCostProvider });

          if (provider !== "novelai") {
            dispatch({ type: "SET_ANLAS_BALANCE", payload: null });
          }
        }
      } catch (error) {
        console.warn("Failed to fetch image provider from /health:", error);
      }
    };
    fetchImageProvider();
  }, []);

  useEffect(() => {
    if (state.imageProvider !== "novelai" && state.anlasBalance !== null) {
      dispatch({ type: "SET_ANLAS_BALANCE", payload: null });
    }
  }, [state.imageProvider, state.anlasBalance]);

  // NovelAI利用時はAnlas残高/利用上限を初期取得する
  // （設定画面・設定パネル・HUDの利用上限バー表示に共通で使う）
  useEffect(() => {
    if (state.imageProvider !== "novelai" || state.anlasBalance !== null) {
      return;
    }
    let cancelled = false;
    fetchAnlasBalance().then((balance) => {
      if (!cancelled && balance) {
        dispatch({ type: "SET_ANLAS_BALANCE", payload: balance });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [state.imageProvider, state.anlasBalance]);

  // 初回ロード時にバックエンドからユーザー設定を取得
  useEffect(() => {
    const fetchUserSettings = async () => {
      try {
        const res = await fetch("/api/settings/user");
        if (res.ok) {
          const data = await res.json();
          dispatch({
            type: "LOAD_SETTINGS",
            payload: {
              nsfwMode: data.nsfw_mode,
              difficulty: data.difficulty,
              bloomCalcMethod: data.bloom_calc_method ?? "legacy",
              feelingMode: normalizeFeelingMode(data.feeling_mode),
              genderCongruenceLlmEnabled:
                data.gender_congruence_llm_enabled ?? false,
              language: data.language ?? DEFAULT_LANGUAGE,
              novelaiTextModel: data.novelai_text_model ?? "glm-4-6",
              novelaiImageModel:
                data.novelai_image_model ?? DEFAULT_NSFW_IMAGE_MODEL,
              novelaiCuratedImageModel:
                data.novelai_curated_image_model ?? DEFAULT_SFW_IMAGE_MODEL,
              ttsEnabled: data.tts_enabled ?? false,
              ttsUseGpu: data.tts_use_gpu ?? false,
              ttsEngineDir: data.tts_engine_dir ?? "contrib/AivisSpeech",
              ttsEnginePort: data.tts_engine_port ?? null,
              ttsModelDir:
                data.tts_model_dir ?? "%APPDATA%\\AivisSpeech-Engine\\Models",
              ttsSpeakerId: data.tts_speaker_id ?? null,
              ttsStyleId: data.tts_style_id ?? null,
              ttsOutputFormat: data.tts_output_format ?? "wav",
              realWorldWeatherEnabled: data.real_world_weather_enabled ?? false,
              realWorldSearchEnabled: data.real_world_search_enabled ?? false,
              realWorldAvailability: {
                promptPreviewEnabled: data.prompt_preview_enabled ?? false,
                weatherConfigured: data.weather_configured ?? false,
                webSearchConfigured: data.web_search_configured ?? false,
              },
            },
          });
        }
      } catch (error) {
        console.warn("Failed to fetch user settings from backend:", error);
      }
    };
    fetchUserSettings();
  }, []);

  // spec 004 (US4): Load per-session settings (history_lookback_count etc.)
  useEffect(() => {
    const fetchSessionSettings = async () => {
      try {
        const res = await fetch("/api/settings");
        if (res.ok) {
          const data = await res.json();
          const settings = data?.settings ?? data;
          if (settings && typeof settings.history_lookback_count === "number") {
            dispatch({
              type: "SET_HISTORY_LOOKBACK_COUNT",
              payload: settings.history_lookback_count,
            });
          }
        }
      } catch (error) {
        console.warn("Failed to fetch session settings from backend:", error);
      }
    };
    fetchSessionSettings();
  }, []);

  // Load self-profile from backend on init (US6)
  useEffect(() => {
    const loadProfile = async () => {
      try {
        const profile = await fetchSelfProfileApi();
        if (profile) {
          dispatch({ type: "SET_SELF_PROFILE", payload: profile });
        }
      } catch (error) {
        console.warn("Failed to fetch self-profile:", error);
      }
    };
    loadProfile();
  }, []);

  // メモリテキストをバックエンドから初期読み込み
  useEffect(() => {
    const loadMemory = async () => {
      try {
        const memoryText = await fetchMemoryTextApi();
        dispatch({ type: "SET_MEMORY_TEXT", payload: memoryText });
      } catch (error) {
        console.warn("Failed to fetch memory text:", error);
      }
    };
    loadMemory();
  }, []);

  // 状態変更時にlocalStorageに保存（imageProviderは除外）
  // 初期化完了後のみ保存（初期状態での上書きを防ぐ）
  useEffect(() => {
    if (!isInitializedRef.current) return;
    try {
      const {
        imageProvider: _ignored,
        preciseReferences: _ignored2,
        selfProfile: _ignored3,
        seed: _ignored4,
        anlasBalance: _ignored5,
        novelaiTextModel: _ignored6,
        novelaiTier: _ignored7,
        novelaiImageModel: _ignored9,
        novelaiCuratedImageModel: _ignored10,
        memoryText: _ignored8,
        // サーバ側の状態なので localStorage には残さない
        realWorldAvailability: _ignored11,
        ...rest
      } = state;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(rest));
      localStorage.setItem("api_total_cost", String(state.totalCost));
    } catch (error) {
      console.error("Failed to save settings to localStorage:", error);
    }
  }, [state]);

  useEffect(() => {
    if (i18n.language !== state.language) {
      void i18n.changeLanguage(state.language);
    }
  }, [state.language]);

  // Apply font family to document root (fonts are bundled via @fontsource)
  useEffect(() => {
    const fontMap: Record<string, string> = {
      "browser-default": "initial",
      system:
        '"Segoe UI", "Noto Sans", system-ui, -apple-system, "Hiragino Sans", sans-serif',
      "biz-udgothic": '"BIZ UDGothic", "Segoe UI", system-ui, sans-serif',
      "noto-sans-jp": '"Noto Sans JP", "Segoe UI", system-ui, sans-serif',
      "biz-udmincho": '"BIZ UDMincho", "Segoe UI", system-ui, serif',
      inter: '"Inter", "Segoe UI", system-ui, sans-serif',
      "roboto-mono": '"Roboto Mono", "Courier New", monospace',
    };

    const fontValue = fontMap[state.fontFamily] ?? fontMap.system;
    document.documentElement.style.setProperty("--app-font-family", fontValue);
  }, [state.fontFamily]);

  // アクション関数
  const setDifficulty = useCallback(
    async (difficulty: "easy" | "normal" | "hard") => {
      dispatch({ type: "SET_DIFFICULTY", payload: difficulty });
      // バックエンドに保存
      try {
        await fetch("/api/settings/user", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ difficulty }),
        });
      } catch (error) {
        console.error("Failed to save difficulty to backend:", error);
      }
    },
    [],
  );

  const setBloomCalcMethod = useCallback(async (method: "legacy" | "new") => {
    dispatch({ type: "SET_BLOOM_CALC_METHOD", payload: method });
    // バックエンドに保存
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bloom_calc_method: method }),
      });
    } catch (error) {
      console.error("Failed to save bloom_calc_method to backend:", error);
    }
  }, []);

  const setFeelingMode = useCallback(
    async (mode: "legacy" | "gender_aware") => {
      dispatch({ type: "SET_FEELING_MODE", payload: mode });
      try {
        await fetch("/api/settings/user", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feeling_mode: mode }),
        });
      } catch (error) {
        console.error("Failed to save feeling_mode to backend:", error);
      }
    },
    [],
  );

  const setGenderCongruenceLlmEnabled = useCallback(
    async (enabled: boolean) => {
      dispatch({ type: "SET_GENDER_CONGRUENCE_LLM_ENABLED", payload: enabled });
      try {
        await fetch("/api/settings/user", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gender_congruence_llm_enabled: enabled }),
        });
      } catch (error) {
        console.error(
          "Failed to save gender_congruence_llm_enabled to backend:",
          error,
        );
      }
    },
    [],
  );

  const setNsfwMode = useCallback(async (enabled: boolean) => {
    dispatch({ type: "SET_NSFW_MODE", payload: enabled });
    // バックエンドに保存
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nsfw_mode: enabled }),
      });
    } catch (error) {
      console.error("Failed to save nsfw_mode to backend:", error);
    }
  }, []);

  const setLanguage = useCallback(async (language: UiLanguage) => {
    dispatch({ type: "SET_LANGUAGE", payload: language });
    void i18n.changeLanguage(language);
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language }),
      });
    } catch (error) {
      console.error("Failed to save language to backend:", error);
    }
  }, []);

  const toggleNsfw = useCallback(async () => {
    // 現在の状態をトグル
    const newValue = !state.nsfwMode;
    dispatch({ type: "SET_NSFW_MODE", payload: newValue });
    // バックエンドに保存
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nsfw_mode: newValue }),
      });
    } catch (error) {
      console.error("Failed to save nsfw_mode to backend:", error);
    }
  }, [state.nsfwMode]);

  const setImageProvider = useCallback(
    (provider: "selfhost" | "openrouter" | "novelai") => {
      dispatch({ type: "SET_IMAGE_PROVIDER", payload: provider });
    },
    [],
  );

  const setTotalCost = useCallback((value: number) => {
    dispatch({ type: "SET_TOTAL_COST", payload: value });
  }, []);

  const addTotalCost = useCallback((value: number) => {
    dispatch({ type: "ADD_TOTAL_COST", payload: value });
  }, []);

  const resetTotalCost = useCallback(() => {
    dispatch({ type: "RESET_TOTAL_COST" });
  }, []);

  const setShowCost = useCallback((show: boolean) => {
    dispatch({ type: "SET_SHOW_COST", payload: show });
  }, []);

  const setAnlasBalance = useCallback((balance: AnlasBalance | null) => {
    dispatch({ type: "SET_ANLAS_BALANCE", payload: balance });
  }, []);

  const setDefaultInstructionType = useCallback((type: InstructionType) => {
    dispatch({ type: "SET_DEFAULT_INSTRUCTION_TYPE", payload: type });
  }, []);

  const setInpaintSettings = useCallback(
    (settings: Partial<InpaintSettings>) => {
      dispatch({ type: "SET_INPAINT_SETTINGS", payload: settings });
    },
    [],
  );

  const toggleInpaint = useCallback(() => {
    dispatch({ type: "TOGGLE_INPAINT" });
  }, []);

  const setInpaintMask = useCallback(
    (maskDataUrl: string | null, selectedMaskId: string | null) => {
      dispatch({
        type: "SET_INPAINT_MASK",
        payload: {
          maskDataUrl,
          selectedMaskId,
        },
      });
    },
    [],
  );

  const clearInpaintMask = useCallback(() => {
    dispatch({ type: "CLEAR_INPAINT_MASK" });
  }, []);

  const setShowAchievementNotifications = useCallback((show: boolean) => {
    dispatch({ type: "SET_SHOW_ACHIEVEMENT_NOTIFICATIONS", payload: show });
  }, []);

  const setShowRealityAttributeNotification = useCallback((show: boolean) => {
    dispatch({
      type: "SET_SHOW_REALITY_ATTRIBUTE_NOTIFICATION",
      payload: show,
    });
  }, []);

  const setExperimentalEndingEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_EXPERIMENTAL_ENDING_ENABLED", payload: enabled });
  }, []);
  const setExperimentalAdventureEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_EXPERIMENTAL_ADVENTURE_ENABLED", payload: enabled });
  }, []);
  const setExperimentalPromptExpanderEnabled = useCallback(
    (enabled: boolean) => {
      dispatch({
        type: "SET_EXPERIMENTAL_PROMPT_EXPANDER_ENABLED",
        payload: enabled,
      });
    },
    [],
  );
  const setPlayMemoryEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_PLAY_MEMORY_ENABLED", payload: enabled });
  }, []);
  const setPlayMemorySystemEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_PLAY_MEMORY_SYSTEM_ENABLED", payload: enabled });
  }, []);
  const setPlayMemoryUserEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_PLAY_MEMORY_USER_ENABLED", payload: enabled });
  }, []);
  const setConfirmFavoriteRemove = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_CONFIRM_FAVORITE_REMOVE", payload: enabled });
  }, []);

  const setSoundEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_SOUND_ENABLED", payload: enabled });
  }, []);

  const setSoundVolume = useCallback((volume: number) => {
    dispatch({ type: "SET_SOUND_VOLUME", payload: volume });
  }, []);

  const togglePanel = useCallback(() => {
    dispatch({ type: "TOGGLE_PANEL" });
  }, []);

  const setPanelOpen = useCallback((open: boolean) => {
    dispatch({ type: "SET_PANEL_OPEN", payload: open });
  }, []);

  const resetSettings = useCallback(() => {
    dispatch({ type: "RESET_SETTINGS" });
  }, []);

  const addPreciseReference = useCallback((ref: PreciseReference) => {
    dispatch({ type: "ADD_PRECISE_REFERENCE", payload: ref });
  }, []);

  const updatePreciseReference = useCallback(
    (id: string, updates: Partial<PreciseReference>) => {
      dispatch({
        type: "UPDATE_PRECISE_REFERENCE",
        payload: { id, ...updates },
      });
    },
    [],
  );

  const removePreciseReference = useCallback((id: string) => {
    dispatch({ type: "REMOVE_PRECISE_REFERENCE", payload: id });
  }, []);

  const clearPreciseReferences = useCallback(() => {
    dispatch({ type: "CLEAR_PRECISE_REFERENCES" });
  }, []);

  const setSelfProfile = useCallback((profile: SelfProfile | null) => {
    dispatch({ type: "SET_SELF_PROFILE", payload: profile });
  }, []);

  const loadSelfProfile = useCallback(async () => {
    try {
      const profile = await fetchSelfProfileApi();
      dispatch({ type: "SET_SELF_PROFILE", payload: profile });
    } catch (error) {
      console.warn("Failed to load self-profile:", error);
    }
  }, []);

  const setSeed = useCallback((seed: number | null) => {
    dispatch({ type: "SET_SEED", payload: seed });
  }, []);

  const setEnableSurroundingsImage = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_ENABLE_SURROUNDINGS_IMAGE", payload: enabled });
  }, []);

  const setSurroundingsIncludePeople = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_SURROUNDINGS_INCLUDE_PEOPLE", payload: enabled });
  }, []);

  const setAdventureEnableCompositeScene = useCallback((enabled: boolean) => {
    dispatch({
      type: "SET_ADVENTURE_ENABLE_COMPOSITE_SCENE",
      payload: enabled,
    });
  }, []);

  const setFontFamily = useCallback((fontFamily: string) => {
    dispatch({ type: "SET_FONT_FAMILY", payload: fontFamily });
  }, []);

  const setClothingColorConsistency = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_CLOTHING_COLOR_CONSISTENCY", payload: enabled });
  }, []);

  const setRespectClothingLayers = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_RESPECT_CLOTHING_LAYERS", payload: enabled });
  }, []);
  const setLinkChatToImage = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_LINK_CHAT_TO_IMAGE", payload: enabled });
  }, []);

  const setEnableMultiplePeople = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_ENABLE_MULTIPLE_PEOPLE", payload: enabled });
  }, []);

  const setMultiCharacterPanelEnabled = useCallback((enabled: boolean) => {
    dispatch({
      type: "SET_MULTI_CHARACTER_PANEL_ENABLED",
      payload: enabled,
    });
  }, []);

  const setNovelaiTextModel = useCallback(async (model: string) => {
    dispatch({ type: "SET_NOVELAI_TEXT_MODEL", payload: model });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novelai_text_model: model }),
      });
    } catch (error) {
      console.error("Failed to save novelai_text_model to backend:", error);
    }
  }, []);

  const setNovelaiTier = useCallback((tier: number | null) => {
    dispatch({ type: "SET_NOVELAI_TIER", payload: tier });
  }, []);

  const setNovelaiImageModel = useCallback(async (model: string) => {
    dispatch({ type: "SET_NOVELAI_IMAGE_MODEL", payload: model });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novelai_image_model: model }),
      });
    } catch (error) {
      console.error("Failed to save novelai_image_model to backend:", error);
    }
  }, []);

  const setNovelaiCuratedImageModel = useCallback(async (model: string) => {
    dispatch({ type: "SET_NOVELAI_CURATED_IMAGE_MODEL", payload: model });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novelai_curated_image_model: model }),
      });
    } catch (error) {
      console.error(
        "Failed to save novelai_curated_image_model to backend:",
        error,
      );
    }
  }, []);

  const setTtsEnabled = useCallback(async (enabled: boolean) => {
    dispatch({ type: "SET_TTS_ENABLED", payload: enabled });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_enabled: enabled }),
      });
    } catch (error) {
      console.error("Failed to save tts_enabled to backend:", error);
    }
  }, []);

  const setTtsUseGpu = useCallback(async (enabled: boolean) => {
    dispatch({ type: "SET_TTS_USE_GPU", payload: enabled });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_use_gpu: enabled }),
      });
    } catch (error) {
      console.error("Failed to save tts_use_gpu to backend:", error);
    }
  }, []);

  const setTtsEngineDir = useCallback(async (engineDir: string) => {
    dispatch({ type: "SET_TTS_ENGINE_DIR", payload: engineDir });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_engine_dir: engineDir }),
      });
    } catch (error) {
      console.error("Failed to save tts_engine_dir to backend:", error);
    }
  }, []);

  const setTtsEnginePort = useCallback(async (port: number) => {
    dispatch({ type: "SET_TTS_ENGINE_PORT", payload: port });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_engine_port: port }),
      });
    } catch (error) {
      console.error("Failed to save tts_engine_port to backend:", error);
    }
  }, []);

  const setTtsModelDir = useCallback(async (modelDir: string) => {
    dispatch({ type: "SET_TTS_MODEL_DIR", payload: modelDir });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_model_dir: modelDir }),
      });
    } catch (error) {
      console.error("Failed to save tts_model_dir to backend:", error);
    }
  }, []);

  const setTtsSpeakerId = useCallback(async (speakerId: string | null) => {
    dispatch({ type: "SET_TTS_SPEAKER_ID", payload: speakerId });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_speaker_id: speakerId ?? "" }),
      });
    } catch (error) {
      console.error("Failed to save tts_speaker_id to backend:", error);
    }
  }, []);

  const setTtsStyleId = useCallback(async (styleId: string | null) => {
    dispatch({ type: "SET_TTS_STYLE_ID", payload: styleId });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_style_id: styleId ?? "" }),
      });
    } catch (error) {
      console.error("Failed to save tts_style_id to backend:", error);
    }
  }, []);

  const setTtsOutputFormat = useCallback(async (format: "wav") => {
    dispatch({ type: "SET_TTS_OUTPUT_FORMAT", payload: format });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tts_output_format: format }),
      });
    } catch (error) {
      console.error("Failed to save tts_output_format to backend:", error);
    }
  }, []);

  const setRealWorldWeatherEnabled = useCallback(async (enabled: boolean) => {
    dispatch({ type: "SET_REAL_WORLD_WEATHER_ENABLED", payload: enabled });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ real_world_weather_enabled: enabled }),
      });
    } catch (error) {
      console.error(
        "Failed to save real_world_weather_enabled to backend:",
        error,
      );
    }
  }, []);

  const setRealWorldSearchEnabled = useCallback(async (enabled: boolean) => {
    dispatch({ type: "SET_REAL_WORLD_SEARCH_ENABLED", payload: enabled });
    try {
      await fetch("/api/settings/user", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ real_world_search_enabled: enabled }),
      });
    } catch (error) {
      console.error(
        "Failed to save real_world_search_enabled to backend:",
        error,
      );
    }
  }, []);

  const setHistoryLookbackCount = useCallback(async (count: number) => {
    const clamped = Math.max(5, Math.min(20, Math.trunc(count)));
    dispatch({ type: "SET_HISTORY_LOOKBACK_COUNT", payload: clamped });
    try {
      await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ history_lookback_count: clamped }),
      });
    } catch (error) {
      console.error("Failed to save history_lookback_count to backend:", error);
    }
  }, []);

  const setHistoryLookbackTarget = useCallback(
    (target: HistoryLookbackTarget, enabled: boolean) => {
      dispatch({
        type: "SET_HISTORY_LOOKBACK_TARGET",
        payload: { target, enabled },
      });
    },
    [],
  );

  const setMemoryText = useCallback((memoryText: string | null) => {
    dispatch({ type: "SET_MEMORY_TEXT", payload: memoryText });
  }, []);

  const loadMemoryText = useCallback(async () => {
    try {
      const memoryText = await fetchMemoryTextApi();
      dispatch({ type: "SET_MEMORY_TEXT", payload: memoryText });
    } catch (error) {
      console.warn("Failed to load memory text:", error);
    }
  }, []);

  // 現在のNSFW設定で実際に使われるNovelAI画像モデルとV5判定
  const effectiveNovelaiImageModel = state.nsfwMode
    ? state.novelaiImageModel
    : state.novelaiCuratedImageModel;
  const isNovelaiV5Active =
    state.imageProvider === "novelai" &&
    isV5ImageModel(effectiveNovelaiImageModel);

  const value: SettingsContextType = {
    state,
    setDifficulty,
    setBloomCalcMethod,
    setFeelingMode,
    setGenderCongruenceLlmEnabled,
    setLanguage,
    setNsfwMode,
    toggleNsfw,
    setImageProvider,
    setTotalCost,
    addTotalCost,
    resetTotalCost,
    setShowCost,
    setAnlasBalance,
    setDefaultInstructionType,
    setInpaintSettings,
    setInpaintMask,
    clearInpaintMask,
    toggleInpaint,
    setShowAchievementNotifications,
    setShowRealityAttributeNotification,
    setExperimentalEndingEnabled,
    setExperimentalAdventureEnabled,
    setExperimentalPromptExpanderEnabled,
    setPlayMemoryEnabled,
    setPlayMemorySystemEnabled,
    setPlayMemoryUserEnabled,
    setConfirmFavoriteRemove,
    setSoundEnabled,
    setSoundVolume,
    togglePanel,
    setPanelOpen,
    resetSettings,
    addPreciseReference,
    updatePreciseReference,
    removePreciseReference,
    clearPreciseReferences,
    selfProfile: state.selfProfile,
    setSelfProfile,
    loadSelfProfile,
    setSeed,
    setEnableSurroundingsImage,
    setSurroundingsIncludePeople,
    setAdventureEnableCompositeScene,
    setFontFamily,
    setClothingColorConsistency,
    setLinkChatToImage,
    setEnableMultiplePeople,
    setRespectClothingLayers,
    setMultiCharacterPanelEnabled,
    setNovelaiTextModel,
    setNovelaiTier,
    setNovelaiImageModel,
    setNovelaiCuratedImageModel,
    effectiveNovelaiImageModel,
    isNovelaiV5Active,
    setTtsEnabled,
    setTtsUseGpu,
    setTtsEngineDir,
    setTtsEnginePort,
    setTtsModelDir,
    setTtsSpeakerId,
    setTtsStyleId,
    setTtsOutputFormat,
    setRealWorldWeatherEnabled,
    setRealWorldSearchEnabled,
    setHistoryLookbackCount,
    setHistoryLookbackTarget,
    memoryText: state.memoryText,
    setMemoryText,
    loadMemoryText,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// Custom Hook
export function useSettings(): SettingsContextType {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
