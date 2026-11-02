/**
 * BGM の環境設定（ミュート/音量）の永続化。
 *
 * Adventure のループ再生（useAdventureBgm）と BGM テスト画面が同じ音量を
 * 共有できるように、localStorage の読み書きをここへ集約する。
 * サロン経営の BGM は別に持つ。TSF シナリオで鳴らしていても、サロンを初めて
 * 開いたときに不意に鳴らさないため(初回はどちらもミュートから始める)。
 * サロンの効果音(salon_se)も同じ形で別に持ち、初回はミュートにする。
 */

export const BGM_PREFS_STORAGE_KEY = "adventure_bgm_prefs";
export const SALON_BGM_PREFS_STORAGE_KEY = "salon_bgm_prefs";
export const SALON_SE_PREFS_STORAGE_KEY = "salon_se_prefs";

/** BGM の設定の置き場所。adventure は TSF シナリオと BGM テスト画面、salon_se はサロンの効果音 */
export type BgmPrefsScope = "adventure" | "salon" | "salon_se";

const STORAGE_KEYS: Record<BgmPrefsScope, string> = {
  adventure: BGM_PREFS_STORAGE_KEY,
  salon: SALON_BGM_PREFS_STORAGE_KEY,
  salon_se: SALON_SE_PREFS_STORAGE_KEY,
};

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

export function loadBgmPreferences(
  scope: BgmPrefsScope = "adventure",
): BgmPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS[scope]);
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

export function saveBgmPreferences(
  prefs: BgmPreferences,
  scope: BgmPrefsScope = "adventure",
): void {
  try {
    localStorage.setItem(STORAGE_KEYS[scope], JSON.stringify(prefs));
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
