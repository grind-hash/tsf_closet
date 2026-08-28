/**
 * VRM アバターの手続き的モーション(純粋関数)。
 *
 * three.js に依存せず、姿勢オフセット・口形状・まばたきの重みだけを計算する。
 * 実際のボーン回転や表情適用は描画側(three-vrm を使う層)が担当する。
 * 角度はラジアン、位置はメートル。
 */

import type { AvatarGestureKey } from "../../../constants/companionAvatar";

export interface PoseOffsets {
  /** 頭の前後の傾き。正で前(うなずき方向) */
  headPitch: number;
  /** 頭の左右の向き。正で左向き */
  headYaw: number;
  /** 頭の左右の傾げ。正で左肩側へ */
  headRoll: number;
  /** 上体の前後の傾き。正で前傾 */
  spinePitch: number;
  /** 腰の上下オフセット(メートル)。正で上 */
  hipsY: number;
}

export const POSE_KEYS: readonly (keyof PoseOffsets)[] = [
  "headPitch",
  "headYaw",
  "headRoll",
  "spinePitch",
  "hipsY",
];

export const ZERO_POSE: PoseOffsets = Object.freeze({
  headPitch: 0,
  headYaw: 0,
  headRoll: 0,
  spinePitch: 0,
  hipsY: 0,
});

/** キーフレーム。t は 0..1 の正規化時刻、v は値 */
export type Keyframe = [t: number, v: number];

export interface GestureClip {
  /** 再生時間(秒) */
  duration: number;
  /** true のとき再生中は視線追従(lookAt)を解除する */
  releaseLookAt?: boolean;
  /** チャンネルごとのカーブ。各カーブは 0 で始まり 0 で終わる */
  keys: Partial<Record<keyof PoseOffsets, Keyframe[]>>;
}

export const GESTURE_CLIPS: Record<
  Exclude<AvatarGestureKey, "idle">,
  GestureClip
> = {
  nod: {
    duration: 0.9,
    keys: {
      headPitch: [
        [0, 0],
        [0.3, 0.35],
        [0.55, -0.05],
        [0.75, 0.2],
        [1, 0],
      ],
    },
  },
  shake_head: {
    duration: 1.2,
    keys: {
      headYaw: [
        [0, 0],
        [0.2, 0.3],
        [0.5, -0.3],
        [0.75, 0.2],
        [1, 0],
      ],
    },
  },
  tilt_head: {
    duration: 1.4,
    keys: {
      headRoll: [
        [0, 0],
        [0.35, 0.22],
        [0.75, 0.22],
        [1, 0],
      ],
    },
  },
  lean_forward: {
    duration: 1.5,
    keys: {
      spinePitch: [
        [0, 0],
        [0.4, 0.16],
        [0.8, 0.16],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.4, -0.06],
        [0.8, -0.06],
        [1, 0],
      ],
    },
  },
  lean_back: {
    duration: 1.5,
    keys: {
      spinePitch: [
        [0, 0],
        [0.4, -0.12],
        [0.8, -0.12],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.4, 0.04],
        [0.8, 0.04],
        [1, 0],
      ],
    },
  },
  look_away: {
    duration: 1.8,
    releaseLookAt: true,
    keys: {
      headYaw: [
        [0, 0],
        [0.3, 0.45],
        [0.75, 0.45],
        [1, 0],
      ],
    },
  },
  bounce: {
    duration: 0.8,
    keys: {
      hipsY: [
        [0, 0],
        [0.25, 0.03],
        [0.5, -0.005],
        [0.7, 0.015],
        [1, 0],
      ],
    },
  },
};

const TWO_PI = Math.PI * 2;

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function smoothstep(x: number): number {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
}

/** キーフレーム列を smoothstep 補間でサンプリングする */
function sampleCurve(keys: Keyframe[], t: number): number {
  if (keys.length === 0) return 0;
  const first = keys[0];
  if (t <= first[0]) return first[1];
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1] = keys[i];
    if (t <= t1) {
      const [t0, v0] = keys[i - 1];
      const span = t1 - t0;
      const u = span > 0 ? smoothstep((t - t0) / span) : 1;
      return v0 + (v1 - v0) * u;
    }
  }
  return keys[keys.length - 1][1];
}

/** 身振りの再生時間(秒)。idle は 0 */
export function gestureDuration(key: AvatarGestureKey): number {
  if (key === "idle") return 0;
  return GESTURE_CLIPS[key].duration;
}

/**
 * 身振りを進行度(0..1)でサンプリングする。範囲外はクランプ、idle は ZERO_POSE。
 * 常に新しいオブジェクトを返す。
 */
export function sampleGesture(
  key: AvatarGestureKey,
  progress: number,
): PoseOffsets {
  const pose: PoseOffsets = { ...ZERO_POSE };
  if (key === "idle") return pose;
  const clip = GESTURE_CLIPS[key];
  const t = clamp01(progress);
  for (const channel of POSE_KEYS) {
    const keys = clip.keys[channel];
    if (keys) pose[channel] = sampleCurve(keys, t);
  }
  return pose;
}

/** 呼吸(3.5 秒周期)と緩やかな揺れ(7 秒・11 秒周期)を合成した待機姿勢 */
export function idlePose(timeSec: number): PoseOffsets {
  const breath = Math.sin((TWO_PI * timeSec) / 3.5);
  return {
    headPitch: 0,
    headYaw: 0.03 * Math.sin((TWO_PI * timeSec) / 7),
    headRoll: 0.015 * Math.sin((TWO_PI * timeSec) / 11),
    spinePitch: 0.015 * breath,
    hipsY: 0.004 * breath,
  };
}

export function addPose(a: PoseOffsets, b: PoseOffsets): PoseOffsets {
  return {
    headPitch: a.headPitch + b.headPitch,
    headYaw: a.headYaw + b.headYaw,
    headRoll: a.headRoll + b.headRoll,
    spinePitch: a.spinePitch + b.spinePitch,
    hipsY: a.hipsY + b.hipsY,
  };
}

/** VRM の口形状プリセット(aa / ih / ou)の重み。各 0..1 */
export interface MouthWeights {
  aa: number;
  ih: number;
  ou: number;
}

/**
 * 音声レベル(0..1)から口形状の重みを作る。
 * aa が主成分で、ih / ou は 5.3Hz の揺らぎで交互に混ざる。
 */
export function mouthWeightsFromLevel(
  level: number,
  timeSec: number,
): MouthWeights {
  const l = clamp01(level);
  const n = 0.5 + 0.5 * Math.sin(TWO_PI * 5.3 * timeSec);
  return {
    aa: clamp01(l ** 0.8 * 0.9),
    ih: clamp01(0.25 * l * n),
    ou: clamp01(0.2 * l * (1 - n)),
  };
}

/** 次のまばたきまでの間隔(秒)。2.5..6.0 の一様分布 */
export function nextBlinkDelay(random: () => number): number {
  return 2.5 + random() * 3.5;
}

/** 目を閉じるのにかかる時間(秒) */
export const BLINK_CLOSE_SEC = 0.06;
/** 目を開くのにかかる時間(秒) */
export const BLINK_OPEN_SEC = 0.1;
/** まばたき 1 回の合計時間(秒) */
export const BLINK_TOTAL_SEC = BLINK_CLOSE_SEC + BLINK_OPEN_SEC;

/**
 * まばたき開始からの経過秒に対する blink 表情の重み(0..1)。
 * 0 → 1 に BLINK_CLOSE_SEC、1 → 0 に BLINK_OPEN_SEC かけて戻り、以降は 0。
 * 終了判定は isBlinkDone で行い、呼び出し側が次のまばたきを予約する。
 */
export function blinkWeight(elapsedSec: number): number {
  if (!(elapsedSec > 0)) return 0;
  if (elapsedSec < BLINK_CLOSE_SEC) return elapsedSec / BLINK_CLOSE_SEC;
  if (elapsedSec < BLINK_TOTAL_SEC) {
    return 1 - (elapsedSec - BLINK_CLOSE_SEC) / BLINK_OPEN_SEC;
  }
  return 0;
}

/** まばたきが完了したか(経過秒が合計時間に達したか) */
export function isBlinkDone(elapsedSec: number): boolean {
  return elapsedSec >= BLINK_TOTAL_SEC;
}
