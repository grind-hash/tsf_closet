/**
 * 音声再生のレベル計測。
 *
 * Web Audio の AnalyserNode で HTMLAudioElement の出力波形を読み取り、
 * 0..1 のレベルへ正規化する。アバターの口パク駆動に使う純粋関数と、
 * それを束ねる小さなメーターを提供する。React には依存しない。
 *
 * 設計上の注意:
 * - createMediaElementSource は要素ごとに 1 回しか呼べず、呼んだ要素の音は
 *   以後その AudioContext からしか出ない。そのためモジュール単位で 1 つの
 *   AudioContext と要素→ノードの対応表を共有し、メーターを作り直しても
 *   同じ要素を再接続しない(再接続は例外になり、要素が無音化する)。
 * - AudioContext が running でないときに要素を接続すると無音化するため、
 *   ユーザー操作(pointerdown / keydown)で resume してから接続する。
 */

/** 時間領域サンプルの RMS。空配列は 0 */
export function rmsFromTimeDomain(samples: Float32Array): number {
  const count = samples.length;
  if (count === 0) return 0;
  let sum = 0;
  for (let i = 0; i < count; i++) {
    const v = samples[i];
    sum += v * v;
  }
  return Math.sqrt(sum / count);
}

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

/**
 * RMS を再生音量で補正し、無音しきい値を差し引いて 0..1 に正規化する。
 * 音量が小さいほど RMS も小さくなるため、音量で割って口の開きを揃える。
 */
export function normalizeVoiceLevel(rms: number, volume: number): number {
  const scaled = rms / Math.max(volume, 0.05);
  return clamp01((scaled - 0.02) / 0.25);
}

/**
 * 指数的に目標へ近づける平滑化。上昇時は attackSec、下降時は releaseSec を
 * 時定数として k = 1 - exp(-dt / tau) で補間する。
 */
export function smoothLevel(
  prev: number,
  next: number,
  dtSec: number,
  attackSec = 0.04,
  releaseSec = 0.12,
): number {
  if (!(dtSec > 0)) return prev;
  const tau = next > prev ? attackSec : releaseSec;
  if (!(tau > 0)) return next;
  const k = 1 - Math.exp(-dtSec / tau);
  return prev + (next - prev) * k;
}

export interface VoiceLevelMeter {
  /** 計測対象の要素を設定する。同じ要素は 1 回だけ Web Audio に接続される */
  attach(audio: HTMLAudioElement): void;
  /** 現在のレベル(0..1)。未接続・停止中・終了後は 0 */
  getLevel(): number;
  /** リスナーと参照を解放する。共有 AudioContext は閉じない */
  dispose(): void;
}

/** 常に 0 を返す無害なメーター(Web Audio が使えない環境向け) */
export function createSilentVoiceLevelMeter(): VoiceLevelMeter {
  return {
    attach() {},
    getLevel: () => 0,
    dispose() {},
  };
}

type AudioContextCtor = new () => AudioContext;

interface ElementNodes {
  source: MediaElementAudioSourceNode;
  analyser: AnalyserNode;
}

const ANALYSER_FFT_SIZE = 1024;
const ANALYSER_SMOOTHING = 0.3;
const UNLOCK_EVENTS = ["pointerdown", "keydown"] as const;

// 要素→ノードの対応表と AudioContext はページ内で共有する(冒頭の注意を参照)
const elementNodes = new WeakMap<HTMLAudioElement, ElementNodes>();
const failedElements = new WeakSet<HTMLAudioElement>();
let sharedContext: AudioContext | null = null;

function resolveAudioContextCtor(): AudioContextCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    AudioContext?: AudioContextCtor;
    webkitAudioContext?: AudioContextCtor;
  };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

function getSharedContext(Ctor: AudioContextCtor): AudioContext | null {
  if (sharedContext && sharedContext.state !== "closed") return sharedContext;
  try {
    sharedContext = new Ctor();
  } catch {
    sharedContext = null;
  }
  return sharedContext;
}

function connectElement(
  ctx: AudioContext,
  audio: HTMLAudioElement,
): ElementNodes | null {
  const existing = elementNodes.get(audio);
  if (existing) return existing;
  if (failedElements.has(audio)) return null;
  try {
    const source = ctx.createMediaElementSource(audio);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = ANALYSER_FFT_SIZE;
    analyser.smoothingTimeConstant = ANALYSER_SMOOTHING;
    source.connect(analyser);
    analyser.connect(ctx.destination);
    const nodes: ElementNodes = { source, analyser };
    elementNodes.set(audio, nodes);
    return nodes;
  } catch {
    // 別の AudioContext に接続済みなどの場合。以後は再試行しない
    failedElements.add(audio);
    return null;
  }
}

export function createVoiceLevelMeter(): VoiceLevelMeter {
  const Ctor = resolveAudioContextCtor();
  if (!Ctor) return createSilentVoiceLevelMeter();

  let current: HTMLAudioElement | null = null;
  let buffer: Float32Array<ArrayBuffer> | null = null;
  let disposed = false;
  let unlockHandler: (() => void) | null = null;

  const removeUnlockListeners = () => {
    if (!unlockHandler) return;
    for (const type of UNLOCK_EVENTS) {
      window.removeEventListener(type, unlockHandler);
    }
    unlockHandler = null;
  };

  const tryConnect = (ctx: AudioContext, audio: HTMLAudioElement) => {
    if (ctx.state === "running") {
      connectElement(ctx, audio);
      return;
    }
    // 停止中のコンテキストに接続すると要素が無音化するため、ユーザー操作を
    // 待って resume してから接続する
    if (unlockHandler) return;
    const handler = () => {
      removeUnlockListeners();
      if (disposed) return;
      ctx
        .resume()
        .then(() => {
          if (disposed || !current) return;
          connectElement(ctx, current);
        })
        .catch(() => {
          // resume に失敗した場合は次の attach で再試行する
        });
    };
    unlockHandler = handler;
    for (const type of UNLOCK_EVENTS) {
      window.addEventListener(type, handler, { once: true });
    }
  };

  return {
    attach(audio) {
      if (disposed) return;
      current = audio;
      if (elementNodes.has(audio)) return;
      const ctx = getSharedContext(Ctor);
      if (!ctx) return;
      tryConnect(ctx, audio);
    },
    getLevel() {
      if (disposed || !current) return 0;
      const nodes = elementNodes.get(current);
      if (!nodes) return 0;
      if (current.paused || current.ended) return 0;
      if (sharedContext && sharedContext.state !== "running") return 0;
      const size = nodes.analyser.fftSize;
      if (!buffer || buffer.length !== size) {
        buffer = new Float32Array(size);
      }
      nodes.analyser.getFloatTimeDomainData(buffer);
      return normalizeVoiceLevel(rmsFromTimeDomain(buffer), current.volume);
    },
    dispose() {
      disposed = true;
      removeUnlockListeners();
      current = null;
      buffer = null;
    },
  };
}
