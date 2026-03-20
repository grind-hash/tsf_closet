/**
 * SettingsContext - アプリケーション設定の管理
 * 007-chat-interactive-ux
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import type {
  InpaintSettings,
  InpaintMaskState,
  ChangeSettings,
  InstructionType,
  PreciseReference,
  AnlasBalance,
} from "../types";
import {
  DEFAULT_CHANGE_SETTINGS,
  DEFAULT_INPAINT_MASK_STATE,
  DEFAULT_INPAINT_SETTINGS,
} from "../types";
import { DEFAULT_LANGUAGE, type UiLanguage } from "../constants/language";
import type { SelfProfile } from "../apis/settings";
import { getSelfProfile as fetchSelfProfileApi } from "../apis/settings";
import i18n from "../i18n";

// 設定状態の型定義
interface SettingsState {
  // 難易度設定
  difficulty: "easy" | "normal" | "hard";
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

  // 変更設定
  changeSettings: ChangeSettings;

  // 通知設定
  showAchievementNotifications: boolean;
  showRealityAttributeNotification: boolean;
  experimentalEndingEnabled: boolean;

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

  // Font family setting
  fontFamily: string;

  // Clothing color consistency (experimental)
  clothingColorConsistency: boolean;

  // Chat-to-image linking: scroll chat on image navigation
  linkChatToImage: boolean;
}

// アクション型
type SettingsAction =
  | { type: "SET_DIFFICULTY"; payload: "easy" | "normal" | "hard" }
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
  | { type: "SET_CHANGE_SETTINGS"; payload: Partial<ChangeSettings> }
  | { type: "SET_SHOW_ACHIEVEMENT_NOTIFICATIONS"; payload: boolean }
  | { type: "SET_SHOW_REALITY_ATTRIBUTE_NOTIFICATION"; payload: boolean }
  | { type: "SET_EXPERIMENTAL_ENDING_ENABLED"; payload: boolean }
  | { type: "SET_SOUND_ENABLED"; payload: boolean }
  | { type: "SET_SOUND_VOLUME"; payload: number }
  | { type: "TOGGLE_PANEL" }
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
  | { type: "SET_FONT_FAMILY"; payload: string }
  | { type: "SET_CLOTHING_COLOR_CONSISTENCY"; payload: boolean }
  | { type: "SET_LINK_CHAT_TO_IMAGE"; payload: boolean };

// デフォルト状態
const defaultState: SettingsState = {
  difficulty: "normal",
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
  changeSettings: DEFAULT_CHANGE_SETTINGS,
  showAchievementNotifications: true,
  showRealityAttributeNotification: true,
  experimentalEndingEnabled: false,
  soundEnabled: true,
  soundVolume: 0.5,
  rightPanelOpen: false,
  preciseReferences: [],
  selfProfile: null,
  seed: null,
  enableSurroundingsImage: false,
  surroundingsIncludePeople: false,
  fontFamily: "system",
  clothingColorConsistency: false,
  linkChatToImage: false,
};

// Reducer
function settingsReducer(
  state: SettingsState,
  action: SettingsAction,
): SettingsState {
  switch (action.type) {
    case "SET_DIFFICULTY":
      return { ...state, difficulty: action.payload };
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
    case "SET_CHANGE_SETTINGS":
      return {
        ...state,
        changeSettings: { ...state.changeSettings, ...action.payload },
      };
    case "SET_SHOW_ACHIEVEMENT_NOTIFICATIONS":
      return { ...state, showAchievementNotifications: action.payload };
    case "SET_SHOW_REALITY_ATTRIBUTE_NOTIFICATION":
      return { ...state, showRealityAttributeNotification: action.payload };
    case "SET_EXPERIMENTAL_ENDING_ENABLED":
      return { ...state, experimentalEndingEnabled: action.payload };
    case "SET_SOUND_ENABLED":
      return { ...state, soundEnabled: action.payload };
    case "SET_SOUND_VOLUME":
      return { ...state, soundVolume: action.payload };
    case "TOGGLE_PANEL":
      return { ...state, rightPanelOpen: !state.rightPanelOpen };
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
    case "SET_FONT_FAMILY":
      return { ...state, fontFamily: action.payload };
    case "SET_CLOTHING_COLOR_CONSISTENCY":
      return { ...state, clothingColorConsistency: action.payload };
    case "SET_LINK_CHAT_TO_IMAGE":
      return { ...state, linkChatToImage: action.payload };
    default:
      return state;
  }
}

// Context型定義
interface SettingsContextType {
  state: SettingsState;
  setDifficulty: (difficulty: "easy" | "normal" | "hard") => void;
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
  setChangeSettings: (settings: Partial<ChangeSettings>) => void;
  setShowAchievementNotifications: (show: boolean) => void;
  setShowRealityAttributeNotification: (show: boolean) => void;
  setExperimentalEndingEnabled: (enabled: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setSoundVolume: (volume: number) => void;
  togglePanel: () => void;
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
  setFontFamily: (fontFamily: string) => void;
  setClothingColorConsistency: (enabled: boolean) => void;
  setLinkChatToImage: (enabled: boolean) => void;
}

// Context作成
const SettingsContext = createContext<SettingsContextType | null>(null);

// localStorage キー
const STORAGE_KEY = "app_settings";

// Lazy initializer: load settings from localStorage synchronously
// to avoid race condition where the save effect overwrites before dispatch is processed
function loadInitialState(initial: SettingsState): SettingsState {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    const legacyTotalCost = localStorage.getItem("api_total_cost");
    if (saved) {
      const parsed = JSON.parse(saved);
      // imageProviderはバックエンドから取得するため除外
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { imageProvider: _ignored, ...rest } = parsed;
      return {
        ...initial,
        ...rest,
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
              language: data.language ?? DEFAULT_LANGUAGE,
            },
          });
        }
      } catch (error) {
        console.warn("Failed to fetch user settings from backend:", error);
      }
    };
    fetchUserSettings();
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

  // 状態変更時にlocalStorageに保存（imageProviderは除外）
  // 初期化完了後のみ保存（初期状態での上書きを防ぐ）
  useEffect(() => {
    if (!isInitializedRef.current) return;
    try {
      /* eslint-disable @typescript-eslint/no-unused-vars */
      const {
        imageProvider: _ignored,
        preciseReferences: _ignored2,
        selfProfile: _ignored3,
        seed: _ignored4,
        anlasBalance: _ignored5,
        ...rest
      } = state;
      /* eslint-enable @typescript-eslint/no-unused-vars */
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

  const setChangeSettings = useCallback((settings: Partial<ChangeSettings>) => {
    dispatch({ type: "SET_CHANGE_SETTINGS", payload: settings });
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

  const setSoundEnabled = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_SOUND_ENABLED", payload: enabled });
  }, []);

  const setSoundVolume = useCallback((volume: number) => {
    dispatch({ type: "SET_SOUND_VOLUME", payload: volume });
  }, []);

  const togglePanel = useCallback(() => {
    dispatch({ type: "TOGGLE_PANEL" });
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

  const setFontFamily = useCallback((fontFamily: string) => {
    dispatch({ type: "SET_FONT_FAMILY", payload: fontFamily });
  }, []);

  const setClothingColorConsistency = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_CLOTHING_COLOR_CONSISTENCY", payload: enabled });
  }, []);

  const setLinkChatToImage = useCallback((enabled: boolean) => {
    dispatch({ type: "SET_LINK_CHAT_TO_IMAGE", payload: enabled });
  }, []);

  const value: SettingsContextType = {
    state,
    setDifficulty,
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
    setChangeSettings,
    setShowAchievementNotifications,
    setShowRealityAttributeNotification,
    setExperimentalEndingEnabled,
    setSoundEnabled,
    setSoundVolume,
    togglePanel,
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
    setFontFamily,
    setClothingColorConsistency,
    setLinkChatToImage,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// Custom Hook
// eslint-disable-next-line react-refresh/only-export-components
export function useSettings(): SettingsContextType {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
