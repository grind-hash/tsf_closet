/**
 * PromptExpanderContext - Prompt Expander 画面の状態管理
 *
 * セッション/エントリ一覧、PE ローカル設定、コンポーザ（入力欄）の状態、
 * 欄ごとの拡張（→ インライン確認 → 欄へ反映 / そのまま生成）、
 * V5 利用上限の確認ゲートをまとめて保持する。
 * AdventureProvider と同様に /prompt-expander 配下でのみマウントされる。
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { fetchAnlasBalance } from "../apis/anlas";
import { getMemoryText } from "../apis/memory";
import {
  createPromptExpanderSession,
  deletePromptExpanderEntry,
  deletePromptExpanderSession,
  draftMangaScript,
  expandPrompt,
  fetchPromptExpanderSession,
  fetchPromptExpanderSessions,
  fetchPromptExpanderSettings,
  generatePromptExpanderImage,
  PromptExpanderApiError,
  type PromptExpanderEntry,
  type PromptExpanderGenerateRequest,
  type PromptExpanderMangaOptions,
  type PromptExpanderSession,
  type PromptExpanderSettings,
  type PromptExpanderSettingsPatch,
  type PromptExpanderSettingsResponse,
  type PromptExpanderSuggestion,
  type PromptExpanderTextModelOption,
  promptExpanderImageUrl,
  renamePromptExpanderSession,
  suggestCharacterPrompts,
  updatePromptExpanderSettings,
  uploadPromptExpanderImage,
} from "../apis/promptExpander";
import {
  isV5ImageModel,
  V5_USAGE_WARN_SUPPRESSED_KEY,
} from "../constants/novelaiImageModels";
import {
  DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
  getMaxCharacterPrompts,
  NOVELAI_TEXT_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_SIZES,
  type PromptExpanderImageSize,
  type PromptExpandMode,
  supportsMangaMode,
} from "../constants/promptExpander";
import type { AnlasBalance } from "../types";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

// ----------------------------------------------------------------
// 型
// ----------------------------------------------------------------

export type PromptExpanderSourceType = "history" | "entry" | "upload";

/** 拡張の対象欄 */
export type PromptExpanderExpansionTarget = "positive" | "negative";

/** コンポーザで選択中の生成元画像 */
export interface PromptExpanderSource {
  kind: PromptExpanderSourceType;
  historyId?: string;
  entryId?: string;
  /** kind="upload" のときの data URL（履歴に残さないアップロード） */
  uploadDataUrl?: string;
  thumbnailUrl: string;
  label: string;
}

/** LLM 拡張の結果（欄の直下のインラインカードで編集可能） */
export interface PromptExpanderPendingExpansion {
  target: PromptExpanderExpansionTarget;
  /** 拡張時に選ばれていたモード（履歴メタデータ用に保持する） */
  mode: PromptExpandMode;
  /** 拡張に使った指示文（target="positive" のとき） */
  instruction: string | null;
  positivePrompt: string | null;
  characterPrompts: string[] | null;
  negativePrompt: string | null;
}

/** 正プロンプト欄の内容が拡張結果由来であることを示す（履歴メタデータ用） */
export interface PromptExpanderPositiveOrigin {
  mode: PromptExpandMode;
  instruction: string;
}

/** ネガティブ欄の内容が拡張結果由来であることを示す */
export interface PromptExpanderNegativeOrigin {
  mode: PromptExpandMode;
}

/** 欄の近くに出す拡張エラー */
export interface PromptExpanderExpansionError {
  target: PromptExpanderExpansionTarget;
  /** API の detail.code（memory_empty / llm_failed 等）または FE 側の検証コード */
  code: string | null;
  message: string;
}

export interface PromptExpanderOptions {
  textModelOptions: PromptExpanderTextModelOption[];
  imageModelOptions: string[];
  maxCharacterPrompts: Record<string, number>;
  imageSizes: PromptExpanderImageSize[];
  novelaiConfigured: boolean;
}

export interface PromptExpanderUploadOptions {
  keepAsEntry: boolean;
  useAsSource: boolean;
  note?: string;
}

interface PromptExpanderContextValue {
  // 一覧/詳細
  sessions: PromptExpanderSession[];
  activeSession: PromptExpanderSession | null;
  entries: PromptExpanderEntry[];
  // 設定
  settings: PromptExpanderSettings;
  settingsLoaded: boolean;
  options: PromptExpanderOptions;
  maxCharacterPrompts: number;
  // ローディング/エラー
  loadingSessions: boolean;
  loadingSession: boolean;
  expanding: boolean;
  expandingTarget: PromptExpanderExpansionTarget | null;
  /** 「あらすじからネームを下書き」の実行中 */
  draftingScript: boolean;
  /** 直近のネーム下書き（元の文と結果。欄が結果のままなら「元の文に戻す」が使える） */
  scriptDraftBackup: { source: string; script: string } | null;
  generating: boolean;
  uploading: boolean;
  suggesting: boolean;
  error: string | null;
  clearError: () => void;
  expansionError: PromptExpanderExpansionError | null;
  clearExpansionError: () => void;
  // コンポーザ
  source: PromptExpanderSource | null;
  positiveText: string;
  positiveMode: PromptExpandMode;
  positiveOrigin: PromptExpanderPositiveOrigin | null;
  characterMode: boolean;
  characterSlots: string[];
  characterSlotsOverCap: boolean;
  /** 漫画モードが実際に効く状態か（設定 ON かつ V5 系モデル） */
  mangaActive: boolean;
  /** 正プロンプト拡張に実際に使うモード（漫画モード中は "tags" 固定） */
  effectivePositiveMode: PromptExpandMode;
  negativeText: string;
  negativeMode: PromptExpandMode;
  negativeOrigin: PromptExpanderNegativeOrigin | null;
  pendingExpansion: PromptExpanderPendingExpansion | null;
  pendingUsageWarn: PromptExpanderGenerateRequest | null;
  anlas: AnlasBalance | null;
  canGenerate: boolean;
  generateDisabledReason: string | null;
  // アクション: セッション
  loadSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<PromptExpanderSession | null>;
  renameSession: (id: string, title: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  openSession: (id: string) => Promise<void>;
  // アクション: 設定
  loadSettings: () => Promise<void>;
  updateSettings: (patch: PromptExpanderSettingsPatch) => Promise<void>;
  updateSettingsDebounced: (patch: PromptExpanderSettingsPatch) => void;
  importGlobalMemory: () => Promise<boolean>;
  // アクション: コンポーザ
  setSource: (source: PromptExpanderSource | null) => void;
  clearSource: () => void;
  setPositiveText: (text: string) => void;
  setPositiveMode: (mode: PromptExpandMode) => void;
  setCharacterMode: (on: boolean) => void;
  addCharacterSlot: (text?: string) => void;
  updateCharacterSlot: (index: number, text: string) => void;
  removeCharacterSlot: (index: number) => void;
  setNegativeText: (text: string) => void;
  setNegativeMode: (mode: PromptExpandMode) => void;
  uploadImage: (
    file: File,
    options: PromptExpanderUploadOptions,
  ) => Promise<void>;
  /** 正プロンプト欄の指示を拡張し、欄の直下に確認カードを出す */
  expandPositive: () => Promise<void>;
  /** ネガティブ欄の内容を拡張し、欄の直下に確認カードを出す */
  expandNegative: () => Promise<void>;
  /** 正プロンプト欄のあらすじを、記法付きのネームに LLM で書き換える（漫画モード） */
  draftScript: () => Promise<void>;
  /** ネーム下書き前の文に戻す */
  undoScriptDraft: () => void;
  /** 編集済みの拡張結果を欄へ書き戻してカードを閉じる */
  applyExpansion: (edited: PromptExpanderPendingExpansion) => void;
  /** 編集済みの拡張結果からそのまま生成する（欄も確認カードも変更しない） */
  generateFromExpansion: (
    edited: PromptExpanderPendingExpansion,
  ) => Promise<void>;
  discardExpansion: () => void;
  /** 欄の内容をそのまま生成する */
  runGenerate: () => Promise<void>;
  confirmUsageWarn: (suppress: boolean) => Promise<void>;
  cancelUsageWarn: () => void;
  /** 拡張ありのエントリは原文を欄へ戻し、変換結果を確認カードとして再現する */
  restoreEntry: (entry: PromptExpanderEntry) => void;
  /** エントリのプロンプト・設定のまま、seed だけ新規（ランダム）で生成し直す */
  regenerateEntry: (entry: PromptExpanderEntry) => Promise<void>;
  selectEntryAsSource: (entry: PromptExpanderEntry) => void;
  deleteEntry: (id: string) => Promise<void>;
  suggestCharacters: (
    count: number,
    mode: PromptExpandMode,
  ) => Promise<PromptExpanderSuggestion[]>;
}

/** キャラクタープロンプトの ON/OFF は作業欄の状態だが、セッション切替や再読み込みをまたいで保つ */
export const PROMPT_EXPANDER_CHARACTER_MODE_KEY =
  "prompt_expander_character_mode";

function readPersistedCharacterMode(): boolean {
  try {
    return localStorage.getItem(PROMPT_EXPANDER_CHARACTER_MODE_KEY) === "true";
  } catch {
    return false;
  }
}

function writePersistedCharacterMode(on: boolean) {
  try {
    localStorage.setItem(PROMPT_EXPANDER_CHARACTER_MODE_KEY, String(on));
  } catch {
    // localStorage が使えない環境では保持しない
  }
}

const DEFAULT_SETTINGS: PromptExpanderSettings = {
  text_model: NOVELAI_TEXT_MODEL_OPTIONS[0],
  image_model: DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
  image_size: "portrait",
  i2i_strength: 0.5,
  i2i_noise: 0,
  seed: null,
  restore_seed: false,
  memory_text: "",
  use_memory: false,
  confirm_before_generate: true,
  inherit_source_prompts: true,
  manga_mode: false,
  manga_panel_count: 0,
  manga_layout: "auto",
  manga_dialogue: true,
  manga_text_language: "auto",
  manga_sound_effects: true,
  manga_reading_direction: "rtl",
  manga_narration: false,
};

const DEFAULT_OPTIONS: PromptExpanderOptions = {
  textModelOptions: NOVELAI_TEXT_MODEL_OPTIONS.map((id) => ({
    id,
    label: id,
  })),
  imageModelOptions: [...PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS],
  maxCharacterPrompts: {},
  imageSizes: [...PROMPT_EXPANDER_IMAGE_SIZES],
  novelaiConfigured: true,
};

const SETTINGS_DEBOUNCE_MS = 400;

const PromptExpanderContext = createContext<
  PromptExpanderContextValue | undefined
>(undefined);

function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

function isUsageExhausted(anlas: AnlasBalance | null): boolean {
  const usage = anlas?.usage;
  if (!usage) return false;
  return usage.percent <= 0 || usage.isNegative;
}

function readUsageWarnSuppressed(): boolean {
  try {
    return sessionStorage.getItem(V5_USAGE_WARN_SUPPRESSED_KEY) === "true";
  } catch {
    return false;
  }
}

function applySettingsResponse(
  payload: PromptExpanderSettingsResponse,
  setSettings: (s: PromptExpanderSettings) => void,
  setOptions: (o: PromptExpanderOptions) => void,
) {
  setSettings({ ...DEFAULT_SETTINGS, ...payload.settings });
  setOptions({
    textModelOptions:
      payload.text_model_options?.length > 0
        ? payload.text_model_options
        : DEFAULT_OPTIONS.textModelOptions,
    imageModelOptions:
      payload.image_model_options?.length > 0
        ? payload.image_model_options
        : DEFAULT_OPTIONS.imageModelOptions,
    maxCharacterPrompts: payload.max_character_prompts ?? {},
    imageSizes:
      payload.image_sizes?.length > 0
        ? payload.image_sizes
        : DEFAULT_OPTIONS.imageSizes,
    novelaiConfigured: payload.novelai_configured !== false,
  });
}

/** 生成ペイロードの元になる欄の値（拡張結果からの生成時は一部を差し替える） */
interface GenerateFields {
  positive: string;
  characterMode: boolean;
  slots: string[];
  negative: string;
  positiveOrigin: PromptExpanderPositiveOrigin | null;
  negativeOrigin: PromptExpanderNegativeOrigin | null;
}

// ----------------------------------------------------------------
// Provider
// ----------------------------------------------------------------

export function PromptExpanderProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { state: settingsState, setAnlasBalance } = useSettings();
  const { showNotification } = useNotification();
  const imageProvider = settingsState.imageProvider;
  const language = settingsState.language;
  const globalAnlas = settingsState.anlasBalance;

  // 一覧/詳細
  const [sessions, setSessions] = useState<PromptExpanderSession[]>([]);
  const [activeSession, setActiveSession] =
    useState<PromptExpanderSession | null>(null);
  const [entries, setEntries] = useState<PromptExpanderEntry[]>([]);

  // 設定
  const [settings, setSettings] =
    useState<PromptExpanderSettings>(DEFAULT_SETTINGS);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [options, setOptions] =
    useState<PromptExpanderOptions>(DEFAULT_OPTIONS);

  // ローディング/エラー
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [expandingTarget, setExpandingTarget] =
    useState<PromptExpanderExpansionTarget | null>(null);
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [draftingScript, setDraftingScript] = useState(false);
  const [scriptDraftBackup, setScriptDraftBackup] = useState<{
    source: string;
    script: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expansionError, setExpansionError] =
    useState<PromptExpanderExpansionError | null>(null);

  // コンポーザ
  const [source, setSourceState] = useState<PromptExpanderSource | null>(null);
  const [positiveText, setPositiveText] = useState("");
  const [positiveMode, setPositiveMode] = useState<PromptExpandMode>("tags");
  const [positiveOrigin, setPositiveOrigin] =
    useState<PromptExpanderPositiveOrigin | null>(null);
  const [characterMode, setCharacterModeState] = useState(
    readPersistedCharacterMode,
  );
  // 復元・欄へ反映など内部からの変更も含めて localStorage に保つ
  const setCharacterMode = useCallback((on: boolean) => {
    setCharacterModeState(on);
    writePersistedCharacterMode(on);
  }, []);
  const [characterSlots, setCharacterSlots] = useState<string[]>([]);
  const [negativeText, setNegativeText] = useState("");
  const [negativeMode, setNegativeMode] = useState<PromptExpandMode>("tags");
  const [negativeOrigin, setNegativeOrigin] =
    useState<PromptExpanderNegativeOrigin | null>(null);
  const [pendingExpansion, setPendingExpansion] =
    useState<PromptExpanderPendingExpansion | null>(null);
  const [pendingUsageWarn, setPendingUsageWarn] =
    useState<PromptExpanderGenerateRequest | null>(null);
  const [anlas, setAnlas] = useState<AnlasBalance | null>(globalAnlas);

  const expanding = expandingTarget !== null;

  const clearError = useCallback(() => setError(null), []);
  const clearExpansionError = useCallback(() => setExpansionError(null), []);

  const reportError = useCallback(
    (title: string, err: unknown) => {
      const message = toErrorMessage(err);
      setError(message);
      showNotification("error", title, message);
    },
    [showNotification],
  );

  // 欄が空になったら「拡張結果由来」の印は意味を失うので外す
  useEffect(() => {
    if (!positiveText.trim()) setPositiveOrigin(null);
  }, [positiveText]);
  useEffect(() => {
    if (!negativeText.trim()) setNegativeOrigin(null);
  }, [negativeText]);

  // ---- Anlas ----------------------------------------------------

  // グローバル残高が後から入った場合は PE 側へも反映する（PE 側が未取得のときのみ）
  useEffect(() => {
    if (globalAnlas && !anlas) {
      setAnlas(globalAnlas);
    }
  }, [globalAnlas, anlas]);

  // マウント時の一回だけ取得する
  // biome-ignore lint/correctness/useExhaustiveDependencies: 初回のみ
  useEffect(() => {
    if (anlas) return;
    let cancelled = false;
    fetchAnlasBalance().then((balance) => {
      if (!cancelled && balance) {
        setAnlas(balance);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyAnlas = useCallback(
    (balance: AnlasBalance | null) => {
      if (!balance) return;
      setAnlas(balance);
      if (imageProvider === "novelai") {
        setAnlasBalance(balance);
      }
    },
    [imageProvider, setAnlasBalance],
  );

  // ---- 設定 -----------------------------------------------------

  const loadSettings = useCallback(async () => {
    try {
      const payload = await fetchPromptExpanderSettings();
      applySettingsResponse(payload, setSettings, setOptions);
      setSettingsLoaded(true);
    } catch (err) {
      reportError("Prompt Expander", err);
    }
  }, [reportError]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const updateSettings = useCallback(
    async (patch: PromptExpanderSettingsPatch) => {
      // 楽観的に反映してから保存する
      setSettings((prev) => ({ ...prev, ...patch }));
      try {
        const payload = await updatePromptExpanderSettings(patch);
        applySettingsResponse(payload, setSettings, setOptions);
      } catch (err) {
        reportError("Prompt Expander", err);
      }
    },
    [reportError],
  );

  // スライダー/数値入力用: 画面には即反映し、PUT は一定時間まとめて送る
  const debounceTimerRef = useRef<number | null>(null);
  const pendingPatchRef = useRef<PromptExpanderSettingsPatch>({});
  const updateSettingsDebounced = useCallback(
    (patch: PromptExpanderSettingsPatch) => {
      setSettings((prev) => ({ ...prev, ...patch }));
      pendingPatchRef.current = { ...pendingPatchRef.current, ...patch };
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = null;
        const merged = pendingPatchRef.current;
        pendingPatchRef.current = {};
        updatePromptExpanderSettings(merged)
          .then((payload) =>
            applySettingsResponse(payload, setSettings, setOptions),
          )
          .catch((err) => reportError("Prompt Expander", err));
      }, SETTINGS_DEBOUNCE_MS);
    },
    [reportError],
  );

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const importGlobalMemory = useCallback(async (): Promise<boolean> => {
    try {
      const text = await getMemoryText();
      if (!text?.trim()) {
        return false;
      }
      await updateSettings({ memory_text: text });
      return true;
    } catch (err) {
      reportError("Prompt Expander", err);
      return false;
    }
  }, [reportError, updateSettings]);

  // ---- セッション -----------------------------------------------

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const list = await fetchPromptExpanderSessions();
      setSessions(list);
    } catch (err) {
      reportError("Prompt Expander", err);
    } finally {
      setLoadingSessions(false);
    }
  }, [reportError]);

  const createSession = useCallback(
    async (title?: string) => {
      try {
        const session = await createPromptExpanderSession(
          title?.trim() || undefined,
        );
        setSessions((prev) => [session, ...prev]);
        navigate(`/prompt-expander/${session.id}`);
        return session;
      } catch (err) {
        reportError("Prompt Expander", err);
        return null;
      }
    },
    [navigate, reportError],
  );

  const renameSession = useCallback(
    async (id: string, title: string) => {
      try {
        const updated = await renamePromptExpanderSession(id, title);
        setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
        setActiveSession((prev) => (prev?.id === id ? updated : prev));
      } catch (err) {
        reportError("Prompt Expander", err);
      }
    },
    [reportError],
  );

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await deletePromptExpanderSession(id);
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (activeSession?.id === id) {
          setActiveSession(null);
          setEntries([]);
          navigate("/prompt-expander");
        }
      } catch (err) {
        reportError("Prompt Expander", err);
      }
    },
    [activeSession?.id, navigate, reportError],
  );

  const openSession = useCallback(
    async (id: string) => {
      setLoadingSession(true);
      try {
        const detail = await fetchPromptExpanderSession(id);
        setActiveSession(detail.session);
        setEntries(detail.entries);
        setSessions((prev) => {
          const exists = prev.some((s) => s.id === detail.session.id);
          return exists
            ? prev.map((s) => (s.id === detail.session.id ? detail.session : s))
            : [detail.session, ...prev];
        });
      } catch (err) {
        setActiveSession(null);
        setEntries([]);
        reportError("Prompt Expander", err);
      } finally {
        setLoadingSession(false);
      }
    },
    [reportError],
  );

  const bumpSessionEntryCount = useCallback(
    (sessionId: string, delta: number, thumbnailUrl?: string | null) => {
      const apply = (s: PromptExpanderSession): PromptExpanderSession => ({
        ...s,
        entry_count: Math.max(0, s.entry_count + delta),
        thumbnail_url:
          thumbnailUrl !== undefined ? thumbnailUrl : s.thumbnail_url,
        updated_at: new Date().toISOString(),
      });
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? apply(s) : s)),
      );
      setActiveSession((prev) =>
        prev && prev.id === sessionId ? apply(prev) : prev,
      );
    },
    [],
  );

  // ---- コンポーザ -----------------------------------------------

  const maxCharacterPrompts =
    options.maxCharacterPrompts[settings.image_model] ??
    getMaxCharacterPrompts(settings.image_model);
  const characterSlotsOverCap =
    characterMode && characterSlots.length > maxCharacterPrompts;
  // 漫画モードは V5 系モデルでだけ効く（V4.5 では設定を残したまま無効）
  const mangaActive =
    settings.manga_mode && supportsMangaMode(settings.image_model);
  // 漫画モード中はコマ説明・外見を英語で組み立てるため、正プロンプトの拡張モードは
  // タグ扱いに固定する（日本語の説明文は画像内にナレーションとして描かれてしまう）
  const effectivePositiveMode: PromptExpandMode = mangaActive
    ? "tags"
    : positiveMode;
  const mangaRequest = useMemo<PromptExpanderMangaOptions>(
    () => ({
      panel_count: settings.manga_panel_count,
      layout: settings.manga_layout,
      dialogue: settings.manga_dialogue,
      text_language: settings.manga_text_language,
      sound_effects: settings.manga_sound_effects,
      reading_direction: settings.manga_reading_direction,
      narration: settings.manga_narration,
    }),
    [
      settings.manga_dialogue,
      settings.manga_layout,
      settings.manga_narration,
      settings.manga_panel_count,
      settings.manga_reading_direction,
      settings.manga_sound_effects,
      settings.manga_text_language,
    ],
  );

  const setSource = useCallback((next: PromptExpanderSource | null) => {
    setSourceState(next);
  }, []);
  const clearSource = useCallback(() => setSourceState(null), []);

  const addCharacterSlot = useCallback(
    (text: string = "") => {
      setCharacterSlots((prev) =>
        prev.length >= maxCharacterPrompts ? prev : [...prev, text],
      );
    },
    [maxCharacterPrompts],
  );
  const updateCharacterSlot = useCallback((index: number, text: string) => {
    setCharacterSlots((prev) =>
      prev.map((slot, i) => (i === index ? text : slot)),
    );
  }, []);
  const removeCharacterSlot = useCallback((index: number) => {
    setCharacterSlots((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const selectEntryAsSource = useCallback((entry: PromptExpanderEntry) => {
    setSourceState({
      kind: "entry",
      entryId: entry.id,
      thumbnailUrl: promptExpanderImageUrl(entry),
      label: entry.instruction || entry.final_prompt || entry.id,
    });
  }, []);

  const uploadImage = useCallback(
    async (file: File, uploadOptions: PromptExpanderUploadOptions) => {
      if (!uploadOptions.keepAsEntry && !uploadOptions.useAsSource) return;
      setUploading(true);
      try {
        const dataUrl = await readFileAsDataUrl(file);
        if (uploadOptions.keepAsEntry) {
          if (!activeSession) {
            throw new Error("session_not_selected");
          }
          const entry = await uploadPromptExpanderImage(
            activeSession.id,
            dataUrl,
            uploadOptions.note,
          );
          setEntries((prev) => [entry, ...prev]);
          bumpSessionEntryCount(activeSession.id, 1, entry.image_url);
          if (uploadOptions.useAsSource) {
            setSourceState({
              kind: "entry",
              entryId: entry.id,
              thumbnailUrl: promptExpanderImageUrl(entry),
              label: uploadOptions.note?.trim() || file.name,
            });
          }
        } else if (uploadOptions.useAsSource) {
          setSourceState({
            kind: "upload",
            uploadDataUrl: dataUrl,
            thumbnailUrl: dataUrl,
            label: uploadOptions.note?.trim() || file.name,
          });
        }
      } catch (err) {
        reportError("Prompt Expander", err);
      } finally {
        setUploading(false);
      }
    },
    [activeSession, bumpSessionEntryCount, reportError],
  );

  // 生成に渡す最終ペイロードを組み立てる
  const buildGeneratePayload = useCallback(
    (fields: GenerateFields): PromptExpanderGenerateRequest => {
      const slots = fields.characterMode
        ? fields.slots.map((s) => s.trim()).filter((s) => s.length > 0)
        : [];
      const payload: PromptExpanderGenerateRequest = {
        prompt: fields.positive.trim(),
        negative_prompt: fields.negative.trim(),
        character_prompts: slots,
        character_mode: fields.characterMode,
        instruction: fields.positiveOrigin?.instruction ?? null,
        positive_expand_mode: fields.positiveOrigin?.mode ?? "off",
        negative_expand_mode: fields.negativeOrigin?.mode ?? "off",
        image_model: settings.image_model,
        text_model: settings.text_model,
        image_size: settings.image_size,
        source_kind: source?.kind ?? "none",
        manga_mode: mangaActive,
        manga_panel_count: mangaActive ? settings.manga_panel_count : null,
      };
      if (settings.seed !== null && settings.seed !== undefined) {
        payload.seed = settings.seed;
      }
      if (source) {
        payload.i2i_strength = settings.i2i_strength;
        payload.i2i_noise = settings.i2i_noise;
        if (source.kind === "history") {
          payload.source_history_id = source.historyId;
        } else if (source.kind === "entry") {
          payload.source_entry_id = source.entryId;
        } else if (source.kind === "upload") {
          payload.source_image = source.uploadDataUrl;
        }
      }
      return payload;
    },
    [mangaActive, settings, source],
  );

  // 確認ゲートを通過した後の実際の生成リクエスト
  const postGenerate = useCallback(
    async (payload: PromptExpanderGenerateRequest) => {
      if (!activeSession) return;
      setGenerating(true);
      setError(null);
      try {
        const resp = await generatePromptExpanderImage(
          activeSession.id,
          payload,
        );
        setEntries((prev) => [resp.entry, ...prev]);
        bumpSessionEntryCount(activeSession.id, 1, resp.entry.image_url);
        applyAnlas(resp.anlas);
      } catch (err) {
        reportError("Prompt Expander", err);
      } finally {
        setGenerating(false);
      }
    },
    [activeSession, applyAnlas, bumpSessionEntryCount, reportError],
  );

  const generate = useCallback(
    async (payload: PromptExpanderGenerateRequest) => {
      if (
        isV5ImageModel(payload.image_model) &&
        isUsageExhausted(anlas) &&
        !readUsageWarnSuppressed()
      ) {
        setPendingUsageWarn(payload);
        return;
      }
      await postGenerate(payload);
    },
    [anlas, postGenerate],
  );

  // 生成前の共通検証（理由コードを返す。null なら生成可）
  const validateForGenerate = useCallback(
    (positive: string, slots: string[], withCharacters: boolean) => {
      if (!activeSession) return "session_not_selected";
      if (!positive.trim()) return "empty_prompt";
      if (withCharacters && slots.length > maxCharacterPrompts) {
        return "too_many_characters";
      }
      return null;
    },
    [activeSession, maxCharacterPrompts],
  );

  const runGenerate = useCallback(async () => {
    const reason = validateForGenerate(
      positiveText,
      characterSlots,
      characterMode,
    );
    if (reason) {
      setError(reason);
      return;
    }
    setError(null);
    await generate(
      buildGeneratePayload({
        positive: positiveText,
        characterMode,
        slots: characterSlots,
        negative: negativeText,
        positiveOrigin,
        negativeOrigin,
      }),
    );
  }, [
    buildGeneratePayload,
    characterMode,
    characterSlots,
    generate,
    negativeOrigin,
    negativeText,
    positiveOrigin,
    positiveText,
    validateForGenerate,
  ]);

  // ---- 拡張 -----------------------------------------------------

  const sourceFields = useMemo(
    () => ({
      source_kind:
        source?.kind === "history" || source?.kind === "entry"
          ? source.kind
          : ("none" as const),
      source_history_id:
        source?.kind === "history" ? source.historyId : undefined,
      source_entry_id: source?.kind === "entry" ? source.entryId : undefined,
    }),
    [source],
  );

  const failExpansion = useCallback(
    (target: PromptExpanderExpansionTarget, err: unknown) => {
      if (err instanceof PromptExpanderApiError) {
        setExpansionError({ target, code: err.code, message: err.message });
      } else {
        setExpansionError({ target, code: null, message: toErrorMessage(err) });
      }
    },
    [],
  );

  const expandPositive = useCallback(async () => {
    const instruction = positiveText.trim();
    if (!instruction) {
      setExpansionError({
        target: "positive",
        code: "empty_instruction",
        message: "empty_instruction",
      });
      return;
    }
    setExpansionError(null);
    setPendingExpansion(null);
    setExpandingTarget("positive");
    try {
      const resp = await expandPrompt({
        instruction,
        expand_positive: true,
        positive_mode: effectivePositiveMode,
        character_mode: characterMode,
        expand_negative: false,
        negative_mode: negativeMode,
        image_model: settings.image_model,
        text_model: settings.text_model,
        language,
        ...sourceFields,
        inherit_source_prompts: settings.inherit_source_prompts,
        // 正プロンプト欄は「指示」そのものなので「現在のプロンプト」としては渡さない
        // （保持すべき現在値は参照元エントリから継承する）。
        // キャラクタースロットは入力済みの現在値として渡す
        current_character_prompts: characterMode ? characterSlots : [],
        manga_mode: mangaActive,
        ...(mangaActive ? { manga: mangaRequest } : {}),
      });
      setPendingExpansion({
        target: "positive",
        mode: effectivePositiveMode,
        instruction,
        positivePrompt: resp.positive_prompt ?? "",
        characterPrompts: characterMode ? resp.character_prompts : null,
        negativePrompt: null,
      });
    } catch (err) {
      failExpansion("positive", err);
    } finally {
      setExpandingTarget(null);
    }
  }, [
    characterMode,
    characterSlots,
    effectivePositiveMode,
    failExpansion,
    language,
    mangaActive,
    mangaRequest,
    negativeMode,
    positiveText,
    settings.image_model,
    settings.inherit_source_prompts,
    settings.text_model,
    sourceFields,
  ]);

  const draftScript = useCallback(async () => {
    const synopsis = positiveText.trim();
    if (!synopsis) {
      setExpansionError({
        target: "positive",
        code: "empty_instruction",
        message: "empty_instruction",
      });
      return;
    }
    setExpansionError(null);
    setDraftingScript(true);
    try {
      const resp = await draftMangaScript({
        instruction: synopsis,
        image_model: settings.image_model,
        text_model: settings.text_model,
        language,
        manga: mangaRequest,
      });
      // 欄をネームで置き換える。元の文は「元の文に戻す」用に保持する
      setScriptDraftBackup({ source: positiveText, script: resp.script });
      setPositiveText(resp.script);
      setPositiveOrigin(null);
    } catch (err) {
      failExpansion("positive", err);
    } finally {
      setDraftingScript(false);
    }
  }, [
    failExpansion,
    language,
    mangaRequest,
    positiveText,
    settings.image_model,
    settings.text_model,
  ]);

  const undoScriptDraft = useCallback(() => {
    if (!scriptDraftBackup) return;
    setPositiveText(scriptDraftBackup.source);
    setScriptDraftBackup(null);
  }, [scriptDraftBackup]);

  const expandNegative = useCallback(async () => {
    const instruction = negativeText.trim();
    if (!instruction) {
      setExpansionError({
        target: "negative",
        code: "empty_instruction",
        message: "empty_instruction",
      });
      return;
    }
    setExpansionError(null);
    setPendingExpansion(null);
    setExpandingTarget("negative");
    try {
      const resp = await expandPrompt({
        // ネガティブ欄の内容を指示として渡す（正プロンプトは拡張しない）
        instruction,
        expand_positive: false,
        positive_mode: positiveMode,
        character_mode: characterMode,
        expand_negative: true,
        negative_mode: negativeMode,
        negative_instruction: instruction,
        image_model: settings.image_model,
        text_model: settings.text_model,
        language,
        ...sourceFields,
        inherit_source_prompts: settings.inherit_source_prompts,
        current_character_prompts: characterMode ? characterSlots : [],
      });
      setPendingExpansion({
        target: "negative",
        mode: negativeMode,
        instruction: null,
        positivePrompt: null,
        characterPrompts: null,
        negativePrompt: resp.negative_prompt ?? "",
      });
    } catch (err) {
      failExpansion("negative", err);
    } finally {
      setExpandingTarget(null);
    }
  }, [
    characterMode,
    characterSlots,
    failExpansion,
    language,
    negativeMode,
    negativeText,
    positiveMode,
    settings.image_model,
    settings.inherit_source_prompts,
    settings.text_model,
    sourceFields,
  ]);

  const applyExpansion = useCallback(
    (edited: PromptExpanderPendingExpansion) => {
      if (edited.target === "positive") {
        setPositiveText(edited.positivePrompt ?? "");
        if (edited.characterPrompts && edited.characterPrompts.length > 0) {
          setCharacterSlots(edited.characterPrompts);
          setCharacterMode(true);
        }
        setPositiveOrigin(
          edited.instruction
            ? { mode: edited.mode, instruction: edited.instruction }
            : null,
        );
      } else {
        setNegativeText(edited.negativePrompt ?? "");
        setNegativeOrigin({ mode: edited.mode });
      }
      setPendingExpansion(null);
      setExpansionError(null);
    },
    [setCharacterMode],
  );

  const generateFromExpansion = useCallback(
    async (edited: PromptExpanderPendingExpansion) => {
      let fields: GenerateFields;
      if (edited.target === "positive") {
        const slots = edited.characterPrompts ?? characterSlots;
        const withCharacters =
          characterMode ||
          (edited.characterPrompts !== null &&
            edited.characterPrompts.length > 0);
        // 原文はクリック時点の入力欄の内容を優先する（拡張後に手直しした分も残す）。
        // 欄が空なら拡張時のスナップショットへ戻す
        const liveInstruction =
          positiveText.trim() || edited.instruction || null;
        fields = {
          positive: edited.positivePrompt ?? "",
          characterMode: withCharacters,
          slots,
          negative: negativeText,
          positiveOrigin: liveInstruction
            ? { mode: edited.mode, instruction: liveInstruction }
            : null,
          negativeOrigin,
        };
      } else {
        fields = {
          positive: positiveText,
          characterMode,
          slots: characterSlots,
          negative: edited.negativePrompt ?? "",
          positiveOrigin,
          negativeOrigin: { mode: edited.mode },
        };
      }
      const reason = validateForGenerate(
        fields.positive,
        fields.slots,
        fields.characterMode,
      );
      if (reason) {
        setError(reason);
        return;
      }
      setError(null);
      // 確認カードは残す（同じ内容で繰り返す・微調整して再生成するため）
      await generate(buildGeneratePayload(fields));
    },
    [
      buildGeneratePayload,
      characterMode,
      characterSlots,
      generate,
      negativeOrigin,
      negativeText,
      positiveOrigin,
      positiveText,
      validateForGenerate,
    ],
  );

  const discardExpansion = useCallback(() => {
    setPendingExpansion(null);
    setExpansionError(null);
  }, []);

  const confirmUsageWarn = useCallback(
    async (suppress: boolean) => {
      if (suppress) {
        try {
          sessionStorage.setItem(V5_USAGE_WARN_SUPPRESSED_KEY, "true");
        } catch {
          // sessionStorage が使えない環境では抑止しない
        }
      }
      const payload = pendingUsageWarn;
      setPendingUsageWarn(null);
      if (payload) {
        await postGenerate(payload);
      }
    },
    [pendingUsageWarn, postGenerate],
  );

  const cancelUsageWarn = useCallback(() => setPendingUsageWarn(null), []);

  const restoreEntry = useCallback(
    (entry: PromptExpanderEntry) => {
      const expandMode = entry.positive_expand_mode;
      const instruction = (entry.instruction ?? "").trim();
      const finalPrompt = entry.final_prompt ?? "";
      // 拡張を経て生成したエントリは、原文を欄へ戻し、変換結果を確認カードとして再現する
      // （そのまま再生成も、原文を直して再プロンプト化もできる）
      const expanded =
        entry.kind === "generated" &&
        expandMode !== "off" &&
        instruction.length > 0 &&
        instruction !== finalPrompt.trim();
      setPositiveText(expanded ? instruction : finalPrompt);
      setNegativeText(entry.final_negative_prompt ?? "");
      const slots = entry.character_prompts ?? [];
      setCharacterMode(slots.length > 0);
      setCharacterSlots(slots);
      setPositiveOrigin(null);
      setNegativeOrigin(null);
      setExpansionError(null);
      if (expanded) {
        setPendingExpansion({
          target: "positive",
          mode: expandMode,
          instruction,
          positivePrompt: finalPrompt,
          characterPrompts: slots.length > 0 ? slots : null,
          negativePrompt: null,
        });
      } else {
        setPendingExpansion(null);
      }
      const patch: PromptExpanderSettingsPatch = {};
      if (entry.image_model) patch.image_model = entry.image_model;
      if (entry.image_size) patch.image_size = entry.image_size;
      // seed は設定で明示的に ON にしたときだけ戻す（OFF なら現在の seed に触れない）
      if (
        settings.restore_seed &&
        entry.seed !== null &&
        entry.seed !== undefined
      ) {
        patch.seed = entry.seed;
      }
      if (entry.i2i_strength !== null && entry.i2i_strength !== undefined) {
        patch.i2i_strength = entry.i2i_strength;
      }
      if (entry.i2i_noise !== null && entry.i2i_noise !== undefined) {
        patch.i2i_noise = entry.i2i_noise;
      }
      // 漫画モードの印も復元する（コマ数 null はおまかせ）
      patch.manga_mode = Boolean(entry.manga_mode);
      if (entry.manga_mode) {
        patch.manga_panel_count = entry.manga_panel_count ?? 0;
      }
      if (Object.keys(patch).length > 0) {
        void updateSettings(patch);
      }
    },
    [setCharacterMode, settings.restore_seed, updateSettings],
  );

  const regenerateEntry = useCallback(
    async (entry: PromptExpanderEntry) => {
      const prompt = (entry.final_prompt ?? "").trim();
      if (!activeSession || !prompt) return;
      const slots = entry.character_prompts ?? [];
      // エントリに保存されたプロンプト・設定をそのまま使う。seed だけは付けず、毎回新しい乱数にする
      const payload: PromptExpanderGenerateRequest = {
        prompt,
        negative_prompt: entry.final_negative_prompt ?? "",
        character_prompts: slots,
        character_mode: entry.character_mode || slots.length > 0,
        instruction:
          entry.positive_expand_mode !== "off" ? entry.instruction : null,
        positive_expand_mode: entry.positive_expand_mode,
        negative_expand_mode: entry.negative_expand_mode,
        image_model: entry.image_model ?? settings.image_model,
        text_model: entry.text_model ?? settings.text_model,
        image_size: entry.image_size ?? settings.image_size,
        source_kind: "none",
        manga_mode: entry.manga_mode,
        manga_panel_count: entry.manga_mode ? entry.manga_panel_count : null,
      };
      // 参照元が履歴/エントリなら同じ元で i2i する（アップロード元は保持していないので t2i に落とす）
      if (entry.source_kind === "history" && entry.source_history_id) {
        payload.source_kind = "history";
        payload.source_history_id = entry.source_history_id;
      } else if (entry.source_kind === "entry" && entry.source_entry_id) {
        payload.source_kind = "entry";
        payload.source_entry_id = entry.source_entry_id;
      }
      if (payload.source_kind !== "none") {
        payload.i2i_strength = entry.i2i_strength ?? settings.i2i_strength;
        payload.i2i_noise = entry.i2i_noise ?? settings.i2i_noise;
      }
      setError(null);
      await generate(payload);
    },
    [
      activeSession,
      generate,
      settings.i2i_noise,
      settings.i2i_strength,
      settings.image_model,
      settings.image_size,
      settings.text_model,
    ],
  );

  const deleteEntry = useCallback(
    async (id: string) => {
      try {
        await deletePromptExpanderEntry(id);
        const removed = entries.find((e) => e.id === id);
        setEntries((prev) => prev.filter((e) => e.id !== id));
        if (removed) {
          bumpSessionEntryCount(removed.session_id, -1);
        }
        if (source?.kind === "entry" && source.entryId === id) {
          setSourceState(null);
        }
      } catch (err) {
        reportError("Prompt Expander", err);
      }
    },
    [bumpSessionEntryCount, entries, reportError, source],
  );

  const suggestCharacters = useCallback(
    async (count: number, mode: PromptExpandMode) => {
      setSuggesting(true);
      try {
        const draft = positiveText.trim();
        const resp = await suggestCharacterPrompts({
          text_model: settings.text_model,
          image_model: settings.image_model,
          mode,
          count,
          language,
          // 入力欄の下書きも渡し、メモリだけに寄った似た提案にならないようにする
          ...(draft ? { input_text: draft } : {}),
        });
        return resp.suggestions;
      } finally {
        setSuggesting(false);
      }
    },
    [language, positiveText, settings.image_model, settings.text_model],
  );

  // 生成ボタンの活性条件（理由は画面側で i18n キーに変換する）
  const generateDisabledReason = useMemo<string | null>(() => {
    if (!options.novelaiConfigured) return "novelai_not_configured";
    if (!activeSession) return "no_session";
    if (expanding || generating || draftingScript) return "busy";
    if (pendingExpansion) return "pending_expansion";
    if (characterSlotsOverCap) return "too_many_characters";
    if (!positiveText.trim()) return "empty_prompt";
    return null;
  }, [
    activeSession,
    characterSlotsOverCap,
    draftingScript,
    expanding,
    generating,
    options.novelaiConfigured,
    pendingExpansion,
    positiveText,
  ]);

  const value = useMemo<PromptExpanderContextValue>(
    () => ({
      sessions,
      activeSession,
      entries,
      settings,
      settingsLoaded,
      options,
      maxCharacterPrompts,
      loadingSessions,
      loadingSession,
      expanding,
      expandingTarget,
      draftingScript,
      scriptDraftBackup,
      generating,
      uploading,
      suggesting,
      error,
      clearError,
      expansionError,
      clearExpansionError,
      source,
      positiveText,
      positiveMode,
      positiveOrigin,
      characterMode,
      characterSlots,
      characterSlotsOverCap,
      mangaActive,
      effectivePositiveMode,
      negativeText,
      negativeMode,
      negativeOrigin,
      pendingExpansion,
      pendingUsageWarn,
      anlas,
      canGenerate: generateDisabledReason === null,
      generateDisabledReason,
      loadSessions,
      createSession,
      renameSession,
      deleteSession,
      openSession,
      loadSettings,
      updateSettings,
      updateSettingsDebounced,
      importGlobalMemory,
      setSource,
      clearSource,
      setPositiveText,
      setPositiveMode,
      setCharacterMode,
      addCharacterSlot,
      updateCharacterSlot,
      removeCharacterSlot,
      setNegativeText,
      setNegativeMode,
      uploadImage,
      expandPositive,
      expandNegative,
      draftScript,
      undoScriptDraft,
      applyExpansion,
      generateFromExpansion,
      discardExpansion,
      runGenerate,
      confirmUsageWarn,
      cancelUsageWarn,
      restoreEntry,
      regenerateEntry,
      selectEntryAsSource,
      deleteEntry,
      suggestCharacters,
    }),
    [
      sessions,
      activeSession,
      entries,
      settings,
      settingsLoaded,
      options,
      maxCharacterPrompts,
      loadingSessions,
      loadingSession,
      expanding,
      expandingTarget,
      draftingScript,
      scriptDraftBackup,
      generating,
      uploading,
      suggesting,
      error,
      clearError,
      expansionError,
      clearExpansionError,
      source,
      positiveText,
      positiveMode,
      positiveOrigin,
      characterMode,
      characterSlots,
      characterSlotsOverCap,
      mangaActive,
      effectivePositiveMode,
      negativeText,
      negativeMode,
      negativeOrigin,
      pendingExpansion,
      pendingUsageWarn,
      anlas,
      generateDisabledReason,
      loadSessions,
      createSession,
      renameSession,
      deleteSession,
      openSession,
      loadSettings,
      updateSettings,
      updateSettingsDebounced,
      importGlobalMemory,
      setSource,
      clearSource,
      setCharacterMode,
      addCharacterSlot,
      updateCharacterSlot,
      removeCharacterSlot,
      uploadImage,
      expandPositive,
      expandNegative,
      draftScript,
      undoScriptDraft,
      applyExpansion,
      generateFromExpansion,
      discardExpansion,
      runGenerate,
      confirmUsageWarn,
      cancelUsageWarn,
      restoreEntry,
      regenerateEntry,
      selectEntryAsSource,
      deleteEntry,
      suggestCharacters,
    ],
  );

  return (
    <PromptExpanderContext.Provider value={value}>
      {children}
    </PromptExpanderContext.Provider>
  );
}

export function usePromptExpander(): PromptExpanderContextValue {
  const ctx = useContext(PromptExpanderContext);
  if (!ctx) {
    throw new Error(
      "usePromptExpander must be used within a PromptExpanderProvider",
    );
  }
  return ctx;
}
