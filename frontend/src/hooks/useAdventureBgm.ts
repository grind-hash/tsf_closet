/**
 * Adventure モード専用の BGM 再生 hook。
 *
 * LLM は semantic key（AdventureBgmKey）だけを返し、ファイル解決・再生・
 * fade・loop・mute・volume・fallback・autoplay 対応はすべてこの hook が担う。
 * 同一キーの連続受信では Audio 要素に一切触れず、キーが変わったときだけ
 * fade out → 停止 → 差し替え → loop 再生 → fade in を行う。
 * BGM は補助機能であり、失敗してもストーリー進行を妨げない。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { AdventureBgmKey } from "../apis/adventure";
import { fetchAdventureBgmCatalog } from "../apis/adventure";

/**
 * semantic key と音声URLの対応。バックエンドのカタログJSONが定義し、
 * GET /adventure/bgm で取得する。LLM にはファイル名を一切見せない。
 */
interface BgmCatalogState {
  defaultKey: string;
  files: Record<string, string>;
}

/** 曲切替時の fade 時間。要件は 500〜1000ms 程度 */
export const BGM_FADE_OUT_MS = 800;
export const BGM_FADE_IN_MS = 400;

// BGM の環境設定（ミュート/音量）。初回利用時は必ずミュートにし、
// localStorage に永続化して次回アクセス時に復元する。
export const BGM_PREFS_STORAGE_KEY = "adventure_bgm_prefs";

export interface BgmPreferences {
  muted: boolean;
  volume: number;
}

const defaultBgmPreferences: BgmPreferences = {
  muted: true,
  volume: 0.5,
};

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function loadBgmPreferences(): BgmPreferences {
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

function saveBgmPreferences(prefs: BgmPreferences): void {
  try {
    localStorage.setItem(BGM_PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage が利用できない環境では無視する
  }
}

type BgmPhase = "idle" | "playing" | "fading_out" | "blocked";

interface BgmFade {
  from: number;
  to: number;
  startedAt: number;
  durationMs: number;
  onDone?: () => void;
}

export interface UseAdventureBgmResult {
  muted: boolean;
  /** マスター音量 0.0〜1.0。表示側で 0〜100% に換算する */
  volume: number;
  /** autoplay 制限で play() が拒否され、ユーザー操作待ちの間 true */
  autoplayBlocked: boolean;
  setMuted: (next: boolean) => void;
  setVolume: (next: number) => void;
}

/**
 * `bgmKey` が示す BGM をループ再生する。null/undefined は停止（run 未ロード時）。
 * 呼び出し側で旧 run のキー欠落を "daily" に正規化してから渡すこと。
 */
export function useAdventureBgm(
  bgmKey: AdventureBgmKey | null | undefined,
): UseAdventureBgmResult {
  const [prefs, setPrefs] = useState<BgmPreferences>(loadBgmPreferences);
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);
  // カタログは ref に持ち、既存 callback 群の依存配列を増やさない。
  // ロード完了だけ state にして、到着時にキー変更 effect を再評価させる
  const catalogRef = useRef<BgmCatalogState | null>(null);
  const [catalogLoaded, setCatalogLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAdventureBgmCatalog()
      .then((catalog) => {
        if (cancelled) return;
        const files: Record<string, string> = {};
        for (const track of catalog.tracks) {
          files[track.key] = track.url;
        }
        catalogRef.current = { defaultKey: catalog.default_key, files };
        setCatalogLoaded(true);
      })
      .catch((error) => {
        // BGM は補助機能。カタログが取れなくてもストーリー進行を妨げない
        console.warn("Adventure BGM カタログの取得に失敗しました", error);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 未知キーは既定曲へ倒す。カタログ未ロード時は null */
  const resolveBgmUrl = useCallback((key: AdventureBgmKey): string | null => {
    const catalog = catalogRef.current;
    if (!catalog) return null;
    return catalog.files[key] ?? catalog.files[catalog.defaultKey] ?? null;
  }, []);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const phaseRef = useRef<BgmPhase>("idle");
  /** Audio 要素に読み込ませたキー（fallback 中もリクエストキーを保持） */
  const currentKeyRef = useRef<AdventureBgmKey | null>(null);
  /** 最後に要求されたキー。fade 完了時にここを読むことで連続変更を1回に収束させる */
  const targetKeyRef = useRef<AdventureBgmKey | null>(null);
  /** fade 係数 0〜1。実効音量 = master × fade 係数 */
  const fadeFactorRef = useRef(0);
  const fadeRef = useRef<BgmFade | null>(null);
  const rafRef = useRef<number | null>(null);
  const mutedRef = useRef(prefs.muted);
  const volumeRef = useRef(prefs.volume);
  /** キーごとに一度だけ daily へ fallback するためのフラグ */
  const fallbackTriedRef = useRef(false);
  const retryHandlerRef = useRef<(() => void) | null>(null);

  const applyEffectiveVolume = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = clamp01(volumeRef.current) * clamp01(fadeFactorRef.current);
  }, []);

  const clearRetryListeners = useCallback(() => {
    const handler = retryHandlerRef.current;
    if (!handler) return;
    document.removeEventListener("pointerdown", handler);
    document.removeEventListener("keydown", handler);
    retryHandlerRef.current = null;
  }, []);

  const stopFade = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    fadeRef.current = null;
  }, []);

  const startFade = useCallback(
    (to: number, durationMs: number, onDone?: () => void) => {
      stopFade();
      const fade: BgmFade = {
        from: fadeFactorRef.current,
        to,
        startedAt: performance.now(),
        durationMs,
        onDone,
      };
      fadeRef.current = fade;
      const tick = () => {
        if (fadeRef.current !== fade) return;
        // タイムスタンプ基準なのでタブ非アクティブでもドリフトせず完了する
        const progress =
          fade.durationMs <= 0
            ? 1
            : clamp01((performance.now() - fade.startedAt) / fade.durationMs);
        fadeFactorRef.current = fade.from + (fade.to - fade.from) * progress;
        applyEffectiveVolume();
        if (progress >= 1) {
          fadeRef.current = null;
          rafRef.current = null;
          fade.onDone?.();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [applyEffectiveVolume, stopFade],
  );

  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (audioRef.current) {
      return audioRef.current;
    }
    const audio = new Audio();
    audio.loop = true;
    audio.preload = "auto";
    audio.addEventListener("error", () => {
      // クリーンアップ済み要素の遅延イベントは無視する(StrictMode の
      // 再マウントや画面離脱後に fallback 再生を復活させない)
      if (audioRef.current !== audio) return;
      // ロード失敗はストーリー進行を妨げず、既定曲へ一度だけ fallback する
      console.warn("Adventure BGM の読み込みに失敗しました", audio.error);
      const catalog = catalogRef.current;
      const fallbackUrl = catalog ? catalog.files[catalog.defaultKey] : null;
      if (
        !fallbackTriedRef.current &&
        catalog &&
        fallbackUrl &&
        currentKeyRef.current !== catalog.defaultKey
      ) {
        fallbackTriedRef.current = true;
        audio.src = fallbackUrl;
        void tryPlayRef.current?.();
        return;
      }
      audio.pause();
      phaseRef.current = "idle";
    });
    audioRef.current = audio;
    return audio;
  }, []);

  // tryPlay ⇄ error リスナーの相互参照を ref 経由で解決する
  const tryPlayRef = useRef<(() => Promise<void>) | null>(null);

  const tryPlay = useCallback(async () => {
    const audio = ensureAudio();
    audio.muted = mutedRef.current;
    fadeFactorRef.current = 0;
    applyEffectiveVolume();
    try {
      await audio.play();
      // クリーンアップ後に解決した遅延 Promise なら巻き戻す
      if (audioRef.current !== audio) {
        audio.pause();
        return;
      }
      phaseRef.current = "playing";
      setAutoplayBlocked(false);
      clearRetryListeners();
      startFade(1, BGM_FADE_IN_MS);
    } catch (error) {
      // クリーンアップの pause による AbortError 等、破棄済み要素の reject は無視
      if (audioRef.current !== audio) return;
      // autoplay 制限等。Adventure 本体は失敗させず、次のユーザー操作で再試行する
      console.warn("Adventure BGM の再生がブロックされました", error);
      phaseRef.current = "blocked";
      setAutoplayBlocked(true);
      if (!retryHandlerRef.current) {
        const handler = () => {
          clearRetryListeners();
          if (phaseRef.current !== "blocked") return;
          const next = targetKeyRef.current;
          if (!next) {
            phaseRef.current = "idle";
            return;
          }
          if (next !== currentKeyRef.current) {
            const url = resolveBgmUrl(next);
            if (!url) {
              phaseRef.current = "idle";
              return;
            }
            currentKeyRef.current = next;
            fallbackTriedRef.current = false;
            ensureAudio().src = url;
          }
          void tryPlay();
        };
        retryHandlerRef.current = handler;
        document.addEventListener("pointerdown", handler);
        document.addEventListener("keydown", handler);
      }
    }
  }, [
    applyEffectiveVolume,
    clearRetryListeners,
    ensureAudio,
    resolveBgmUrl,
    startFade,
  ]);
  tryPlayRef.current = tryPlay;

  /** fade out 完了時（または停止状態から）targetKey を1回だけ反映する */
  const swapToTarget = useCallback(() => {
    const audio = ensureAudio();
    const next = targetKeyRef.current;
    if (!next) {
      audio.pause();
      phaseRef.current = "idle";
      return;
    }
    if (next === currentKeyRef.current && audio.src) {
      // fade 中に元のキーへ戻ったケース。src と currentTime には触れず戻す
      phaseRef.current = "playing";
      startFade(1, BGM_FADE_IN_MS);
      return;
    }
    audio.pause();
    const url = resolveBgmUrl(next);
    if (!url) {
      // カタログ未ロードまたは空。ロード完了時の effect 再評価で立ち上がる
      phaseRef.current = "idle";
      return;
    }
    currentKeyRef.current = next;
    fallbackTriedRef.current = false;
    audio.src = url;
    void tryPlay();
  }, [ensureAudio, resolveBgmUrl, startFade, tryPlay]);

  // キー変更の反映。同一キーは厳密に no-op で、要素の再生成・currentTime
  // リセット・fade を一切行わない。
  useEffect(() => {
    const next = bgmKey ?? null;
    targetKeyRef.current = next;
    // カタログ未ロード中は目標キーの記録だけ行い、ロード完了時の
    // 再評価(catalogLoaded 変化)で再生を立ち上げる
    if (!catalogLoaded) return;
    const phase = phaseRef.current;
    if (phase === "fading_out") {
      // 進行中の fade の完了時に targetKeyRef が読まれるため何もしない
      return;
    }
    if (next === null) {
      if (phase === "playing") {
        phaseRef.current = "fading_out";
        startFade(0, BGM_FADE_OUT_MS, swapToTarget);
      } else if (phase === "blocked") {
        clearRetryListeners();
        phaseRef.current = "idle";
      }
      return;
    }
    if (phase === "playing") {
      if (next === currentKeyRef.current) return;
      phaseRef.current = "fading_out";
      startFade(0, BGM_FADE_OUT_MS, swapToTarget);
      return;
    }
    if (phase === "idle") {
      swapToTarget();
    }
    // blocked: targetKeyRef の更新だけで十分。ユーザー操作時の再試行が拾う
  }, [bgmKey, catalogLoaded, clearRetryListeners, startFade, swapToTarget]);

  // アンマウント時（/adventure 離脱時）は完全に停止する。破棄の印は
  // audioRef を null にすることで表し、hook 全体の旗は持たない
  // (StrictMode の再マウントで旗が立ったまま残り、再生不能になるため)
  useEffect(() => {
    return () => {
      stopFade();
      clearRetryListeners();
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      audioRef.current = null;
      phaseRef.current = "idle";
      currentKeyRef.current = null;
    };
  }, [clearRetryListeners, stopFade]);

  const setMuted = useCallback(
    (next: boolean) => {
      mutedRef.current = next;
      const audio = audioRef.current;
      if (audio) {
        audio.muted = next;
      }
      setPrefs((prev) => {
        const merged = { ...prev, muted: next };
        saveBgmPreferences(merged);
        return merged;
      });
      // ミュート解除はユーザー操作なので、ブロックされていた再生を再試行できる。
      // 何らかの理由で idle に落ちていても、目標キーが残っていれば立ち上げ直す
      if (!next) {
        if (phaseRef.current === "blocked") {
          const nextKey = targetKeyRef.current;
          if (nextKey && nextKey !== currentKeyRef.current) {
            const url = resolveBgmUrl(nextKey);
            if (!url) {
              phaseRef.current = "idle";
              return;
            }
            currentKeyRef.current = nextKey;
            fallbackTriedRef.current = false;
            ensureAudio().src = url;
          }
          void tryPlay();
        } else if (phaseRef.current === "idle" && targetKeyRef.current) {
          swapToTarget();
        }
      }
    },
    [ensureAudio, resolveBgmUrl, swapToTarget, tryPlay],
  );

  const setVolume = useCallback(
    (next: number) => {
      const clamped = clamp01(next);
      volumeRef.current = clamped;
      applyEffectiveVolume();
      setPrefs((prev) => {
        const merged = { ...prev, volume: clamped };
        saveBgmPreferences(merged);
        return merged;
      });
    },
    [applyEffectiveVolume],
  );

  return {
    muted: prefs.muted,
    volume: prefs.volume,
    autoplayBlocked,
    setMuted,
    setVolume,
  };
}
