/**
 * VRM アバターの手続き的モーション(純粋関数)。
 *
 * three.js に依存せず、姿勢オフセット・待機姿勢の関節角・口形状・まばたきの
 * 重みだけを計算する。実際のボーン回転や表情適用は描画側(three-vrm を使う層)が
 * 担当する。角度はラジアン、位置はメートル。
 */

import type { AvatarGestureKey } from "../../../constants/companionAvatar";

/**
 * モデル基準の姿勢オフセット。「前」「左」はモデル自身から見た向きで、
 * ボーンの局所回転へは poseToBoneRotation で前方の符号を掛けて変換する
 */
export interface PoseOffsets {
  /** 頭の前後の傾き。正で前(うなずき方向) */
  headPitch: number;
  /** 頭の左右の向き。正で左向き */
  headYaw: number;
  /** 頭の左右の傾げ。正で左肩側へ */
  headRoll: number;
  /** 上体の前後の傾き。正で前傾 */
  spinePitch: number;
  /** 上体の左右のひねり。正で左向き */
  spineYaw: number;
  /** 上体の左右の傾げ。正で左肩側へ */
  spineRoll: number;
  /** 腰の上下オフセット(メートル)。正で上 */
  hipsY: number;
  /** 腰の左右オフセット(メートル)。正でモデルの左へ */
  hipsX: number;
  /** 両腕を体側から持ち上げる角度。正で腕が体から離れる(待機姿勢に加算) */
  armLift: number;
  /** 左腕だけを持ち上げる角度(armLift に加算) */
  armLiftL: number;
  /** 右腕だけを持ち上げる角度(armLift に加算) */
  armLiftR: number;
  /** 左腕を前方へ振る追加角。正で前へ */
  armForwardL: number;
  /** 右腕を前方へ振る追加角。正で前へ */
  armForwardR: number;
  /** 左肘の前方曲げの追加角。負で待機姿勢より伸ばす(0 未満には曲がらない) */
  elbowL: number;
  /** 右肘の前方曲げの追加角。負で待機姿勢より伸ばす(0 未満には曲がらない) */
  elbowR: number;
  /** 左前腕を前額面で上へ振り上げる角度(手を振る・挙手用)。0 以上 */
  elbowUpL: number;
  /** 右前腕を前額面で上へ振り上げる角度(手を振る・挙手用)。0 以上 */
  elbowUpR: number;
  /** 左前腕のひねり。正で手のひらがモデルの前方(視聴者側)を向く。0 以上 */
  palmTurnL: number;
  /** 右前腕のひねり。正で手のひらがモデルの前方(視聴者側)を向く。0 以上 */
  palmTurnR: number;
}

export const POSE_KEYS: readonly (keyof PoseOffsets)[] = [
  "headPitch",
  "headYaw",
  "headRoll",
  "spinePitch",
  "spineYaw",
  "spineRoll",
  "hipsY",
  "hipsX",
  "armLift",
  "armLiftL",
  "armLiftR",
  "armForwardL",
  "armForwardR",
  "elbowL",
  "elbowR",
  "elbowUpL",
  "elbowUpR",
  "palmTurnL",
  "palmTurnR",
];

export const ZERO_POSE: PoseOffsets = Object.freeze({
  headPitch: 0,
  headYaw: 0,
  headRoll: 0,
  spinePitch: 0,
  spineYaw: 0,
  spineRoll: 0,
  hipsY: 0,
  hipsX: 0,
  armLift: 0,
  armLiftL: 0,
  armLiftR: 0,
  armForwardL: 0,
  armForwardR: 0,
  elbowL: 0,
  elbowR: 0,
  elbowUpL: 0,
  elbowUpR: 0,
  palmTurnL: 0,
  palmTurnR: 0,
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
      spineYaw: [
        [0, 0],
        [0.3, 0.12],
        [0.75, 0.12],
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
  bow: {
    duration: 1.8,
    releaseLookAt: true,
    keys: {
      spinePitch: [
        [0, 0],
        [0.3, 0.32],
        [0.65, 0.32],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.3, 0.22],
        [0.65, 0.22],
        [1, 0],
      ],
    },
  },
  look_down: {
    duration: 1.6,
    releaseLookAt: true,
    keys: {
      headPitch: [
        [0, 0],
        [0.3, 0.3],
        [0.75, 0.3],
        [1, 0],
      ],
      spinePitch: [
        [0, 0],
        [0.3, 0.05],
        [0.75, 0.05],
        [1, 0],
      ],
    },
  },
  perk_up: {
    duration: 1.1,
    keys: {
      spinePitch: [
        [0, 0],
        [0.25, -0.1],
        [0.7, -0.08],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.25, -0.08],
        [0.7, -0.06],
        [1, 0],
      ],
      hipsY: [
        [0, 0],
        [0.25, 0.012],
        [0.7, 0.008],
        [1, 0],
      ],
    },
  },
  shrink: {
    duration: 1.8,
    keys: {
      hipsY: [
        [0, 0],
        [0.35, -0.03],
        [0.75, -0.03],
        [1, 0],
      ],
      spinePitch: [
        [0, 0],
        [0.35, 0.14],
        [0.75, 0.14],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.35, 0.18],
        [0.75, 0.18],
        [1, 0],
      ],
      armLift: [
        [0, 0],
        [0.35, -0.03],
        [0.75, -0.03],
        [1, 0],
      ],
    },
  },
  sway: {
    duration: 2.4,
    keys: {
      spineRoll: [
        [0, 0],
        [0.2, 0.1],
        [0.5, -0.1],
        [0.8, 0.1],
        [1, 0],
      ],
      hipsX: [
        [0, 0],
        [0.2, 0.02],
        [0.5, -0.02],
        [0.8, 0.02],
        [1, 0],
      ],
      headRoll: [
        [0, 0],
        [0.2, -0.05],
        [0.5, 0.05],
        [0.8, -0.05],
        [1, 0],
      ],
    },
  },
  double_bounce: {
    duration: 1.3,
    keys: {
      hipsY: [
        [0, 0],
        [0.18, 0.03],
        [0.34, -0.004],
        [0.5, 0.028],
        [0.66, -0.003],
        [0.82, 0.012],
        [1, 0],
      ],
      armLift: [
        [0, 0],
        [0.18, 0.12],
        [0.5, 0.1],
        [0.82, 0.04],
        [1, 0],
      ],
    },
  },
  wave_hand: {
    duration: 2.2,
    keys: {
      armLiftR: [
        [0, 0],
        [0.14, 0.95],
        [0.82, 0.95],
        [1, 0],
      ],
      armForwardR: [
        [0, 0],
        [0.14, 0.15],
        [0.82, 0.15],
        [1, 0],
      ],
      elbowUpR: [
        [0, 0],
        [0.14, 1.5],
        [0.3, 1.1],
        [0.46, 1.7],
        [0.62, 1.1],
        [0.82, 1.5],
        [1, 0],
      ],
      palmTurnR: [
        [0, 0],
        [0.14, 1.4],
        [0.82, 1.4],
        [1, 0],
      ],
      headRoll: [
        [0, 0],
        [0.2, 0.06],
        [0.8, 0.06],
        [1, 0],
      ],
    },
  },
  raise_hand: {
    duration: 1.6,
    keys: {
      armLiftR: [
        [0, 0],
        [0.25, 1.75],
        [0.7, 1.7],
        [1, 0],
      ],
      elbowUpR: [
        [0, 0],
        [0.25, 0.35],
        [0.7, 0.3],
        [1, 0],
      ],
      palmTurnR: [
        [0, 0],
        [0.25, 1.1],
        [0.7, 1.05],
        [1, 0],
      ],
      elbowR: [
        [0, 0],
        [0.25, -0.2],
        [0.7, -0.2],
        [1, 0],
      ],
      spinePitch: [
        [0, 0],
        [0.25, -0.05],
        [0.7, -0.05],
        [1, 0],
      ],
    },
  },
  reach_out: {
    duration: 2,
    keys: {
      armForwardR: [
        [0, 0],
        [0.35, 1.3],
        [0.7, 1.3],
        [1, 0],
      ],
      armLiftR: [
        [0, 0],
        [0.35, 0.15],
        [0.7, 0.15],
        [1, 0],
      ],
      elbowR: [
        [0, 0],
        [0.35, -0.25],
        [0.7, -0.25],
        [1, 0],
      ],
      spinePitch: [
        [0, 0],
        [0.35, 0.08],
        [0.7, 0.08],
        [1, 0],
      ],
    },
  },
  cheer: {
    duration: 1.7,
    keys: {
      armLiftL: [
        [0, 0],
        [0.22, 1.7],
        [0.7, 1.6],
        [1, 0],
      ],
      armLiftR: [
        [0, 0],
        [0.22, 1.8],
        [0.7, 1.7],
        [1, 0],
      ],
      elbowUpL: [
        [0, 0],
        [0.22, 0.3],
        [0.7, 0.25],
        [1, 0],
      ],
      elbowUpR: [
        [0, 0],
        [0.22, 0.25],
        [0.7, 0.2],
        [1, 0],
      ],
      palmTurnL: [
        [0, 0],
        [0.22, 0.7],
        [0.7, 0.65],
        [1, 0],
      ],
      palmTurnR: [
        [0, 0],
        [0.22, 0.75],
        [0.7, 0.7],
        [1, 0],
      ],
      hipsY: [
        [0, 0],
        [0.15, 0.025],
        [0.35, -0.003],
        [0.55, 0.015],
        [1, 0],
      ],
      headPitch: [
        [0, 0],
        [0.22, -0.08],
        [0.7, -0.06],
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

/**
 * 呼吸(3.5 秒周期)と緩やかな揺れ(7 秒・9 秒・11 秒周期)を合成した待機姿勢。
 * 腕は吸気で体からわずかに離れ、別周期の揺れも重ねて静止して見えないようにする
 */
export function idlePose(timeSec: number): PoseOffsets {
  const breath = Math.sin((TWO_PI * timeSec) / 3.5);
  return {
    ...ZERO_POSE,
    headYaw: 0.03 * Math.sin((TWO_PI * timeSec) / 7),
    headRoll: 0.015 * Math.sin((TWO_PI * timeSec) / 11),
    spinePitch: 0.015 * breath,
    hipsY: 0.004 * breath,
    armLift: 0.012 * breath + 0.006 * Math.sin((TWO_PI * timeSec) / 9),
  };
}

export function addPose(a: PoseOffsets, b: PoseOffsets): PoseOffsets {
  const sum: PoseOffsets = { ...a };
  for (const key of POSE_KEYS) sum[key] = a[key] + b[key];
  return sum;
}

/* ------------------------------------------------------------------------ */
/* 前方の判定と、姿勢オフセットからボーン回転への変換                          */
/* ------------------------------------------------------------------------ */

/** normalized bone の局所系でモデルが向いている Z の符号。VRM 1.0 は +1、0.x は -1 */
export type Facing = 1 | -1;

/**
 * 左腕の向きから前方の Z 符号を求める。
 * Y 上・右手系では 左 = 上 × 前 なので、左腕の X の符号がそのまま前の Z の符号になる。
 * 腕の向きが取れないときは仕様版から推定する(1.0 は +Z 向き、0.x は -Z 向き)
 */
export function detectFacing(
  leftArmDir: Vec3 | null,
  specVersion: "0" | "1",
): Facing {
  if (leftArmDir && Math.abs(leftArmDir[0]) > 1e-3) {
    return leftArmDir[0] > 0 ? 1 : -1;
  }
  return specVersion === "0" ? -1 : 1;
}

export interface BoneRotations {
  /** 頭の Euler 角(XYZ 順、ラジアン) */
  head: Vec3;
  /** 背骨の Euler 角(XYZ 順、ラジアン) */
  spine: Vec3;
}

/**
 * モデル基準の姿勢オフセットを normalized bone の局所回転へ変換する。
 * normalized bone の局所系は読込時のシーン系と一致し、0.x モデルは -Z 向きのまま
 * (表示ではシーンごと 180° 回して +Z 向きに揃えている)。そのため X 軸回り(前後の傾き)
 * と Z 軸回り(左右の傾げ)は前方の符号で反転し、Y 軸回り(左右の向き)は不変。
 * +Z 向きでは X 正回転で頭頂が +Z(前)へ、Z 正回転で頭頂が -X(右肩側)へ動く
 */
export function poseToBoneRotation(
  pose: PoseOffsets,
  facing: Facing,
): BoneRotations {
  return {
    head: [facing * pose.headPitch, pose.headYaw, -facing * pose.headRoll],
    spine: [facing * pose.spinePitch, pose.spineYaw, -facing * pose.spineRoll],
  };
}

/* ------------------------------------------------------------------------ */
/* 待機姿勢(腕・肘・指)                                                     */
/* ------------------------------------------------------------------------ */

export type Vec3 = readonly [number, number, number];

/** 回転軸(単位ベクトル)と角度(ラジアン) */
export interface AxisAngle {
  axis: Vec3;
  angle: number;
}

/**
 * VRM の rest ポーズ(T ポーズ、手のひらは下向き)における「下」。
 * three-vrm の normalized bone はどの関節でも rest の局所系がワールド系と一致する
 * ため、この向きは腕・指どのボーンの局所系でも同じ意味を持つ
 */
export const DOWN: Vec3 = [0, -1, 0];

/** rest ポーズにおける「上」。DOWN と同様、どのボーンの局所系でも同じ意味を持つ */
export const UP: Vec3 = [0, 1, 0];

export function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/** 単位ベクトル化。長さがほぼ 0 なら null */
export function normalize(v: Vec3): Vec3 | null {
  const length = Math.hypot(v[0], v[1], v[2]);
  if (!(length > 1e-6)) return null;
  return [v[0] / length, v[1] / length, v[2] / length];
}

/**
 * ボーンの向き from を toward の側へ angle だけ傾ける回転を返す。
 * 軸は from × toward なので、モデルが +X / -X どちらに腕を伸ばしていても
 * (VRM 1.0 は +Z 向き、0.x は -Z 向き)符号を意識せずに同じ意図の回転が得られる。
 * from と toward が平行なら null
 */
export function tiltTowards(
  from: Vec3,
  toward: Vec3,
  angle: number,
): AxisAngle | null {
  const axis = axisBetween(from, toward);
  if (!axis) return null;
  return { axis, angle };
}

/** from を toward の側へ倒す回転軸(from × toward の単位ベクトル)。平行なら null */
export function axisBetween(from: Vec3, toward: Vec3): Vec3 | null {
  return normalize(cross(from, toward));
}

export type ArmSide = "left" | "right";

export interface ArmRestAngles {
  /** T ポーズから腕を体側へ下ろす角度。π/2 で真下 */
  lower: number;
  /** 下ろした腕を前方へ振る角度 */
  forward: number;
  /** 肘を前方へ曲げる角度 */
  bend: number;
}

/**
 * 待機姿勢の腕の角度。左右をわずかに変え、鏡写しの硬さを避ける。
 * lower は肩幅の広い衣装でも体にめり込まず、かつ A ポーズに見えない範囲に置く
 */
export const ARM_REST: Record<ArmSide, ArmRestAngles> = {
  left: { lower: 1.3, forward: 0.07, bend: 0.28 },
  right: { lower: 1.3, forward: 0.09, bend: 0.34 },
};

/** 片腕ぶんの姿勢チャンネル。PoseOffsets から左右いずれかを取り出したもの */
export interface ArmChannels {
  /** 体側から持ち上げる角度(armLift + 片腕ぶん) */
  lift: number;
  /** 前方へ振る追加角 */
  forward: number;
  /** 肘の前方曲げの追加角 */
  elbow: number;
  /** 前腕を前額面で上へ振り上げる角度 */
  elbowUp: number;
  /** 前腕のひねり。正で手のひらが前方を向く */
  palmTurn: number;
}

/** 姿勢オフセットから片腕ぶんのチャンネルを取り出す */
export function armChannels(pose: PoseOffsets, side: ArmSide): ArmChannels {
  if (side === "left") {
    return {
      lift: pose.armLift + pose.armLiftL,
      forward: pose.armForwardL,
      elbow: pose.elbowL,
      elbowUp: pose.elbowUpL,
      palmTurn: pose.palmTurnL,
    };
  }
  return {
    lift: pose.armLift + pose.armLiftR,
    forward: pose.armForwardR,
    elbow: pose.elbowR,
    elbowUp: pose.elbowUpR,
    palmTurn: pose.palmTurnR,
  };
}

export const FINGER_NAMES = [
  "thumb",
  "index",
  "middle",
  "ring",
  "little",
] as const;
export type FingerName = (typeof FINGER_NAMES)[number];
export type FingerSegment =
  | "metacarpal"
  | "proximal"
  | "intermediate"
  | "distal";

/** 指ごとの関節列(根元から先端へ)。VRM 1.0 の命名で、0.x は three-vrm が読み替える */
export const FINGER_SEGMENTS: Record<FingerName, readonly FingerSegment[]> = {
  thumb: ["metacarpal", "proximal", "distal"],
  index: ["proximal", "intermediate", "distal"],
  middle: ["proximal", "intermediate", "distal"],
  ring: ["proximal", "intermediate", "distal"],
  little: ["proximal", "intermediate", "distal"],
};

/**
 * 力を抜いた手の指の曲げ角(FINGER_SEGMENTS と同じ順)。
 * 人差し指が最も浅く小指へ向かって深くなる。親指の付け根(中手骨)は動かさない
 */
export const FINGER_CURL: Record<FingerName, readonly number[]> = {
  thumb: [0, 0.15, 0.2],
  index: [0.3, 0.35, 0.2],
  middle: [0.38, 0.42, 0.25],
  ring: [0.45, 0.48, 0.28],
  little: [0.5, 0.52, 0.3],
};

/** three-vrm の humanoid ボーン名(例: leftIndexProximal)を組み立てる */
export function fingerBoneName(
  side: ArmSide,
  finger: FingerName,
  segment: FingerSegment,
): string {
  const capitalize = (word: string): string =>
    word.charAt(0).toUpperCase() + word.slice(1);
  return `${side}${capitalize(finger)}${capitalize(segment)}`;
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

/** viseme 口パク用の口形状ターゲット(aa/ih/ou/ee/oh)。各 0..1 */
export interface MouthTargets {
  aa: number;
  ih: number;
  ou: number;
  ee: number;
  oh: number;
}

export const CLOSED_MOUTH_TARGETS: MouthTargets = {
  aa: 0,
  ih: 0,
  ou: 0,
  ee: 0,
  oh: 0,
};

/**
 * viseme とその重みから口形状ターゲットを作る。
 * モデルに ee / oh のプリセットが無い場合は近い口形(ee→ih、oh→ou)へ
 * 振り替える。viseme が null(閉口区間)なら全チャンネル 0
 */
export function mouthWeightsFromViseme(
  viseme: string | null,
  w: number,
  hasEe: boolean,
  hasOh: boolean,
): MouthTargets {
  const targets: MouthTargets = { ...CLOSED_MOUTH_TARGETS };
  if (!viseme) return targets;
  const resolved =
    viseme === "ee" && !hasEe
      ? "ih"
      : viseme === "oh" && !hasOh
        ? "ou"
        : viseme;
  if (resolved in targets) {
    targets[resolved as keyof MouthTargets] = clamp01(w);
  }
  return targets;
}

/** 口を開く方向の追従時定数(秒) */
export const MOUTH_ATTACK_SEC = 0.03;
/** 口を閉じる方向の追従時定数(秒) */
export const MOUTH_RELEASE_SEC = 0.09;

/**
 * 口形状ターゲットへの指数追従。チャンネルごとに attack/release を使い分け、
 * モーラ境界で口形が瞬時に切り替わるのを和らげる
 */
export function approachMouthTargets(
  current: MouthTargets,
  target: MouthTargets,
  deltaSec: number,
): MouthTargets {
  const dt = Math.max(deltaSec, 0);
  const step = (from: number, to: number): number => {
    const tau = to > from ? MOUTH_ATTACK_SEC : MOUTH_RELEASE_SEC;
    return from + (to - from) * (1 - Math.exp(-dt / tau));
  };
  return {
    aa: step(current.aa, target.aa),
    ih: step(current.ih, target.ih),
    ou: step(current.ou, target.ou),
    ee: step(current.ee, target.ee),
    oh: step(current.oh, target.oh),
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
