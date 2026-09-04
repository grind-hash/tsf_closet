/**
 * Adventure のトークモードの音声入力(マイク)設定。
 * ブラウザ機能(Web Speech API)のトグルなので、読み上げ設定と同じく
 * localStorage に持つ。自動送信は既定 OFF(認識結果を確認してから送る)。
 */

export const SPEECH_INPUT_PREFS_STORAGE_KEY = "adventure_speech_input_prefs";

export interface SpeechInputPreferences {
  /** 認識が確定したらそのまま送信する */
  autoSend: boolean;
}

export const DEFAULT_SPEECH_INPUT_PREFERENCES: SpeechInputPreferences = {
  autoSend: false,
};

export function loadSpeechInputPreferences(): SpeechInputPreferences {
  try {
    const raw = localStorage.getItem(SPEECH_INPUT_PREFS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SPEECH_INPUT_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<SpeechInputPreferences>;
    return {
      autoSend: parsed.autoSend === true,
    };
  } catch {
    return { ...DEFAULT_SPEECH_INPUT_PREFERENCES };
  }
}

export function saveSpeechInputPreferences(
  prefs: SpeechInputPreferences,
): void {
  try {
    localStorage.setItem(
      SPEECH_INPUT_PREFS_STORAGE_KEY,
      JSON.stringify({ autoSend: prefs.autoSend }),
    );
  } catch {
    // 保存できなくても音声入力自体は動く
  }
}
