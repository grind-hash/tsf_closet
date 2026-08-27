/**
 * Adventure のセリフ読み上げ(AivisSpeech)の ON/OFF と音量。
 * BGM と同じく localStorage に持ち、既定は OFF(不意に音を出さない)。
 */
import { clamp01 } from "./bgmPreferences";

export const VOICE_PREFS_STORAGE_KEY = "adventure_voice_prefs";

export interface VoicePreferences {
  enabled: boolean;
  /** 0.0〜1.0 */
  volume: number;
}

export const DEFAULT_VOICE_PREFERENCES: VoicePreferences = {
  enabled: false,
  volume: 1,
};

export function loadVoicePreferences(): VoicePreferences {
  try {
    const raw = localStorage.getItem(VOICE_PREFS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_VOICE_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<VoicePreferences>;
    return {
      enabled: parsed.enabled === true,
      volume:
        typeof parsed.volume === "number" && Number.isFinite(parsed.volume)
          ? clamp01(parsed.volume)
          : DEFAULT_VOICE_PREFERENCES.volume,
    };
  } catch {
    return { ...DEFAULT_VOICE_PREFERENCES };
  }
}

export function saveVoicePreferences(prefs: VoicePreferences): void {
  try {
    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({ enabled: prefs.enabled, volume: clamp01(prefs.volume) }),
    );
  } catch {
    // 保存できなくても読み上げ自体は動く
  }
}
