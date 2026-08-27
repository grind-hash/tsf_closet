/**
 * Adventure のセリフ読み上げ(AivisSpeech)の ON/OFF と音量と再生速度。
 * BGM と同じく localStorage に持ち、既定は OFF(不意に音を出さない)。
 */
import { clamp01 } from "./bgmPreferences";

export const VOICE_PREFS_STORAGE_KEY = "adventure_voice_prefs";

/** 再生速度の下限/上限。HTMLMediaElement.playbackRate に直接渡す */
export const MIN_VOICE_SPEED = 0.5;
export const MAX_VOICE_SPEED = 2;

/** UI で選べる再生速度。チャットの音声バーと同じ刻みに揃えている */
export const VOICE_SPEED_OPTIONS = [0.75, 1, 1.25, 1.5, 2] as const;

export interface VoicePreferences {
  enabled: boolean;
  /** 0.0〜1.0 */
  volume: number;
  /** 再生速度の倍率。1.0 が等速 */
  speed: number;
}

// 音声の初期音量は 100% ではなく 50% にする(BGM と同じ)
export const DEFAULT_VOICE_PREFERENCES: VoicePreferences = {
  enabled: false,
  volume: 0.5,
  speed: 1,
};

export function clampVoiceSpeed(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_VOICE_PREFERENCES.speed;
  return Math.min(MAX_VOICE_SPEED, Math.max(MIN_VOICE_SPEED, value));
}

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
      speed:
        typeof parsed.speed === "number"
          ? clampVoiceSpeed(parsed.speed)
          : DEFAULT_VOICE_PREFERENCES.speed,
    };
  } catch {
    return { ...DEFAULT_VOICE_PREFERENCES };
  }
}

export function saveVoicePreferences(prefs: VoicePreferences): void {
  try {
    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({
        enabled: prefs.enabled,
        volume: clamp01(prefs.volume),
        speed: clampVoiceSpeed(prefs.speed),
      }),
    );
  } catch {
    // 保存できなくても読み上げ自体は動く
  }
}
