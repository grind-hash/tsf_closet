/**
 * BGM の環境設定（ミュート/音量）の永続化。
 *
 * Adventure のループ再生（useAdventureBgm）と BGM テスト画面が同じ音量を
 * 共有できるように、localStorage の読み書きをここへ集約する。
 */

export const BGM_PREFS_STORAGE_KEY = "adventure_bgm_prefs";

export interface BgmPreferences {
  muted: boolean;
  volume: number;
}

// 初回利用時は必ずミュートにする（自動再生の不意打ちを避ける）
export const defaultBgmPreferences: BgmPreferences = {
  muted: true,
  volume: 0.5,
};

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function loadBgmPreferences(): BgmPreferences {
  try {
    const raw = localStorage.getItem(BGM_PREFS_STORAGE_KEY);
    if (!raw) {
      return { ...defaultBgmPreferences };
    }
    const parsed = JSON.parse(raw) as Partial<BgmPreferences>;
    return {
      muted:
        typeof parsed.muted === "boolean"
          ? parsed.muted
          : defaultBgmPreferences.muted,
      volume:
        typeof parsed.volume === "number"
          ? clamp01(parsed.volume)
          : defaultBgmPreferences.volume,
    };
  } catch {
    return { ...defaultBgmPreferences };
  }
}

export function saveBgmPreferences(prefs: BgmPreferences): void {
  try {
    localStorage.setItem(BGM_PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage が利用できない環境では無視する
  }
}

/**
 * ミュート状態には触れず音量だけを更新する。BGM テスト画面のように
 * 明示的なユーザー操作で鳴らす画面から、本編の音量設定を共有するために使う。
 */
export function saveBgmVolume(volume: number): void {
  const current = loadBgmPreferences();
  saveBgmPreferences({ ...current, volume: clamp01(volume) });
}
