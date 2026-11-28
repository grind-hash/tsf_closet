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
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { fetchAnlasBalance } from "../apis/anlas";
import { getCharacterPreset } from "../apis/characters";
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
  type PromptExpanderCastMember,
  type PromptExpanderEntry,
  type PromptExpanderEntryReference,
  type PromptExpanderGenerateRequest,
  type PromptExpanderMangaOptions,
  type PromptExpanderReferenceRequest,
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
  type PreciseReferenceFormat,
  preciseReferenceFormat,
  V5_USAGE_WARN_SUPPRESSED_KEY,
} from "../constants/novelaiImageModels";
import {
  DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
  DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY,
  DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH,
  DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
  DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS,
  getMaxCharacterPrompts,
  isCharacterReferenceType,
  NOVELAI_TEXT_MODEL_OPTIONS,
  PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
  PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY,
  PROMPT_EXPANDER_CAST_NAME_MAX_LENGTH,
  PROMPT_EXPANDER_CAST_TAGS_MAX_LENGTH,
  PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_SIZES,
  PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
  PROMPT_EXPANDER_STORY_CONTEXT_MAX,
  type PromptExpanderImageSize,
  type PromptExpanderReferenceType,
  type PromptExpandMode,
  supportsMangaMode,
  supportsPreciseReference,
} from "../constants/promptExpander";
import { usePersistedState } from "../hooks/usePersistedState";
import type { AnlasBalance } from "../types";
import { mediaUrl } from "../utils/adventureFormat";
import { ApiError } from "../utils/http";
import {
  clampReferenceStrength,
  isReferenceTypeSupported,
} from "../utils/preciseReferences";
import { compareEntriesByCreation } from "../utils/promptExpanderStoryContext";
import {
  readStorage,
  readStorageFlag,
  removeStorage,
  writeStorage,
  writeStorageFlag,
} from "../utils/storage";
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

/** 精密参照の参照元（i2i 元の種類に加え、キャラクターの立ち絵を ID で指せる） */
export type PromptExpanderReferenceSourceType =
  | PromptExpanderSourceType
  | "character";

/** 精密参照に足す画像。種別・強度などは足した時点の既定値から始まる */
export interface PromptExpanderReferenceInput {
  kind: PromptExpanderReferenceSourceType;
  historyId?: string;
  entryId?: string;
  /** kind="character" のときのキャラクタープリセット ID（再生成でも同じ立ち絵を使える） */
  characterPresetId?: string;
  /** kind="upload" のときの data URL（履歴に残さないアップロード） */
  uploadDataUrl?: string;
  thumbnailUrl: string;
  label: string;
  /** 登場人物としての名前（キャラクターの立ち絵ならプリセット名が入る） */
  name?: string;
  /** 登場人物の外見タグ（キャラクターの立ち絵ならプリセットの外見タグが入る） */
  appearanceTags?: string;
}

/** 精密参照 1 枚分。画像ごとに種別・強度などを持ち、セッション内だけ保持する */
export interface PromptExpanderReference extends PromptExpanderReferenceInput {
  id: string;
  type: PromptExpanderReferenceType;
  /** 衣装も参照するか（V5 のキャラ系の参照だけ効く） */
  includeOutfit: boolean;
  strength: number;
  /** 忠実度（V4.5 の参照だけ効く） */
  fidelity: number;
  name: string;
  appearanceTags: string;
}

export type PromptExpanderReferencePatch = Partial<
  Pick<
    PromptExpanderReference,
    | "type"
    | "includeOutfit"
    | "strength"
    | "fidelity"
    | "name"
    | "appearanceTags"
  >
>;

/** 画像ピッカー／アップロードの入れ先（i2i 元 or 精密参照） */
export type PromptExpanderPickerTarget = "source" | "reference";

/** インペイントで使うマスク（新規描画 or 過去エントリのマスク再利用） */
export interface PromptExpanderMask {
  /** 新規に描いたマスクの data URL */
  dataUrl?: string;
  /** 過去エントリのマスクを再利用するときの元エントリ ID */
  fromEntryId?: string;
  thumbnailUrl: string;
  label: string;
}

/** 直近の生成の結果。成功は開始元のセッションとエントリ、失敗はエラー文を持つ */
export type PromptExpanderGenerateOutcome =
  | { status: "success"; sessionId: string; entryId: string }
  | { status: "error"; sessionId: string; message: string };

/** プロンプトを作る元の欄（指示・あらすじの欄 or ネームの欄） */
export type PromptExpanderPromptSource = "instruction" | "script";

/** プロンプト欄の入れ方（LLM で作る or 直接書く）。直接書くでは指示・ネームの欄を出さない */
export type PromptExpanderPromptInputMode = "assist" | "direct";

/** プロンプト欄の内容が LLM で作ったものであることを示す（履歴メタデータ用） */
export interface PromptExpanderPositiveOrigin {
  mode: PromptExpandMode;
  /** プロンプトを作った欄の文（指示 or ネーム） */
  instruction: string;
  /** プロンプトを作った欄 */
  source: PromptExpanderPromptSource;
  /** ネームから作ったときの、ネームの下書き元のあらすじ */
  synopsis: string | null;
}

/** ネガティブ欄の内容が拡張結果由来であることを示す */
export interface PromptExpanderNegativeOrigin {
  mode: PromptExpandMode;
}

/** ネガティブ欄の変換カード（欄の直下で手直しして、欄へ反映するか、そのまま生成する） */
export interface PromptExpanderNegativeExpansion {
  mode: PromptExpandMode;
  negativePrompt: string;
}

/** プロンプトを作り直す前の内容（「元に戻す」用）。欄が作った内容のままのあいだ戻せる */
export interface PromptExpanderPromptUndo {
  prompt: string;
  characterMode: boolean;
  characterSlots: string[];
  origin: PromptExpanderPositiveOrigin | null;
  /** 作り直して欄に入れた内容 */
  applied: string;
}

/** ネームを下書きし直す前の内容（「元に戻す」用） */
export interface PromptExpanderScriptUndo {
  script: string;
  /** 下書きして欄に入れた内容 */
  applied: string;
}

/** セッションごとの書きかけ。同じタブの再読み込みでも残るよう sessionStorage に置く */
interface SessionDraft {
  version: 2;
  instructionText: string;
  scriptText: string;
  /** プロンプト欄（生成で送る内容） */
  positiveText: string;
  negativeText: string;
  characterSlots: string[];
  positiveOrigin: PromptExpanderPositiveOrigin | null;
  negativeOrigin: PromptExpanderNegativeOrigin | null;
  negativeExpansion: PromptExpanderNegativeExpansion | null;
  promptUndo: PromptExpanderPromptUndo | null;
  scriptUndo: PromptExpanderScriptUndo | null;
  /** これまでの話に選んだエントリの ID（漫画で続きのページを作るときに LLM へ渡す） */
  storyContextEntryIds: string[];
}

const EMPTY_SESSION_DRAFT: SessionDraft = {
  version: 2,
  instructionText: "",
  scriptText: "",
  positiveText: "",
  negativeText: "",
  characterSlots: [],
  positiveOrigin: null,
  negativeOrigin: null,
  negativeExpansion: null,
  promptUndo: null,
  scriptUndo: null,
  storyContextEntryIds: [],
};

const SESSION_DRAFT_KEY_PREFIX = "prompt_expander_draft:";

function sessionDraftKey(sessionId: string): string {
  return `${SESSION_DRAFT_KEY_PREFIX}${sessionId}`;
}

function draftText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isExpandMode(value: unknown): value is PromptExpandMode {
  return value === "off" || value === "japanese" || value === "tags";
}

function readPositiveOrigin(
  value: unknown,
): PromptExpanderPositiveOrigin | null {
  if (!isRecord(value) || typeof value.instruction !== "string") return null;
  return {
    mode: isExpandMode(value.mode) ? value.mode : "tags",
    instruction: value.instruction,
    source: value.source === "script" ? "script" : "instruction",
    synopsis: typeof value.synopsis === "string" ? value.synopsis : null,
  };
}

function readSlots(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((slot): slot is string => typeof slot === "string")
    : [];
}

/**
 * 欄を分ける前（プロンプト欄 1 つに指示・ネーム・プロンプトを順に入れていた形）の書きかけを読み替える。
 * 拡張結果を反映済みならプロンプト欄へ、ネームを下書きした後ならネーム欄へ、それ以外は指示欄へ入れる
 */
function readLegacySessionDraft(data: Record<string, unknown>): SessionDraft {
  const text = draftText(data.positiveText);
  const draft: SessionDraft = {
    ...EMPTY_SESSION_DRAFT,
    negativeText: draftText(data.negativeText),
    characterSlots: readSlots(data.characterSlots),
    negativeOrigin: isRecord(data.negativeOrigin)
      ? {
          mode: isExpandMode(data.negativeOrigin.mode)
            ? data.negativeOrigin.mode
            : "tags",
        }
      : null,
  };
  const backup = isRecord(data.scriptDraftBackup)
    ? {
        source: draftText(data.scriptDraftBackup.source),
        script: draftText(data.scriptDraftBackup.script),
      }
    : null;
  const origin = readPositiveOrigin(data.positiveOrigin);
  if (origin) {
    const fromScript = backup !== null && backup.script === origin.instruction;
    draft.positiveText = text;
    draft.positiveOrigin = {
      ...origin,
      source: fromScript ? "script" : "instruction",
      synopsis: fromScript ? backup.source : null,
    };
    if (fromScript) {
      draft.instructionText = backup.source;
      draft.scriptText = backup.script;
    } else {
      draft.instructionText = origin.instruction;
    }
  } else if (backup) {
    draft.instructionText = backup.source;
    draft.scriptText = text;
  } else {
    draft.instructionText = text;
  }
  const cards = isRecord(data.pendingExpansions)
    ? data.pendingExpansions
    : null;
  const negativeCard =
    cards && isRecord(cards.negative) ? cards.negative : null;
  if (negativeCard && typeof negativeCard.negativePrompt === "string") {
    draft.negativeExpansion = {
      mode: isExpandMode(negativeCard.mode) ? negativeCard.mode : "tags",
      negativePrompt: negativeCard.negativePrompt,
    };
  }
  return draft;
}

function readSessionDraft(sessionId: string): SessionDraft | null {
  const raw = readStorage("session", sessionDraftKey(sessionId));
  if (!raw) return null;
  try {
    const data: unknown = JSON.parse(raw);
    if (!isRecord(data)) return null;
    if (data.version !== 2) return readLegacySessionDraft(data);
    const negativeExpansion = isRecord(data.negativeExpansion)
      ? {
          mode: isExpandMode(data.negativeExpansion.mode)
            ? data.negativeExpansion.mode
            : "tags",
          negativePrompt: draftText(data.negativeExpansion.negativePrompt),
        }
      : null;
    const promptUndo = isRecord(data.promptUndo)
      ? {
          prompt: draftText(data.promptUndo.prompt),
          characterMode: data.promptUndo.characterMode === true,
          characterSlots: readSlots(data.promptUndo.characterSlots),
          origin: readPositiveOrigin(data.promptUndo.origin),
          applied: draftText(data.promptUndo.applied),
        }
      : null;
    const scriptUndo = isRecord(data.scriptUndo)
      ? {
          script: draftText(data.scriptUndo.script),
          applied: draftText(data.scriptUndo.applied),
        }
      : null;
    return {
      version: 2,
      instructionText: draftText(data.instructionText),
      scriptText: draftText(data.scriptText),
      positiveText: draftText(data.positiveText),
      negativeText: draftText(data.negativeText),
      characterSlots: readSlots(data.characterSlots),
      positiveOrigin: readPositiveOrigin(data.positiveOrigin),
      negativeOrigin: isRecord(data.negativeOrigin)
        ? {
            mode: isExpandMode(data.negativeOrigin.mode)
              ? data.negativeOrigin.mode
              : "tags",
          }
        : null,
      negativeExpansion,
      promptUndo,
      scriptUndo,
      // これまでの話を足す前の書きかけには無いので、空として読む
      storyContextEntryIds: readSlots(data.storyContextEntryIds),
    };
  } catch {
    return null;
  }
}

function isEmptyDraft(draft: SessionDraft): boolean {
  return (
    !draft.instructionText &&
    !draft.scriptText &&
    !draft.positiveText &&
    !draft.negativeText &&
    draft.characterSlots.length === 0 &&
    !draft.negativeExpansion &&
    !draft.promptUndo &&
    !draft.scriptUndo &&
    draft.storyContextEntryIds.length === 0
  );
}

function writeSessionDraft(sessionId: string, draft: SessionDraft): void {
  if (isEmptyDraft(draft)) {
    removeStorage("session", sessionDraftKey(sessionId));
    return;
  }
  writeStorage("session", sessionDraftKey(sessionId), JSON.stringify(draft));
}

/**
 * 開いていないセッションの書きかけを書き換える。
 * LLM に頼んだあとで別のセッションへ移ったとき、届いた結果を依頼元のセッションにだけ入れるために使う
 */
function updateStoredSessionDraft(
  sessionId: string,
  update: (draft: SessionDraft) => SessionDraft,
): void {
  writeSessionDraft(
    sessionId,
    update(readSessionDraft(sessionId) ?? EMPTY_SESSION_DRAFT),
  );
}

/** 「欄へ復元」の前に控える内容 */
interface RestoreSnapshot {
  instructionText: string;
  scriptText: string;
  positiveText: string;
  negativeText: string;
  characterMode: boolean;
  characterSlots: string[];
  positiveOrigin: PromptExpanderPositiveOrigin | null;
  negativeOrigin: PromptExpanderNegativeOrigin | null;
  negativeExpansion: PromptExpanderNegativeExpansion | null;
  promptUndo: PromptExpanderPromptUndo | null;
  scriptUndo: PromptExpanderScriptUndo | null;
  promptInputMode: PromptExpanderPromptInputMode;
  settings: PromptExpanderSettingsPatch;
  references: PromptExpanderReference[];
  inpaintMask: PromptExpanderMask | null;
  restoredPositive: string;
}

/**
 * 生成履歴でエントリを見せたあとにフォーカスする先。
 * image はカードの画像（プレビューを開く）、story は「これまでの話に入れる／外す」ボタン
 */
export type PromptExpanderEntryRevealFocus = "image" | "story";

/** 生成履歴で見せたいエントリ。同じエントリを続けて見せられるよう連番を付ける */
export interface PromptExpanderEntryRevealRequest {
  entryId: string;
  seq: number;
  focus: PromptExpanderEntryRevealFocus;
}

/** 欄の近くに出す拡張エラー */
export interface PromptExpanderExpansionError {
  target: PromptExpanderExpansionTarget;
  /** 正プロンプト側のときの、操作した欄（指示・あらすじ or ネーム） */
  field?: PromptExpanderPromptSource;
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
  /** 精密参照 1 枚あたりの Anlas 消費 */
  anlasPerReference: number;
}

export interface PromptExpanderUploadOptions {
  keepAsEntry: boolean;
  /** 画像を target（既定は i2i 元）の選択状態に入れる */
  useAsSource: boolean;
  target?: PromptExpanderPickerTarget;
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
  generating: boolean;
  /** 生成中のセッション ID（生成中でなければ null）。履歴の「生成しています」はこれが開いているセッションのときだけ出す */
  generatingSessionId: string | null;
  /** 直近の生成の結果（生成バーに出す）。次の生成を始めるか、閉じると消える */
  lastGenerateOutcome: PromptExpanderGenerateOutcome | null;
  dismissGenerateOutcome: () => void;
  /** 生成履歴で見せたいエントリ（「結果を見る」で設定し、EntryList が絞り込みを解いてそこへ移る） */
  entryRevealRequest: PromptExpanderEntryRevealRequest | null;
  /** focus を story にすると、移った先で「これまでの話に入れる」ボタンを目立たせてフォーカスする */
  requestEntryReveal: (
    entryId: string,
    focus?: PromptExpanderEntryRevealFocus,
  ) => void;
  /** EntryList が見せ終えた要求を消す（一覧を開き直したときに、前の要求でもう一度動かないように） */
  completeEntryReveal: (seq: number) => void;
  uploading: boolean;
  suggesting: boolean;
  error: string | null;
  clearError: () => void;
  expansionError: PromptExpanderExpansionError | null;
  clearExpansionError: () => void;
  // コンポーザ
  source: PromptExpanderSource | null;
  /** 精密参照に使う画像（i2i 元とは独立。セッション内だけ保持する。最大 6 枚） */
  references: PromptExpanderReference[];
  /** 生成に載る精密参照（設定 ON・対応モデル・対応種別のものだけ） */
  sendableReferences: PromptExpanderReference[];
  /** 名前を付けたキャラ系の参照から作る登場人物（プロンプト化・ネーム下書きに渡す） */
  referenceCast: PromptExpanderCastMember[];
  /** 現在の画像モデルで精密参照が使えるか（V5 Full の節約モードは不可） */
  referenceSupported: boolean;
  /** 現在の画像モデルでの精密参照の送信形式（使えないモデルは null） */
  referenceFormat: PreciseReferenceFormat | null;
  /** V5 でインペイント中のため精密参照を送れない状態か */
  referenceInpaintBlocked: boolean;
  /** 精密参照が 1 枚以上生成へ載る状態か */
  referenceActive: boolean;
  /** 精密参照で追加消費する Anlas（載る枚数 × 1 枚あたりの消費） */
  referenceAnlasCost: number;
  /** 背景透過が実際に効く状態か（設定 ON かつ漫画モード OFF） */
  transparentActive: boolean;
  /** インペイントに使うマスク（i2i 元の上に描く。セッション内だけ保持する） */
  inpaintMask: PromptExpanderMask | null;
  /** インペイントが実際に生成へ載る状態か（設定 ON かつ i2i 元あり かつ マスクあり） */
  inpaintActive: boolean;
  /** プロンプト欄の入れ方（LLM で作る or 直接書く）。localStorage に保つ */
  promptInputMode: PromptExpanderPromptInputMode;
  /** 指示（漫画モードではあらすじ）の欄。利用者が書く。LLM は書き換えない */
  instructionText: string;
  /** ネームの欄（漫画モード）。LLM の下書きが入り、手直しできる */
  scriptText: string;
  /** プロンプト欄（生成で送る内容）。プロンプト化の結果が入り、直接書いてもよい */
  positiveText: string;
  positiveMode: PromptExpandMode;
  positiveOrigin: PromptExpanderPositiveOrigin | null;
  /** プロンプトを作り直す前の内容（欄が作った内容のままなら「元に戻す」が使える） */
  promptUndo: PromptExpanderPromptUndo | null;
  /** ネームを下書きし直す前の内容 */
  scriptUndo: PromptExpanderScriptUndo | null;
  characterMode: boolean;
  characterSlots: string[];
  characterSlotsOverCap: boolean;
  /** 漫画モードが実際に効く状態か（設定 ON かつ V5 系モデル） */
  mangaActive: boolean;
  /** これまでの話に選んだエントリ（開いているセッションにあるものだけ、生成した順） */
  storyContextEntries: PromptExpanderEntry[];
  /** storyContextEntries の ID（漫画のネーム下書き・プロンプト化に送る） */
  storyContextEntryIds: string[];
  /** 正プロンプト拡張に実際に使うモード（漫画モード中は "tags" 固定） */
  effectivePositiveMode: PromptExpandMode;
  negativeText: string;
  negativeMode: PromptExpandMode;
  negativeOrigin: PromptExpanderNegativeOrigin | null;
  /** ネガティブ欄の変換カード */
  negativeExpansion: PromptExpanderNegativeExpansion | null;
  pendingUsageWarn: PromptExpanderGenerateRequest | null;
  /** 精密参照の Anlas 確認待ちの生成ペイロード */
  pendingReferenceWarn: PromptExpanderGenerateRequest | null;
  anlas: AnlasBalance | null;
  canGenerate: boolean;
  generateDisabledReason: string | null;
  // アクション: セッション
  loadSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<PromptExpanderSession | null>;
  /** 保存できたら true。失敗したら通知を出して false */
  renameSession: (id: string, title: string) => Promise<boolean>;
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
  /** 精密参照を末尾に足す。上限に達していれば足さずに false を返す */
  addReference: (input: PromptExpanderReferenceInput) => boolean;
  updateReference: (id: string, patch: PromptExpanderReferencePatch) => void;
  removeReference: (id: string) => void;
  clearReferences: () => void;
  setInpaintMask: (mask: PromptExpanderMask | null) => void;
  clearInpaintMask: () => void;
  setPromptInputMode: (mode: PromptExpanderPromptInputMode) => void;
  setInstructionText: (text: string) => void;
  setScriptText: (text: string) => void;
  setPositiveText: (text: string) => void;
  setPositiveMode: (mode: PromptExpandMode) => void;
  setCharacterMode: (on: boolean) => void;
  addCharacterSlot: (text?: string) => void;
  updateCharacterSlot: (index: number, text: string) => void;
  removeCharacterSlot: (index: number) => void;
  setNegativeText: (text: string) => void;
  setNegativeMode: (mode: PromptExpandMode) => void;
  /** 画像を入れ先へ送る。失敗時は通知して false を返す */
  uploadImage: (
    file: File,
    options: PromptExpanderUploadOptions,
  ) => Promise<boolean>;
  /** 指示（あらすじ）欄かネーム欄の文から LLM でプロンプトを作り、プロンプト欄へ入れる */
  expandPositive: (field: PromptExpanderPromptSource) => Promise<void>;
  /** プロンプトを作り直す前の内容に戻す */
  undoPrompt: () => void;
  /** ネガティブ欄の内容を拡張し、欄の直下に確認カードを出す */
  expandNegative: () => Promise<void>;
  /** あらすじ欄から、記法付きのネームを LLM で下書きしてネーム欄へ入れる（漫画モード） */
  draftScript: () => Promise<void>;
  /** ネームを下書きし直す前の内容に戻す */
  undoScript: () => void;
  /** これまでの話に入れる・外す（上限に達していれば入れない） */
  toggleStoryContextEntry: (entryId: string) => void;
  removeStoryContextEntry: (entryId: string) => void;
  clearStoryContext: () => void;
  /** ネガティブの変換カードの内容を欄へ書き戻してカードを閉じる */
  applyNegativeExpansion: () => void;
  /** ネガティブの変換カードの内容でそのまま生成する（欄もカードも変更しない） */
  generateFromNegativeExpansion: () => Promise<void>;
  /** ネガティブの変換カードを閉じる */
  discardNegativeExpansion: () => void;
  /** ネガティブの変換カードで手直しした内容を書き戻す（書きかけと一緒に保存される） */
  editNegativeExpansion: (negativePrompt: string) => void;
  /** 欄の内容をそのまま生成する */
  runGenerate: () => Promise<void>;
  confirmUsageWarn: (suppress: boolean) => Promise<void>;
  cancelUsageWarn: () => void;
  confirmReferenceWarn: (suppress: boolean) => Promise<void>;
  cancelReferenceWarn: () => void;
  /** 拡張ありのエントリは指示（あらすじ・ネーム）とプロンプトをそれぞれの欄へ戻す */
  restoreEntry: (entry: PromptExpanderEntry) => void;
  /** 「欄へ復元」で置き換えた内容を控えている間の、復元後の正プロンプト（欄が変わったら案内を消す） */
  restoreUndo: { restoredPositive: string } | null;
  /** 「欄へ復元」の前の内容（欄・設定・精密参照・マスク）に戻す */
  undoRestore: () => void;
  /** エントリのプロンプト・設定のまま、seed だけ新規（ランダム）で生成し直す */
  regenerateEntry: (entry: PromptExpanderEntry) => Promise<void>;
  selectEntryAsSource: (entry: PromptExpanderEntry) => void;
  /** エントリを精密参照に足す。既に参照に入っていれば外す */
  selectEntryAsReference: (entry: PromptExpanderEntry) => void;
  deleteEntry: (id: string) => Promise<void>;
  suggestCharacters: (
    count: number,
    mode: PromptExpandMode,
  ) => Promise<PromptExpanderSuggestion[]>;
}

/** キャラクタープロンプトの ON/OFF は作業欄の状態だが、セッション切替や再読み込みをまたいで保つ */
export const PROMPT_EXPANDER_CHARACTER_MODE_KEY =
  "prompt_expander_character_mode";

/** プロンプト欄の入れ方（LLM で作る / 直接書く）も、セッション切替や再読み込みをまたいで保つ */
export const PROMPT_EXPANDER_PROMPT_INPUT_MODE_KEY =
  "prompt_expander_prompt_input_mode";

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
  use_precise_reference: false,
  transparent_background: false,
  transparent_emphasis: DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS,
  use_inpaint: false,
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
  anlasPerReference: PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
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
  return readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY);
}

function readReferenceWarnSuppressed(): boolean {
  return readStorageFlag("session", PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY);
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
    anlasPerReference:
      payload.anlas_per_reference ?? PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
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

let referenceIdSeq = 0;

/** 足した参照に既定の種別・強度などを付ける（衣装も参照するの初期値は OFF） */
function createReference(
  input: PromptExpanderReferenceInput,
  settings: Partial<
    Pick<
      PromptExpanderReference,
      "type" | "includeOutfit" | "strength" | "fidelity"
    >
  > = {},
): PromptExpanderReference {
  referenceIdSeq += 1;
  return {
    ...input,
    id: `ref-${Date.now()}-${referenceIdSeq}`,
    type: settings.type ?? DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
    includeOutfit: settings.includeOutfit ?? false,
    strength: settings.strength ?? DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH,
    fidelity: settings.fidelity ?? DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY,
    name: (input.name ?? "").slice(0, PROMPT_EXPANDER_CAST_NAME_MAX_LENGTH),
    appearanceTags: (input.appearanceTags ?? "").slice(
      0,
      PROMPT_EXPANDER_CAST_TAGS_MAX_LENGTH,
    ),
  };
}

/** 名前を付けたキャラ系の参照から登場人物を作る（同じ名前は先頭だけ） */
export function buildReferenceCast(
  references: PromptExpanderReference[],
): PromptExpanderCastMember[] {
  const seen = new Set<string>();
  const cast: PromptExpanderCastMember[] = [];
  for (const ref of references) {
    const name = ref.name.trim().replace(/\s+/g, " ");
    if (!name || !isCharacterReferenceType(ref.type)) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    cast.push({ name, appearance_tags: ref.appearanceTags.trim() });
  }
  return cast;
}

/** 生成リクエストに載せる参照 1 枚分。強度はモデルの上限に収める */
function toReferenceRequest(
  ref: PromptExpanderReference,
  format: PreciseReferenceFormat,
): PromptExpanderReferenceRequest {
  const request: PromptExpanderReferenceRequest = {
    kind: ref.kind,
    type: ref.type,
    include_outfit: ref.includeOutfit,
    strength: clampReferenceStrength(ref.strength, format),
    fidelity: ref.fidelity,
  };
  if (ref.kind === "history") request.history_id = ref.historyId;
  else if (ref.kind === "entry") request.entry_id = ref.entryId;
  else if (ref.kind === "character")
    request.character_preset_id = ref.characterPresetId;
  else request.image = ref.uploadDataUrl;
  const name = ref.name.trim();
  if (name && isCharacterReferenceType(ref.type)) request.name = name;
  const appearanceTags = ref.appearanceTags.trim();
  if (appearanceTags && isCharacterReferenceType(ref.type)) {
    request.appearance_tags = appearanceTags;
  }
  return request;
}

// ----------------------------------------------------------------
// Provider
// ----------------------------------------------------------------

export function PromptExpanderProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { state: settingsState, setAnlasBalance } = useSettings();
  const { showNotification } = useNotification();
  const { t } = useTranslation();
  const imageProvider = settingsState.imageProvider;
  const language = settingsState.language;
  const globalAnlas = settingsState.anlasBalance;

  // 一覧/詳細
  const [sessions, setSessions] = useState<PromptExpanderSession[]>([]);
  const [activeSession, setActiveSession] =
    useState<PromptExpanderSession | null>(null);
  const [entries, setEntries] = useState<PromptExpanderEntry[]>([]);
  // これまでの話に選んだエントリの ID（選んだ順。書きかけとしてセッションごとに持つ）
  const [storyContextIds, setStoryContextIds] = useState<string[]>([]);

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
  const [generatingSessionId, setGeneratingSessionId] = useState<string | null>(
    null,
  );
  const [lastGenerateOutcome, setLastGenerateOutcome] =
    useState<PromptExpanderGenerateOutcome | null>(null);
  const [entryRevealRequest, setEntryRevealRequest] =
    useState<PromptExpanderEntryRevealRequest | null>(null);
  const [restoreSnapshot, setRestoreSnapshot] =
    useState<RestoreSnapshot | null>(null);
  const [uploading, setUploading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [draftingScript, setDraftingScript] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expansionError, setExpansionError] =
    useState<PromptExpanderExpansionError | null>(null);

  // コンポーザ
  const [source, setSourceState] = useState<PromptExpanderSource | null>(null);
  // 精密参照の画像（複数枚）。i2i 元とは独立して選び、画像ごとに設定を持つ（永続化しない）
  const [references, setReferences] = useState<PromptExpanderReference[]>([]);
  // インペイントのマスク。ベース画像は i2i 元を使うので、ここには形だけを持つ
  const [inpaintMask, setInpaintMaskState] =
    useState<PromptExpanderMask | null>(null);
  const [promptInputMode, setPromptInputMode] =
    usePersistedState<PromptExpanderPromptInputMode>(
      PROMPT_EXPANDER_PROMPT_INPUT_MODE_KEY,
      "assist",
      {
        serialize: (value) => value,
        deserialize: (raw) => (raw === "direct" ? "direct" : "assist"),
      },
    );
  const [instructionText, setInstructionText] = useState("");
  const [scriptText, setScriptText] = useState("");
  const [positiveText, setPositiveText] = useState("");
  const [positiveMode, setPositiveMode] = useState<PromptExpandMode>("tags");
  const [positiveOrigin, setPositiveOrigin] =
    useState<PromptExpanderPositiveOrigin | null>(null);
  const [promptUndo, setPromptUndo] = useState<PromptExpanderPromptUndo | null>(
    null,
  );
  const [scriptUndo, setScriptUndo] = useState<PromptExpanderScriptUndo | null>(
    null,
  );
  // 復元・欄へ反映など内部からの変更も含めて localStorage に保つ
  const [characterMode, setCharacterMode] = usePersistedState<boolean>(
    PROMPT_EXPANDER_CHARACTER_MODE_KEY,
    false,
  );
  const [characterSlots, setCharacterSlots] = useState<string[]>([]);
  const [negativeText, setNegativeText] = useState("");
  const [negativeMode, setNegativeMode] = useState<PromptExpandMode>("tags");
  const [negativeOrigin, setNegativeOrigin] =
    useState<PromptExpanderNegativeOrigin | null>(null);
  const [negativeExpansion, setNegativeExpansion] =
    useState<PromptExpanderNegativeExpansion | null>(null);
  const [pendingUsageWarn, setPendingUsageWarn] =
    useState<PromptExpanderGenerateRequest | null>(null);
  const [pendingReferenceWarn, setPendingReferenceWarn] =
    useState<PromptExpanderGenerateRequest | null>(null);
  const [anlas, setAnlas] = useState<AnlasBalance | null>(globalAnlas);

  const expanding = expandingTarget !== null;
  // 生成の完了時に「いま開いているセッション」を見るため、最新の ID を ref に写しておく
  const activeSessionIdRef = useRef<string | null>(null);
  activeSessionIdRef.current = activeSession?.id ?? null;

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

  // 書きかけ（指示・ネーム・プロンプトの欄、ネガティブの変換カード、元に戻す用の控え）は
  // セッションごとに持つ。開いているセッションが変わったら、そのセッションの書きかけに入れ替える
  const activeSessionId = activeSession?.id ?? null;
  const draftOwnerRef = useRef<string | null>(null);
  useEffect(() => {
    if (draftOwnerRef.current === activeSessionId) return;
    draftOwnerRef.current = activeSessionId;
    const draft =
      (activeSessionId ? readSessionDraft(activeSessionId) : null) ??
      EMPTY_SESSION_DRAFT;
    setInstructionText(draft.instructionText);
    setScriptText(draft.scriptText);
    setPositiveText(draft.positiveText);
    setNegativeText(draft.negativeText);
    setCharacterSlots(draft.characterSlots);
    setPositiveOrigin(draft.positiveOrigin);
    setNegativeOrigin(draft.negativeOrigin);
    setNegativeExpansion(draft.negativeExpansion);
    setPromptUndo(draft.promptUndo);
    setScriptUndo(draft.scriptUndo);
    setStoryContextIds(draft.storyContextEntryIds);
    setRestoreSnapshot(null);
    setExpansionError(null);
  }, [activeSessionId]);
  // 書きかけが変わるたびに、持ち主のセッションへ保存する（セッションを切り替えた描画では
  // 欄はまだ前のセッションのままなので、ここは欄が変わったときだけ動く）
  useEffect(() => {
    const owner = draftOwnerRef.current;
    if (!owner) return;
    writeSessionDraft(owner, {
      version: 2,
      instructionText,
      scriptText,
      positiveText,
      negativeText,
      characterSlots,
      positiveOrigin,
      negativeOrigin,
      negativeExpansion,
      promptUndo,
      scriptUndo,
      storyContextEntryIds: storyContextIds,
    });
  }, [
    characterSlots,
    instructionText,
    negativeExpansion,
    negativeOrigin,
    negativeText,
    positiveOrigin,
    positiveText,
    promptUndo,
    scriptText,
    scriptUndo,
    storyContextIds,
  ]);

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
    async (id: string, title: string): Promise<boolean> => {
      try {
        const updated = await renamePromptExpanderSession(id, title);
        setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
        setActiveSession((prev) => (prev?.id === id ? updated : prev));
        return true;
      } catch (err) {
        reportError("Prompt Expander", err);
        return false;
      }
    },
    [reportError],
  );

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await deletePromptExpanderSession(id);
        removeStorage("session", sessionDraftKey(id));
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

  // 最後に開こうとしたセッション。先に頼んだ読み込みが後から返ってきても、それで上書きしない
  const requestedSessionIdRef = useRef<string | null>(null);
  const openSession = useCallback(
    async (id: string) => {
      requestedSessionIdRef.current = id;
      setLoadingSession(true);
      try {
        const detail = await fetchPromptExpanderSession(id);
        if (requestedSessionIdRef.current !== id) return;
        setActiveSession(detail.session);
        setEntries(detail.entries);
        setSessions((prev) => {
          const exists = prev.some((s) => s.id === detail.session.id);
          return exists
            ? prev.map((s) => (s.id === detail.session.id ? detail.session : s))
            : [detail.session, ...prev];
        });
      } catch (err) {
        if (requestedSessionIdRef.current !== id) return;
        setActiveSession(null);
        setEntries([]);
        reportError("Prompt Expander", err);
      } finally {
        if (requestedSessionIdRef.current === id) setLoadingSession(false);
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
  // 背景透過はコマ枠を切り抜けないため漫画モードとは両立しない（設定は残す）
  const transparentActive = settings.transparent_background && !mangaActive;
  // インペイントは i2i 元をベース画像にするため、元画像とマスクの両方が要る
  const inpaintActive =
    settings.use_inpaint && source !== null && inpaintMask !== null;
  // 精密参照は V5 Full の節約モードでは効かない（設定は残したまま無効）。
  // V5 はインペイントと併用できず、衣装の参照は V5 だけ。参照画像が無ければ載せない
  const referenceSupported = supportsPreciseReference(settings.image_model);
  const referenceFormat = preciseReferenceFormat(settings.image_model);
  const referenceInpaintBlocked = referenceFormat === "v5" && inpaintActive;
  const sendableReferences = useMemo(() => {
    if (
      !settings.use_precise_reference ||
      !referenceSupported ||
      referenceFormat === null ||
      referenceInpaintBlocked
    ) {
      return [];
    }
    return references.filter((ref) =>
      isReferenceTypeSupported(ref.type, referenceFormat),
    );
  }, [
    referenceFormat,
    referenceInpaintBlocked,
    referenceSupported,
    references,
    settings.use_precise_reference,
  ]);
  const referenceActive = sendableReferences.length > 0;
  const referenceAnlasCost =
    sendableReferences.length * options.anlasPerReference;
  const referenceCast = useMemo(
    () => buildReferenceCast(sendableReferences),
    [sendableReferences],
  );
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

  // これまでの話: 開いているセッションの一覧にあるものだけを、生成した順（話の順）に並べる。
  // 一覧を読み込む前や、ほかのタブで消したエントリの ID は表示にも送信にも使わない
  const storyContextEntries = useMemo(() => {
    if (storyContextIds.length === 0) return [];
    const selected = new Set(storyContextIds);
    return entries
      .filter((entry) => selected.has(entry.id))
      .sort(compareEntriesByCreation);
  }, [entries, storyContextIds]);
  const storyContextEntryIds = useMemo(
    () => storyContextEntries.map((entry) => entry.id),
    [storyContextEntries],
  );
  const toggleStoryContextEntry = useCallback(
    (entryId: string) => {
      setStoryContextIds((prev) => {
        if (prev.includes(entryId)) return prev.filter((id) => id !== entryId);
        // 一覧に無くなった ID は数えずに捨ててから上限を見る
        const kept = prev.filter((id) => entries.some((e) => e.id === id));
        if (kept.length >= PROMPT_EXPANDER_STORY_CONTEXT_MAX) return prev;
        return [...kept, entryId];
      });
    },
    [entries],
  );
  const removeStoryContextEntry = useCallback((entryId: string) => {
    setStoryContextIds((prev) => prev.filter((id) => id !== entryId));
  }, []);
  const clearStoryContext = useCallback(() => setStoryContextIds([]), []);

  const setSource = useCallback((next: PromptExpanderSource | null) => {
    setSourceState(next);
  }, []);
  const clearSource = useCallback(() => setSourceState(null), []);
  const addReference = useCallback(
    (input: PromptExpanderReferenceInput) => {
      if (references.length >= PROMPT_EXPANDER_REFERENCE_MAX_COUNT) {
        return false;
      }
      setReferences((prev) =>
        prev.length >= PROMPT_EXPANDER_REFERENCE_MAX_COUNT
          ? prev
          : [...prev, createReference(input)],
      );
      return true;
    },
    [references.length],
  );
  const updateReference = useCallback(
    (id: string, patch: PromptExpanderReferencePatch) => {
      setReferences((prev) =>
        prev.map((ref) => {
          if (ref.id !== id) return ref;
          const next = { ...ref, ...patch };
          next.name = next.name.slice(0, PROMPT_EXPANDER_CAST_NAME_MAX_LENGTH);
          next.appearanceTags = next.appearanceTags.slice(
            0,
            PROMPT_EXPANDER_CAST_TAGS_MAX_LENGTH,
          );
          return next;
        }),
      );
    },
    [],
  );
  const removeReference = useCallback((id: string) => {
    setReferences((prev) => prev.filter((ref) => ref.id !== id));
  }, []);
  const clearReferences = useCallback(() => setReferences([]), []);
  const setInpaintMask = useCallback((next: PromptExpanderMask | null) => {
    setInpaintMaskState(next);
  }, []);
  const clearInpaintMask = useCallback(() => setInpaintMaskState(null), []);

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
  const selectEntryAsReference = useCallback(
    (entry: PromptExpanderEntry) => {
      const existing = references.find(
        (ref) => ref.kind === "entry" && ref.entryId === entry.id,
      );
      if (existing) {
        removeReference(existing.id);
        return;
      }
      addReference({
        kind: "entry",
        entryId: entry.id,
        thumbnailUrl: promptExpanderImageUrl(entry),
        label: entry.instruction || entry.final_prompt || entry.id,
      });
    },
    [addReference, references, removeReference],
  );

  const uploadImage = useCallback(
    async (
      file: File,
      uploadOptions: PromptExpanderUploadOptions,
    ): Promise<boolean> => {
      if (!uploadOptions.keepAsEntry && !uploadOptions.useAsSource) {
        return false;
      }
      // 精密参照向けのアップロードは i2i 元ではなく参照画像の一覧へ足す
      const assign = (input: PromptExpanderSource) => {
        if (uploadOptions.target === "reference") {
          addReference(input);
        } else {
          setSourceState(input);
        }
      };
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
            assign({
              kind: "entry",
              entryId: entry.id,
              thumbnailUrl: promptExpanderImageUrl(entry),
              label: uploadOptions.note?.trim() || file.name,
            });
          }
        } else if (uploadOptions.useAsSource) {
          assign({
            kind: "upload",
            uploadDataUrl: dataUrl,
            thumbnailUrl: dataUrl,
            label: uploadOptions.note?.trim() || file.name,
          });
        }
        return true;
      } catch (err) {
        reportError("Prompt Expander", err);
        return false;
      } finally {
        setUploading(false);
      }
    },
    [activeSession, addReference, bumpSessionEntryCount, reportError],
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
        // ネームから作ったプロンプトなら、ネームの下書き元のあらすじも残す（復元で欄を分けて戻すため）
        synopsis:
          fields.positiveOrigin?.source === "script"
            ? fields.positiveOrigin.synopsis
            : null,
        positive_expand_mode: fields.positiveOrigin?.mode ?? "off",
        negative_expand_mode: fields.negativeOrigin?.mode ?? "off",
        image_model: settings.image_model,
        text_model: settings.text_model,
        image_size: settings.image_size,
        source_kind: source?.kind ?? "none",
        manga_mode: mangaActive,
        manga_panel_count: mangaActive ? settings.manga_panel_count : null,
        transparent_background: transparentActive,
      };
      // 強調は透過が効くときだけ意味を持つ（V4.5 の白背景指定を効かせるため）
      if (transparentActive) {
        payload.transparent_emphasis = settings.transparent_emphasis;
      }
      // インペイントは i2i 元をベース画像に使うので、source と併せて載せる
      if (inpaintActive && inpaintMask) {
        if (inpaintMask.dataUrl) {
          payload.inpaint_mask = inpaintMask.dataUrl;
        } else if (inpaintMask.fromEntryId) {
          payload.inpaint_mask_entry_id = inpaintMask.fromEntryId;
        }
      }
      if (settings.seed !== null && settings.seed !== undefined) {
        payload.seed = settings.seed;
      }
      // 精密参照は i2i 元とは別の画像を、載せられるもの（ON・対応モデル・対応種別）だけ
      // 送る。強度はモデルの上限に収める（V4.5 は 1.0、V5 は 5.0）
      if (sendableReferences.length > 0 && referenceFormat !== null) {
        payload.references = sendableReferences.map((ref) =>
          toReferenceRequest(ref, referenceFormat),
        );
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
    [
      inpaintActive,
      inpaintMask,
      mangaActive,
      referenceFormat,
      sendableReferences,
      settings,
      source,
      transparentActive,
    ],
  );

  // 確認ゲートを通過した後の実際の生成リクエスト
  const postGenerate = useCallback(
    async (payload: PromptExpanderGenerateRequest) => {
      if (!activeSession) return;
      // 生成中に別のセッションを開くことがあるので、開始元のセッションを覚えておく
      const sessionId = activeSession.id;
      setGenerating(true);
      setGeneratingSessionId(sessionId);
      setLastGenerateOutcome(null);
      // 生成したら復元の取り消しは終わり（生成に使った内容が基準になる）
      setRestoreSnapshot(null);
      setError(null);
      try {
        const resp = await generatePromptExpanderImage(sessionId, payload);
        // 結果は開始元のセッションのもの。いま開いている履歴が別のセッションなら足さない
        if (activeSessionIdRef.current === resp.entry.session_id) {
          setEntries((prev) => [resp.entry, ...prev]);
        }
        bumpSessionEntryCount(sessionId, 1, resp.entry.image_url);
        applyAnlas(resp.anlas);
        setLastGenerateOutcome({
          status: "success",
          sessionId,
          entryId: resp.entry.id,
        });
      } catch (err) {
        reportError("Prompt Expander", err);
        setLastGenerateOutcome({
          status: "error",
          sessionId,
          message: toErrorMessage(err),
        });
      } finally {
        setGenerating(false);
        setGeneratingSessionId(null);
      }
    },
    [activeSession, applyAnlas, bumpSessionEntryCount, reportError],
  );

  const dismissGenerateOutcome = useCallback(
    () => setLastGenerateOutcome(null),
    [],
  );
  const entryRevealSeq = useRef(0);
  const requestEntryReveal = useCallback(
    (entryId: string, focus: PromptExpanderEntryRevealFocus = "image") => {
      entryRevealSeq.current += 1;
      setEntryRevealRequest({ entryId, seq: entryRevealSeq.current, focus });
    },
    [],
  );
  const completeEntryReveal = useCallback((seq: number) => {
    setEntryRevealRequest((prev) => (prev?.seq === seq ? null : prev));
  }, []);

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
      // 精密参照は参照 1 枚ごとに Anlas を消費するため、生成前に確認を挟む
      if (
        (payload.references?.length ?? 0) > 0 &&
        !readReferenceWarnSuppressed()
      ) {
        setPendingReferenceWarn(payload);
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
    (
      target: PromptExpanderExpansionTarget,
      err: unknown,
      field?: PromptExpanderPromptSource,
    ) => {
      if (err instanceof ApiError) {
        setExpansionError({
          target,
          field,
          code: err.code,
          message: err.message,
        });
      } else {
        setExpansionError({
          target,
          field,
          code: null,
          message: toErrorMessage(err),
        });
      }
    },
    [],
  );

  // 指示（あらすじ）欄かネーム欄の文から LLM でプロンプトを作り、プロンプト欄へ入れる。
  // 指示・ネームの欄は書き換えない。前のプロンプトは「元に戻す」用に控える
  const expandPositive = useCallback(
    async (field: PromptExpanderPromptSource) => {
      const instruction = (
        field === "script" ? scriptText : instructionText
      ).trim();
      if (!instruction) {
        setExpansionError({
          target: "positive",
          field,
          code: "empty_instruction",
          message: "empty_instruction",
        });
        return;
      }
      // ネームから作るときは、ネームの下書き元のあらすじも履歴に残す
      const synopsis =
        field === "script" ? instructionText.trim() || null : null;
      setExpansionError(null);
      // 依頼したセッション。応答までに別のセッションへ移っていたら、結果はこのセッションの書きかけにだけ入れる
      const requestSessionId = activeSessionIdRef.current;
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
          // プロンプト欄は作り直す対象なので「現在のプロンプト」としては渡さない
          // （保持すべき現在値は参照元エントリから継承する）。
          // キャラクタースロットは入力済みの現在値として渡す
          current_character_prompts: characterMode ? characterSlots : [],
          manga_mode: mangaActive,
          ...(mangaActive ? { manga: mangaRequest } : {}),
          // 背景透過 ON のときは背景・情景を描写しない規則を LLM に足す
          transparent_background: transparentActive,
          // 名前を付けた精密参照は、キャラ枠 ON のとき登場人物として渡す
          ...(characterMode && referenceCast.length > 0
            ? { cast: referenceCast }
            : {}),
          // これまでの話（前のページ）は漫画モードのときだけ渡す
          ...(mangaActive && storyContextEntryIds.length > 0
            ? { context_entry_ids: storyContextEntryIds }
            : {}),
        });
        const prompt = resp.positive_prompt ?? "";
        const slots =
          characterMode && resp.character_prompts?.length
            ? resp.character_prompts
            : null;
        const origin: PromptExpanderPositiveOrigin = {
          mode: effectivePositiveMode,
          instruction,
          source: field,
          synopsis,
        };
        if (activeSessionIdRef.current === requestSessionId) {
          setPromptUndo(
            positiveText.trim()
              ? {
                  prompt: positiveText,
                  characterMode,
                  characterSlots,
                  origin: positiveOrigin,
                  applied: prompt,
                }
              : null,
          );
          setPositiveText(prompt);
          if (slots) {
            setCharacterSlots(slots);
            setCharacterMode(true);
          }
          setPositiveOrigin(origin);
        } else if (requestSessionId) {
          updateStoredSessionDraft(requestSessionId, (draft) => ({
            ...draft,
            positiveText: prompt,
            characterSlots: slots ?? draft.characterSlots,
            positiveOrigin: origin,
            promptUndo: draft.positiveText.trim()
              ? {
                  prompt: draft.positiveText,
                  characterMode,
                  characterSlots: draft.characterSlots,
                  origin: draft.positiveOrigin,
                  applied: prompt,
                }
              : null,
          }));
        }
      } catch (err) {
        // 別のセッションへ移っていたら、そのセッションの欄にエラーを出さない
        if (activeSessionIdRef.current === requestSessionId) {
          failExpansion("positive", err, field);
        }
      } finally {
        setExpandingTarget(null);
      }
    },
    [
      characterMode,
      characterSlots,
      effectivePositiveMode,
      failExpansion,
      instructionText,
      language,
      mangaActive,
      mangaRequest,
      negativeMode,
      positiveOrigin,
      positiveText,
      referenceCast,
      scriptText,
      setCharacterMode,
      settings.image_model,
      settings.inherit_source_prompts,
      settings.text_model,
      sourceFields,
      storyContextEntryIds,
      transparentActive,
    ],
  );

  const undoPrompt = useCallback(() => {
    if (!promptUndo) return;
    setPositiveText(promptUndo.prompt);
    setCharacterMode(promptUndo.characterMode);
    setCharacterSlots(promptUndo.characterSlots);
    setPositiveOrigin(promptUndo.origin);
    setPromptUndo(null);
  }, [promptUndo, setCharacterMode]);

  // あらすじ欄から、記法付きのネームを下書きしてネーム欄へ入れる。あらすじ欄は書き換えない
  const draftScript = useCallback(async () => {
    const synopsis = instructionText.trim();
    if (!synopsis) {
      setExpansionError({
        target: "positive",
        field: "instruction",
        code: "empty_instruction",
        message: "empty_instruction",
      });
      return;
    }
    setExpansionError(null);
    // 依頼したセッション。応答までに別のセッションへ移っていたら、ネームはこのセッションの書きかけにだけ入れる
    const requestSessionId = activeSessionIdRef.current;
    setDraftingScript(true);
    try {
      const resp = await draftMangaScript({
        instruction: synopsis,
        image_model: settings.image_model,
        text_model: settings.text_model,
        language,
        manga: mangaRequest,
        // 名前を付けた精密参照の登場人物は、ネームの話者名に使わせる
        ...(referenceCast.length > 0 ? { cast: referenceCast } : {}),
        // これまでの話（前のページ）があれば、その続きとして下書きさせる
        ...(storyContextEntryIds.length > 0
          ? { context_entry_ids: storyContextEntryIds }
          : {}),
      });
      if (activeSessionIdRef.current === requestSessionId) {
        // 前のネームが空でも控える（「下書きしました」の案内と、空に戻す操作のため）
        setScriptUndo({ script: scriptText, applied: resp.script });
        setScriptText(resp.script);
      } else if (requestSessionId) {
        updateStoredSessionDraft(requestSessionId, (draft) => ({
          ...draft,
          scriptText: resp.script,
          scriptUndo: { script: draft.scriptText, applied: resp.script },
        }));
      }
    } catch (err) {
      if (activeSessionIdRef.current === requestSessionId) {
        failExpansion("positive", err, "instruction");
      }
    } finally {
      setDraftingScript(false);
    }
  }, [
    failExpansion,
    instructionText,
    language,
    mangaRequest,
    referenceCast,
    scriptText,
    settings.image_model,
    settings.text_model,
    storyContextEntryIds,
  ]);

  const undoScript = useCallback(() => {
    if (!scriptUndo) return;
    setScriptText(scriptUndo.script);
    setScriptUndo(null);
  }, [scriptUndo]);

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
    // 依頼したセッション。応答までに別のセッションへ移っていたら、結果はこのセッションの書きかけにだけ入れる
    const requestSessionId = activeSessionIdRef.current;
    // 今の変換カードは新しい結果が届くまで残す
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
      const card: PromptExpanderNegativeExpansion = {
        mode: negativeMode,
        negativePrompt: resp.negative_prompt ?? "",
      };
      if (activeSessionIdRef.current === requestSessionId) {
        setNegativeExpansion(card);
      } else if (requestSessionId) {
        updateStoredSessionDraft(requestSessionId, (draft) => ({
          ...draft,
          negativeExpansion: card,
        }));
      }
    } catch (err) {
      if (activeSessionIdRef.current === requestSessionId) {
        failExpansion("negative", err);
      }
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

  const applyNegativeExpansion = useCallback(() => {
    if (!negativeExpansion) return;
    setNegativeText(negativeExpansion.negativePrompt);
    setNegativeOrigin({ mode: negativeExpansion.mode });
    setNegativeExpansion(null);
    setExpansionError(null);
  }, [negativeExpansion]);

  const generateFromNegativeExpansion = useCallback(async () => {
    if (!negativeExpansion) return;
    const fields: GenerateFields = {
      positive: positiveText,
      characterMode,
      slots: characterSlots,
      negative: negativeExpansion.negativePrompt,
      positiveOrigin,
      negativeOrigin: { mode: negativeExpansion.mode },
    };
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
  }, [
    buildGeneratePayload,
    characterMode,
    characterSlots,
    generate,
    negativeExpansion,
    positiveOrigin,
    positiveText,
    validateForGenerate,
  ]);

  const discardNegativeExpansion = useCallback(() => {
    setNegativeExpansion(null);
    setExpansionError(null);
  }, []);

  const editNegativeExpansion = useCallback((negativePrompt: string) => {
    setNegativeExpansion((prev) => (prev ? { ...prev, negativePrompt } : prev));
  }, []);

  const confirmUsageWarn = useCallback(
    async (suppress: boolean) => {
      if (suppress) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      const payload = pendingUsageWarn;
      setPendingUsageWarn(null);
      if (!payload) return;
      // 精密参照も送る生成なら、続けて Anlas の確認へ進む
      if (
        (payload.references?.length ?? 0) > 0 &&
        !readReferenceWarnSuppressed()
      ) {
        setPendingReferenceWarn(payload);
        return;
      }
      await postGenerate(payload);
    },
    [pendingUsageWarn, postGenerate],
  );

  const cancelUsageWarn = useCallback(() => setPendingUsageWarn(null), []);

  const confirmReferenceWarn = useCallback(
    async (suppress: boolean) => {
      if (suppress) {
        writeStorageFlag(
          "session",
          PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY,
          true,
        );
      }
      const payload = pendingReferenceWarn;
      setPendingReferenceWarn(null);
      if (payload) {
        await postGenerate(payload);
      }
    },
    [pendingReferenceWarn, postGenerate],
  );

  const cancelReferenceWarn = useCallback(
    () => setPendingReferenceWarn(null),
    [],
  );

  // 「欄へ復元」で精密参照も戻す。キャラクターは立ち絵の URL を取り直すので非同期になり、
  // 続けて別のエントリを復元したときは古い結果を捨てる
  const referenceRestoreSeq = useRef(0);
  const restoreReferences = useCallback(
    async (entryRefs: PromptExpanderEntryReference[]) => {
      referenceRestoreSeq.current += 1;
      const seq = referenceRestoreSeq.current;
      const restored = await Promise.all(
        entryRefs.map(async (ref): Promise<PromptExpanderReference | null> => {
          const settings = {
            type: ref.type,
            includeOutfit: ref.include_outfit ?? false,
            strength: ref.strength,
            fidelity:
              ref.fidelity ?? DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY,
          };
          const cast = {
            name: ref.name ?? "",
            appearanceTags: ref.appearance_tags ?? "",
          };
          if (ref.kind === "entry" && ref.entry_id) {
            const source = entries.find((e) => e.id === ref.entry_id);
            return createReference(
              {
                kind: "entry",
                entryId: ref.entry_id,
                thumbnailUrl: promptExpanderImageUrl(
                  `/prompt-expander/images/${ref.entry_id}`,
                ),
                label:
                  source?.instruction ||
                  source?.final_prompt ||
                  ref.name ||
                  ref.entry_id,
                ...cast,
              },
              settings,
            );
          }
          if (ref.kind === "history" && ref.history_id) {
            return createReference(
              {
                kind: "history",
                historyId: ref.history_id,
                thumbnailUrl: mediaUrl(`/history/images/${ref.history_id}`),
                label: ref.name || t("promptExpander.picker.playLabelFallback"),
                ...cast,
              },
              settings,
            );
          }
          if (ref.kind === "character" && ref.character_preset_id) {
            try {
              const preset = await getCharacterPreset(ref.character_preset_id);
              const url = preset.portrait_url ?? preset.thumbnail_url;
              if (!url) return null;
              return createReference(
                {
                  kind: "character",
                  characterPresetId: preset.id,
                  thumbnailUrl: mediaUrl(url),
                  label: preset.name,
                  name: ref.name ?? preset.name,
                  appearanceTags:
                    ref.appearance_tags ?? preset.appearance_tags ?? "",
                },
                settings,
              );
            } catch {
              // 削除されたキャラクターは戻せないので外す（件数は下で知らせる）
              return null;
            }
          }
          // アップロードした参照は画像を保存していないので戻せない
          return null;
        }),
      );
      if (seq !== referenceRestoreSeq.current) return;
      const kept = restored
        .filter((ref): ref is PromptExpanderReference => ref !== null)
        .slice(0, PROMPT_EXPANDER_REFERENCE_MAX_COUNT);
      setReferences(kept);
      const skipped = entryRefs.length - kept.length;
      if (skipped > 0) {
        showNotification(
          "warning",
          t("promptExpander.reference.restoreSkippedTitle"),
          t("promptExpander.reference.restoreSkippedBody", { count: skipped }),
        );
      }
    },
    [entries, showNotification, t],
  );

  const restoreEntry = useCallback(
    (entry: PromptExpanderEntry) => {
      // 欄に書きかけの内容があれば、復元で置き換わるものを控えて「元に戻す」を出す
      const hasDraft =
        instructionText.trim().length > 0 ||
        scriptText.trim().length > 0 ||
        positiveText.trim().length > 0 ||
        negativeText.trim().length > 0 ||
        characterSlots.some((slot) => slot.trim().length > 0) ||
        negativeExpansion !== null;
      const expandMode = entry.positive_expand_mode;
      const instruction = (entry.instruction ?? "").trim();
      const synopsis = (entry.synopsis ?? "").trim();
      const finalPrompt = entry.final_prompt ?? "";
      // LLM で作ったエントリは、指示（ネームから作ったならあらすじとネーム）とプロンプトを
      // それぞれの欄へ戻す（そのまま再生成も、指示を直して作り直しもできる）
      const expanded =
        entry.kind === "generated" &&
        expandMode !== "off" &&
        instruction.length > 0 &&
        instruction !== finalPrompt.trim();
      const fromScript = expanded && synopsis.length > 0;
      const restoredPositive = finalPrompt;
      setInstructionText(expanded ? (fromScript ? synopsis : instruction) : "");
      setScriptText(fromScript ? instruction : "");
      setPositiveText(restoredPositive);
      setNegativeText(entry.final_negative_prompt ?? "");
      const slots = entry.character_prompts ?? [];
      setCharacterMode(slots.length > 0);
      setCharacterSlots(slots);
      setPositiveOrigin(
        expanded
          ? {
              mode: expandMode,
              instruction,
              source: fromScript ? "script" : "instruction",
              synopsis: fromScript ? synopsis : null,
            }
          : null,
      );
      setNegativeOrigin(null);
      setExpansionError(null);
      // 欄を丸ごと置き換えるので、変換カードと元に戻す用の控えも手放す
      setNegativeExpansion(null);
      setPromptUndo(null);
      setScriptUndo(null);
      // 「直接書く」のままだと戻した指示やネームが見えないので、LLM で作るへ切り替える
      if (expanded) setPromptInputMode("assist");
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
      // 背景透過の印も戻す。精密参照は参照付きエントリのときだけ ON にし、
      // 参照画像と画像ごとの設定は i2i 元と同じく復元しない（参照なしのエントリでは触らない）
      patch.transparent_background = Boolean(entry.transparent_background);
      if ((entry.references?.length ?? 0) > 0) {
        patch.use_precise_reference = true;
        void restoreReferences(entry.references);
      }
      // インペイントのマスクは保存済みなので、同じ領域で差分を作り続けられるよう戻す
      // （ベース画像は i2i 元と同じく復元しない。インペイントでないエントリでは触らない）
      if (entry.inpaint && entry.mask_url) {
        patch.use_inpaint = true;
        setInpaintMaskState({
          fromEntryId: entry.id,
          thumbnailUrl: promptExpanderImageUrl(entry.mask_url),
          label: entry.instruction || entry.id,
        });
      }
      if (hasDraft) {
        // 戻すのは、この復元で変える設定の今の値だけ
        const previousSettings: Record<string, unknown> = {};
        for (const key of Object.keys(patch) as Array<
          keyof PromptExpanderSettings
        >) {
          previousSettings[key] = settings[key];
        }
        setRestoreSnapshot({
          instructionText,
          scriptText,
          positiveText,
          negativeText,
          characterMode,
          characterSlots,
          positiveOrigin,
          negativeOrigin,
          negativeExpansion,
          promptUndo,
          scriptUndo,
          promptInputMode,
          settings: previousSettings as PromptExpanderSettingsPatch,
          references,
          inpaintMask,
          restoredPositive,
        });
      } else {
        setRestoreSnapshot(null);
      }
      if (Object.keys(patch).length > 0) {
        void updateSettings(patch);
      }
    },
    [
      characterMode,
      characterSlots,
      inpaintMask,
      instructionText,
      negativeExpansion,
      negativeOrigin,
      negativeText,
      positiveOrigin,
      positiveText,
      promptInputMode,
      promptUndo,
      references,
      restoreReferences,
      scriptText,
      scriptUndo,
      setCharacterMode,
      setPromptInputMode,
      settings,
      updateSettings,
    ],
  );

  const undoRestore = useCallback(() => {
    const snapshot = restoreSnapshot;
    if (!snapshot) return;
    // 復元で始めた精密参照の読み直しが後から終わっても、戻した参照を上書きしないようにする
    referenceRestoreSeq.current += 1;
    setInstructionText(snapshot.instructionText);
    setScriptText(snapshot.scriptText);
    setPositiveText(snapshot.positiveText);
    setNegativeText(snapshot.negativeText);
    setCharacterMode(snapshot.characterMode);
    setCharacterSlots(snapshot.characterSlots);
    setPositiveOrigin(snapshot.positiveOrigin);
    setNegativeOrigin(snapshot.negativeOrigin);
    setNegativeExpansion(snapshot.negativeExpansion);
    setPromptUndo(snapshot.promptUndo);
    setScriptUndo(snapshot.scriptUndo);
    setPromptInputMode(snapshot.promptInputMode);
    setExpansionError(null);
    setReferences(snapshot.references);
    setInpaintMaskState(snapshot.inpaintMask);
    if (Object.keys(snapshot.settings).length > 0) {
      void updateSettings(snapshot.settings);
    }
    setRestoreSnapshot(null);
  }, [restoreSnapshot, setCharacterMode, setPromptInputMode, updateSettings]);

  const restoreUndo = useMemo(
    () =>
      restoreSnapshot
        ? { restoredPositive: restoreSnapshot.restoredPositive }
        : null,
    [restoreSnapshot],
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
        synopsis:
          entry.positive_expand_mode !== "off"
            ? (entry.synopsis ?? null)
            : null,
        positive_expand_mode: entry.positive_expand_mode,
        negative_expand_mode: entry.negative_expand_mode,
        image_model: entry.image_model ?? settings.image_model,
        text_model: entry.text_model ?? settings.text_model,
        image_size: entry.image_size ?? settings.image_size,
        source_kind: "none",
        manga_mode: entry.manga_mode,
        manga_panel_count: entry.manga_mode ? entry.manga_panel_count : null,
        transparent_background: Boolean(entry.transparent_background),
      };
      // 強調段数はエントリに保存していないので、現在の設定に従う
      // （送らないとルーターの既定値が使われ、「なし」にしていても強調が付く）
      if (entry.transparent_background) {
        payload.transparent_emphasis = settings.transparent_emphasis;
      }
      // 精密参照も同じ参照元で再現する。アップロード参照は画像を保持していないので外し、
      // 外した枚数を知らせる（参照の数が変わると絵が変わるため黙って落とさない）
      const entryReferences = entry.references ?? [];
      const reproducible = entryReferences.filter(
        (ref) =>
          (ref.kind === "history" && ref.history_id) ||
          (ref.kind === "entry" && ref.entry_id) ||
          (ref.kind === "character" && ref.character_preset_id),
      );
      if (reproducible.length > 0) {
        payload.references = reproducible.map((ref) => ({
          kind: ref.kind,
          ...(ref.history_id ? { history_id: ref.history_id } : {}),
          ...(ref.entry_id ? { entry_id: ref.entry_id } : {}),
          ...(ref.character_preset_id
            ? { character_preset_id: ref.character_preset_id }
            : {}),
          type: ref.type,
          include_outfit: ref.include_outfit ?? false,
          strength: ref.strength,
          fidelity: ref.fidelity ?? DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY,
          ...(ref.name ? { name: ref.name } : {}),
          ...(ref.appearance_tags
            ? { appearance_tags: ref.appearance_tags }
            : {}),
        }));
      }
      const skipped = entryReferences.length - reproducible.length;
      if (skipped > 0) {
        showNotification(
          "warning",
          t("promptExpander.reference.regenerateSkippedTitle"),
          t("promptExpander.reference.regenerateSkippedBody", {
            count: skipped,
          }),
        );
      }
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
        // 保存済みマスクを使い回して、同じ領域のまま作り直す（表情差分の連続生成）。
        // 元画像を再現できないアップロード由来のときはマスクも落とす
        if (entry.inpaint) {
          payload.inpaint_mask_entry_id = entry.id;
        }
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
      settings.transparent_emphasis,
      showNotification,
      t,
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
        setStoryContextIds((prev) => prev.filter((storyId) => storyId !== id));
        // 消したエントリを指す参照だけ外す（他の参照は残す）
        setReferences((prev) =>
          prev.filter((ref) => !(ref.kind === "entry" && ref.entryId === id)),
        );
        // マスクの実体は元エントリと一緒に消えるので、参照だけ残さない
        if (inpaintMask?.fromEntryId === id) {
          setInpaintMaskState(null);
        }
      } catch (err) {
        reportError("Prompt Expander", err);
      }
    },
    [bumpSessionEntryCount, entries, inpaintMask, reportError, source],
  );

  const suggestCharacters = useCallback(
    async (count: number, mode: PromptExpandMode) => {
      setSuggesting(true);
      try {
        // プロンプト → ネーム → 指示の順に、最初に書いてある欄を下書きとして渡す
        const draft =
          positiveText.trim() || scriptText.trim() || instructionText.trim();
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
    [
      instructionText,
      language,
      positiveText,
      scriptText,
      settings.image_model,
      settings.text_model,
    ],
  );

  // 生成ボタンの活性条件（理由は画面側で i18n キーに変換する）
  const generateDisabledReason = useMemo<string | null>(() => {
    if (!options.novelaiConfigured) return "novelai_not_configured";
    if (!activeSession) return "no_session";
    if (expanding || generating || draftingScript) return "busy";
    if (negativeExpansion) return "pending_expansion";
    if (characterSlotsOverCap) return "too_many_characters";
    if (!positiveText.trim()) return "empty_prompt";
    return null;
  }, [
    activeSession,
    characterSlotsOverCap,
    draftingScript,
    expanding,
    generating,
    negativeExpansion,
    options.novelaiConfigured,
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
      generating,
      generatingSessionId,
      lastGenerateOutcome,
      dismissGenerateOutcome,
      entryRevealRequest,
      requestEntryReveal,
      completeEntryReveal,
      uploading,
      suggesting,
      error,
      clearError,
      expansionError,
      clearExpansionError,
      source,
      references,
      sendableReferences,
      referenceCast,
      referenceSupported,
      referenceFormat,
      referenceInpaintBlocked,
      referenceActive,
      referenceAnlasCost,
      transparentActive,
      inpaintMask,
      inpaintActive,
      promptInputMode,
      instructionText,
      scriptText,
      positiveText,
      promptUndo,
      scriptUndo,
      positiveMode,
      positiveOrigin,
      characterMode,
      characterSlots,
      characterSlotsOverCap,
      mangaActive,
      storyContextEntries,
      storyContextEntryIds,
      effectivePositiveMode,
      negativeText,
      negativeMode,
      negativeOrigin,
      negativeExpansion,
      pendingUsageWarn,
      pendingReferenceWarn,
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
      addReference,
      updateReference,
      removeReference,
      clearReferences,
      setInpaintMask,
      clearInpaintMask,
      setPromptInputMode,
      setInstructionText,
      setScriptText,
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
      undoScript,
      toggleStoryContextEntry,
      removeStoryContextEntry,
      clearStoryContext,
      undoPrompt,
      applyNegativeExpansion,
      generateFromNegativeExpansion,
      discardNegativeExpansion,
      editNegativeExpansion,
      runGenerate,
      confirmUsageWarn,
      cancelUsageWarn,
      confirmReferenceWarn,
      cancelReferenceWarn,
      restoreEntry,
      restoreUndo,
      undoRestore,
      regenerateEntry,
      selectEntryAsSource,
      selectEntryAsReference,
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
      generating,
      generatingSessionId,
      lastGenerateOutcome,
      dismissGenerateOutcome,
      entryRevealRequest,
      requestEntryReveal,
      completeEntryReveal,
      uploading,
      suggesting,
      error,
      clearError,
      expansionError,
      clearExpansionError,
      source,
      references,
      sendableReferences,
      referenceCast,
      referenceSupported,
      referenceFormat,
      referenceInpaintBlocked,
      referenceActive,
      referenceAnlasCost,
      transparentActive,
      inpaintMask,
      inpaintActive,
      promptInputMode,
      instructionText,
      scriptText,
      positiveText,
      promptUndo,
      scriptUndo,
      positiveMode,
      positiveOrigin,
      characterMode,
      characterSlots,
      characterSlotsOverCap,
      mangaActive,
      storyContextEntries,
      storyContextEntryIds,
      effectivePositiveMode,
      negativeText,
      negativeMode,
      negativeOrigin,
      negativeExpansion,
      pendingUsageWarn,
      pendingReferenceWarn,
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
      addReference,
      updateReference,
      removeReference,
      clearReferences,
      setInpaintMask,
      clearInpaintMask,
      setCharacterMode,
      setPromptInputMode,
      addCharacterSlot,
      updateCharacterSlot,
      removeCharacterSlot,
      uploadImage,
      expandPositive,
      expandNegative,
      draftScript,
      undoScript,
      toggleStoryContextEntry,
      removeStoryContextEntry,
      clearStoryContext,
      undoPrompt,
      applyNegativeExpansion,
      generateFromNegativeExpansion,
      discardNegativeExpansion,
      editNegativeExpansion,
      runGenerate,
      confirmUsageWarn,
      cancelUsageWarn,
      confirmReferenceWarn,
      cancelReferenceWarn,
      restoreEntry,
      restoreUndo,
      undoRestore,
      regenerateEntry,
      selectEntryAsSource,
      selectEntryAsReference,
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
