import type {
  AdventureNarrationVoice,
  AdventureSpeechStyle,
} from "../apis/adventure";
import {
  NARRATION_PRONOUN_MAX_LENGTH,
  NARRATION_VOICES,
  SETUP_PREFS_STORAGE_KEY,
  SPEECH_CUSTOM_MAX_LENGTH,
  SPEECH_STYLES,
} from "../constants/adventure";

// Adventure セットアップ画面の設定値（localStorage）の読み出しと正規化。

export type AdventureSetupPrefs = {
  narrationVoice: AdventureNarrationVoice;
  narrationPronoun: string;
  /** 主人公のセリフの口調。攻略対象の口調はrun固有なので保存しない */
  speechStyle: AdventureSpeechStyle;
  speechCustom: string;
  enableCompositeScene: boolean;
  /** 対面会話モード(romance のみ)。既定 OFF */
  companionMode: boolean;
  /** 対面会話モードで描く 3D モデル(VRM)の登録 ID。"" は「なし(立ち絵)」 */
  companionAvatarId: string;
  /** romance の主人公(自分)。テンプレキャラID または __session__。次回にも引き継ぐ */
  romancePlayerCharacterId: string;
  /** 主人公を「セッションの姿」にしたときのセッションID */
  romancePlayerSessionId: string;
  /** romance の主人公の呼び名。"" は選択したキャラクターの名前に従う */
  romancePlayerName: string;
  /** run 単位のNovelAI画像モデル。"default" はグローバル設定に従う */
  imageModel: string;
  /** 持ち物システム(全プリセット)。既定 OFF */
  inventoryEnabled: boolean;
};

export function readSetupPrefs(): Partial<AdventureSetupPrefs> {
  try {
    const saved = localStorage.getItem(SETUP_PREFS_STORAGE_KEY);
    if (!saved) return {};
    const parsed: unknown = JSON.parse(saved);
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as Partial<AdventureSetupPrefs>;
  } catch {
    return {};
  }
}

export function normalizeNarrationVoice(
  value: unknown,
): AdventureNarrationVoice | null {
  return NARRATION_VOICES.includes(value as AdventureNarrationVoice)
    ? (value as AdventureNarrationVoice)
    : null;
}

export function normalizeNarrationPronoun(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return trimmed.slice(0, NARRATION_PRONOUN_MAX_LENGTH);
}

export function normalizeSpeechStyle(
  value: unknown,
): AdventureSpeechStyle | null {
  return SPEECH_STYLES.includes(value as AdventureSpeechStyle)
    ? (value as AdventureSpeechStyle)
    : null;
}

export function normalizeSpeechCustom(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return value.trim().slice(0, SPEECH_CUSTOM_MAX_LENGTH);
}
