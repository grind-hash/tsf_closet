import { Euler, Quaternion, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import {
  AVATAR_GESTURES,
  type AvatarGestureKey,
} from "../../../constants/companionAvatar";
import {
  ARM_REST,
  type ArmSide,
  type AxisAngle,
  addPose,
  approachMouthTargets,
  armChannels,
  axisBetween,
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  BLINK_TOTAL_SEC,
  blinkWeight,
  CLOSED_MOUTH_TARGETS,
  DOWN,
  detectFacing,
  type Facing,
  FINGER_CURL,
  FINGER_NAMES,
  FINGER_SEGMENTS,
  fingerBoneName,
  GESTURE_CLIPS,
  gestureDuration,
  idlePose,
  isBlinkDone,
  mouthWeightsFromLevel,
  mouthWeightsFromViseme,
  nextBlinkDelay,
  POSE_KEYS,
  type PoseOffsets,
  poseToBoneRotation,
  sampleGesture,
  tiltTowards,
  type Vec3,
  ZERO_POSE,
} from "./avatarMotion";

const CLIP_KEYS = Object.keys(GESTURE_CLIPS) as Array<
  Exclude<AvatarGestureKey, "idle">
>;

function expectZeroPose(pose: PoseOffsets): void {
  for (const key of POSE_KEYS) {
    expect(Math.abs(pose[key])).toBeLessThan(1e-9);
  }
}

describe("avatarMotion clips", () => {
  it("covers every non-idle gesture of the vocabulary", () => {
    const expected = AVATAR_GESTURES.filter((key) => key !== "idle");
    expect(new Set(CLIP_KEYS)).toEqual(new Set(expected));
  });

  it("returns ZERO_POSE for idle at any progress", () => {
    expect(gestureDuration("idle")).toBe(0);
    for (const progress of [0, 0.3, 1, 5, -1]) {
      expectZeroPose(sampleGesture("idle", progress));
    }
  });

  it("starts and ends every clip at ZERO_POSE", () => {
    for (const key of CLIP_KEYS) {
      expectZeroPose(sampleGesture(key, 0));
      expectZeroPose(sampleGesture(key, 1));
      // 範囲外はクランプされる
      expectZeroPose(sampleGesture(key, -0.5));
      expectZeroPose(sampleGesture(key, 1.5));
      expect(gestureDuration(key)).toBeGreaterThan(0);
    }
  });

  it("keeps every sample finite and within its channel limit", () => {
    // 回転はラジアン、hips はメートル。腕系は振り上げがあるため上限が大きい
    const limits: Record<keyof PoseOffsets, number> = {
      headPitch: 0.5,
      headYaw: 0.5,
      headRoll: 0.5,
      spinePitch: 0.5,
      spineYaw: 0.5,
      spineRoll: 0.5,
      hipsY: 0.06,
      hipsX: 0.06,
      armLift: 0.3,
      armLiftL: 2,
      armLiftR: 2,
      armForwardL: 1.5,
      armForwardR: 1.5,
      elbowL: 0.6,
      elbowR: 0.6,
      elbowUpL: 2,
      elbowUpR: 2,
      palmTurnL: 2,
      palmTurnR: 2,
    };
    for (const key of CLIP_KEYS) {
      for (let step = 0; step <= 20; step++) {
        const pose = sampleGesture(key, step / 20);
        for (const channel of POSE_KEYS) {
          const value = pose[channel];
          expect(Number.isFinite(value)).toBe(true);
          expect(Math.abs(value)).toBeLessThanOrEqual(limits[channel]);
        }
      }
    }
  });

  it("reaches the keyframe peak in the middle of a nod", () => {
    expect(sampleGesture("nod", 0.3).headPitch).toBeCloseTo(0.35, 9);
    expect(sampleGesture("look_away", 0.5).headYaw).toBeCloseTo(0.45, 9);
    expect(GESTURE_CLIPS.look_away.releaseLookAt).toBe(true);
  });

  it("plays the new clips on their intended channels", () => {
    expect(sampleGesture("bow", 0.45).spinePitch).toBeCloseTo(0.32, 9);
    expect(GESTURE_CLIPS.bow.releaseLookAt).toBe(true);
    expect(GESTURE_CLIPS.look_down.releaseLookAt).toBe(true);
    expect(sampleGesture("wave_hand", 0.46).elbowUpR).toBeCloseTo(1.7, 9);
    expect(sampleGesture("wave_hand", 0.46).armLiftR).toBeCloseTo(0.95, 9);
    expect(sampleGesture("wave_hand", 0.46).palmTurnR).toBeCloseTo(1.4, 9);
    expect(sampleGesture("raise_hand", 0.25).palmTurnR).toBeCloseTo(1.1, 9);
    // 片腕の身振りは左腕を動かさない
    expect(sampleGesture("wave_hand", 0.46).armLiftL).toBe(0);
    expect(sampleGesture("raise_hand", 0.25).armLiftR).toBeCloseTo(1.75, 9);
    expect(sampleGesture("raise_hand", 0.25).elbowR).toBeCloseTo(-0.2, 9);
    expect(sampleGesture("reach_out", 0.5).armForwardR).toBeCloseTo(1.3, 9);
    expect(sampleGesture("cheer", 0.22).armLiftL).toBeCloseTo(1.7, 9);
    expect(sampleGesture("cheer", 0.22).armLiftR).toBeCloseTo(1.8, 9);
    expect(sampleGesture("sway", 0.2).hipsX).toBeCloseTo(0.02, 9);
    expect(sampleGesture("sway", 0.2).spineRoll).toBeCloseTo(0.1, 9);
  });

  it("does not mutate ZERO_POSE through returned poses", () => {
    const pose = sampleGesture("idle", 0);
    pose.headPitch = 1;
    expect(ZERO_POSE.headPitch).toBe(0);
  });
});

describe("avatarMotion idle and helpers", () => {
  it("breathes with small amplitude and zero headPitch", () => {
    for (let t = 0; t < 12; t += 0.25) {
      const pose = idlePose(t);
      expect(pose.headPitch).toBe(0);
      expect(Math.abs(pose.spinePitch)).toBeLessThanOrEqual(0.015 + 1e-12);
      expect(Math.abs(pose.hipsY)).toBeLessThanOrEqual(0.004 + 1e-12);
      expect(Math.abs(pose.headYaw)).toBeLessThanOrEqual(0.03 + 1e-12);
      expect(Math.abs(pose.headRoll)).toBeLessThanOrEqual(0.015 + 1e-12);
      expect(Math.abs(pose.armLift)).toBeLessThanOrEqual(0.018 + 1e-12);
    }
    expectZeroPose(idlePose(0));
  });

  it("adds poses channel-wise", () => {
    const sum = addPose(
      { ...ZERO_POSE, headPitch: 1, spineYaw: 2, hipsX: 3, armLiftR: 4 },
      { ...ZERO_POSE, headPitch: 10, spineYaw: 20, hipsX: 30, armLiftR: 40 },
    );
    expect(sum).toEqual({
      ...ZERO_POSE,
      headPitch: 11,
      spineYaw: 22,
      hipsX: 33,
      armLiftR: 44,
    });
  });

  it("splits pose channels per arm and adds the shared lift", () => {
    const pose = {
      ...ZERO_POSE,
      armLift: 0.5,
      armLiftL: 1,
      armLiftR: 2,
      armForwardR: 0.25,
      elbowL: -0.2,
      elbowUpR: 1.5,
      palmTurnR: 0.75,
    };
    expect(armChannels(pose, "left")).toEqual({
      lift: 1.5,
      forward: 0,
      elbow: -0.2,
      elbowUp: 0,
      palmTurn: 0,
    });
    expect(armChannels(pose, "right")).toEqual({
      lift: 2.5,
      forward: 0.25,
      elbow: 0,
      elbowUp: 1.5,
      palmTurn: 0.75,
    });
  });

  it("maps voice level to mouth weights", () => {
    for (const t of [0, 0.1, 0.37]) {
      expect(mouthWeightsFromLevel(0, t)).toEqual({ aa: 0, ih: 0, ou: 0 });
      const loud = mouthWeightsFromLevel(1, t);
      expect(loud.aa).toBeCloseTo(0.9, 9);
      expect(loud.ih).toBeGreaterThanOrEqual(0);
      expect(loud.ih).toBeLessThanOrEqual(0.25);
      expect(loud.ou).toBeGreaterThanOrEqual(0);
      expect(loud.ou).toBeLessThanOrEqual(0.2);
    }
    // 範囲外の入力もクランプされる
    expect(mouthWeightsFromLevel(3, 0).aa).toBeCloseTo(0.9, 9);
    expect(mouthWeightsFromLevel(-1, 0)).toEqual({ aa: 0, ih: 0, ou: 0 });
  });

  it("schedules blinks between 2.5 and 6.0 seconds", () => {
    expect(nextBlinkDelay(() => 0)).toBeCloseTo(2.5, 9);
    expect(nextBlinkDelay(() => 1)).toBeCloseTo(6.0, 9);
    expect(nextBlinkDelay(() => 0.5)).toBeCloseTo(4.25, 9);
  });

  it("shapes the blink as close then open", () => {
    expect(blinkWeight(-1)).toBe(0);
    expect(blinkWeight(0)).toBe(0);
    expect(blinkWeight(BLINK_CLOSE_SEC / 2)).toBeCloseTo(0.5, 9);
    expect(blinkWeight(BLINK_CLOSE_SEC)).toBeCloseTo(1, 9);
    expect(blinkWeight(BLINK_CLOSE_SEC + BLINK_OPEN_SEC / 2)).toBeCloseTo(
      0.5,
      9,
    );
    expect(blinkWeight(BLINK_TOTAL_SEC)).toBe(0);
    expect(blinkWeight(BLINK_TOTAL_SEC + 1)).toBe(0);
    expect(isBlinkDone(0)).toBe(false);
    expect(isBlinkDone(BLINK_CLOSE_SEC)).toBe(false);
    expect(isBlinkDone(BLINK_TOTAL_SEC)).toBe(true);
  });
});

/* 描画側と同じ手順で回転を合成し、姿勢の向きを three.js で検証する */

function quatOf(tilt: AxisAngle | null): Quaternion {
  if (!tilt) throw new Error("tilt is null");
  return new Quaternion().setFromAxisAngle(
    new Vector3(...tilt.axis),
    tilt.angle,
  );
}

function rotate(v: Vec3, q: Quaternion): Vector3 {
  return new Vector3(...v).applyQuaternion(q);
}

/**
 * 想定する rest 姿勢の組み合わせ。VRM 1.0 は +Z 向き(左腕 +X)、0.x は -Z 向き
 * (左腕 -X)。右腕は常に左腕の逆方向
 */
const RIGS: Array<{ label: string; facing: 1 | -1; leftArmX: 1 | -1 }> = [
  { label: "vrm1", facing: 1, leftArmX: 1 },
  { label: "vrm0", facing: -1, leftArmX: -1 },
];

describe("avatarMotion rest pose geometry", () => {
  it("tilts a direction toward the target and rejects parallel inputs", () => {
    const from: Vec3 = [1, 0, 0];
    const toward: Vec3 = [0, -1, 0];
    const tilt = tiltTowards(from, toward, 0.5);
    expect(tilt).not.toBeNull();
    const axis = new Vector3(...(tilt as AxisAngle).axis);
    expect(axis.length()).toBeCloseTo(1, 9);
    const before = new Vector3(...from).dot(new Vector3(...toward));
    const after = rotate(from, quatOf(tilt)).dot(new Vector3(...toward));
    expect(after).toBeGreaterThan(before);
    expect(tiltTowards(from, [2, 0, 0], 0.5)).toBeNull();
    expect(tiltTowards(from, [-1, 0, 0], 0.5)).toBeNull();
    expect(tiltTowards([0, 0, 0], toward, 0.5)).toBeNull();
  });

  it("derives a frontal-plane raise axis from the arm direction", () => {
    for (const lateral of [1, -1]) {
      const armDir: Vec3 = [lateral, 0, 0];
      const axis = axisBetween(armDir, [0, 1, 0]);
      expect(axis).not.toBeNull();
      const raised = rotate(
        armDir,
        new Quaternion().setFromAxisAngle(new Vector3(...(axis as Vec3)), 1.2),
      );
      // 前腕は前額面内で持ち上がり、左右どちらの腕でも上を向く
      expect(raised.y).toBeGreaterThan(0.8);
      expect(Math.abs(raised.z)).toBeLessThan(1e-9);
    }
    expect(axisBetween([1, 0, 0], [2, 0, 0])).toBeNull();
  });

  it("keeps the rest angles within a natural standing range", () => {
    for (const side of ["left", "right"] as const) {
      const angles = ARM_REST[side];
      // 真下(π/2)より手前で止め、A ポーズ(0.9 以下)にも万歳にもならない
      expect(angles.lower).toBeGreaterThan(1.1);
      expect(angles.lower).toBeLessThan(Math.PI / 2);
      expect(angles.forward).toBeGreaterThan(0);
      expect(angles.forward).toBeLessThan(0.3);
      expect(angles.bend).toBeGreaterThan(0);
      expect(angles.bend).toBeLessThan(0.7);
    }
    expect(ARM_REST.left).not.toEqual(ARM_REST.right);
  });

  it.each(RIGS)("hangs both arms down, slightly forward, for $label", ({
    facing,
    leftArmX,
  }) => {
    const forward: Vec3 = [0, 0, facing];
    const sides: Array<[ArmSide, number]> = [
      ["left", leftArmX],
      ["right", -leftArmX],
    ];
    for (const [side, lateral] of sides) {
      const armDir: Vec3 = [lateral, 0, 0];
      const angles = ARM_REST[side];
      const upper = quatOf(tiltTowards(DOWN, forward, angles.forward)).multiply(
        quatOf(tiltTowards(armDir, DOWN, angles.lower)),
      );
      const upperDir = rotate(armDir, upper);
      // 腕は下を向き、体の外側にわずかに開き、少し前へ出る
      expect(upperDir.y).toBeLessThan(-0.9);
      expect(upperDir.x * lateral).toBeGreaterThan(0);
      expect(upperDir.z * facing).toBeGreaterThan(0);
      // 肘は前へ曲がる: 前腕は上腕よりさらに前を向く
      const elbow = quatOf(tiltTowards(armDir, forward, angles.bend));
      const forearmDir = rotate(armDir, upper.clone().multiply(elbow));
      expect(forearmDir.z * facing).toBeGreaterThan(upperDir.z * facing);
      expect(forearmDir.y).toBeLessThan(-0.8);
    }
  });

  it.each(RIGS)("turns the palm toward the front for $label", ({ facing }) => {
    const forward: Vec3 = [0, 0, facing];
    const axis = axisBetween(DOWN, forward);
    expect(axis).not.toBeNull();
    // ひねり軸は rest の骨軸(±X)と平行 = 前腕まわりの純粋なひねり
    expect(Math.abs((axis as Vec3)[0])).toBeCloseTo(1, 9);
    // 手のひらの rest 法線(DOWN)が 90 度のひねりで前方を向く
    const palm = rotate(
      DOWN,
      new Quaternion().setFromAxisAngle(
        new Vector3(...(axis as Vec3)),
        Math.PI / 2,
      ),
    );
    expect(palm.z * facing).toBeGreaterThan(0.99);
  });

  it.each(RIGS)("curls fingers toward the palm for $label", ({ leftArmX }) => {
    for (const lateral of [leftArmX, -leftArmX]) {
      const fingerDir: Vec3 = [lateral, 0, 0];
      for (const finger of FINGER_NAMES) {
        const curls = FINGER_CURL[finger];
        expect(curls).toHaveLength(FINGER_SEGMENTS[finger].length);
        let total = new Quaternion();
        for (const curl of curls) {
          expect(curl).toBeGreaterThanOrEqual(0);
          expect(curl).toBeLessThan(0.8);
          total = total.multiply(quatOf(tiltTowards(fingerDir, DOWN, curl)));
        }
        const tip = rotate(fingerDir, total);
        // 手のひら(rest では下向き)側へ曲がり、反り返らない
        expect(tip.y).toBeLessThan(-0.3);
        expect(tip.x * lateral).toBeGreaterThan(0);
      }
    }
    // 人差し指より小指のほうが深く握る
    expect(FINGER_CURL.little[0]).toBeGreaterThan(FINGER_CURL.index[0]);
  });

  it("builds three-vrm bone names for fingers", () => {
    expect(fingerBoneName("left", "thumb", "metacarpal")).toBe(
      "leftThumbMetacarpal",
    );
    expect(fingerBoneName("right", "index", "intermediate")).toBe(
      "rightIndexIntermediate",
    );
    expect(fingerBoneName("left", "little", "distal")).toBe("leftLittleDistal");
  });
});

describe("avatarMotion facing and bone rotation", () => {
  it("reads the facing from the left arm and falls back to the spec version", () => {
    expect(detectFacing([1, 0, 0], "0")).toBe(1);
    expect(detectFacing([-0.7, 0.1, 0], "1")).toBe(-1);
    expect(detectFacing(null, "1")).toBe(1);
    expect(detectFacing(null, "0")).toBe(-1);
    // X 成分がほぼ 0 なら腕からは判定せず仕様版に従う
    expect(detectFacing([1e-6, -1, 0], "0")).toBe(-1);
  });

  /** 頭・背骨の Euler 回転で単位ベクトルを回した結果 */
  function rotateBy(head: Vec3, v: Vec3): Vector3 {
    return new Vector3(...v).applyEuler(new Euler(...head));
  }

  const UP: Vec3 = [0, 1, 0];

  it.each(RIGS)("maps model-relative offsets onto bone axes for $label", ({
    facing,
  }) => {
    const forward: Vec3 = [0, 0, facing];
    const left: Vec3 = [facing, 0, 0];
    const pitch = poseToBoneRotation(
      { ...ZERO_POSE, headPitch: 0.3, spinePitch: 0.2 },
      facing,
    );
    // 前傾: 頭頂と上体の先端が前(モデルの向き)へ動く
    expect(
      rotateBy(pitch.head, UP).dot(new Vector3(...forward)),
    ).toBeGreaterThan(0.1);
    expect(
      rotateBy(pitch.spine, UP).dot(new Vector3(...forward)),
    ).toBeGreaterThan(0.1);
    // 左向き: 顔の向きがモデルの左へ回る
    const yaw = poseToBoneRotation({ ...ZERO_POSE, headYaw: 0.3 }, facing);
    expect(
      rotateBy(yaw.head, forward).dot(new Vector3(...left)),
    ).toBeGreaterThan(0.1);
    // 左肩側へ傾げ: 頭頂がモデルの左へ動く
    const roll = poseToBoneRotation({ ...ZERO_POSE, headRoll: 0.3 }, facing);
    expect(rotateBy(roll.head, UP).dot(new Vector3(...left))).toBeGreaterThan(
      0.1,
    );
    // 上体のひねり: 前方がモデルの左へ回る
    const spinYaw = poseToBoneRotation({ ...ZERO_POSE, spineYaw: 0.3 }, facing);
    expect(
      rotateBy(spinYaw.spine, forward).dot(new Vector3(...left)),
    ).toBeGreaterThan(0.1);
    // 上体の傾げ: 上体の先端がモデルの左へ動く
    const spinRoll = poseToBoneRotation(
      { ...ZERO_POSE, spineRoll: 0.3 },
      facing,
    );
    expect(
      rotateBy(spinRoll.spine, UP).dot(new Vector3(...left)),
    ).toBeGreaterThan(0.1);
    // 0 は 0 のまま(facing が -1 のとき -0 になるため絶対値で比べる)
    const zero = poseToBoneRotation(ZERO_POSE, facing);
    expect(zero.head.map(Math.abs)).toEqual([0, 0, 0]);
    expect(zero.spine.map(Math.abs)).toEqual([0, 0, 0]);
  });

  it.each(
    RIGS,
  )("leans forward toward the viewer and back away from it for $label", ({
    facing,
  }) => {
    const forwardZ = (key: AvatarGestureKey, f: Facing): number => {
      const rotation = poseToBoneRotation(sampleGesture(key, 0.5), f);
      return rotateBy(rotation.spine, UP).z * f;
    };
    expect(forwardZ("lean_forward", facing)).toBeGreaterThan(0.05);
    expect(forwardZ("lean_back", facing)).toBeLessThan(-0.05);
  });
});

describe("mouthWeightsFromViseme", () => {
  it("activates only the channel for the viseme", () => {
    expect(mouthWeightsFromViseme("aa", 1, true, true)).toEqual({
      ...CLOSED_MOUTH_TARGETS,
      aa: 1,
    });
    expect(mouthWeightsFromViseme("oh", 0.4, true, true)).toEqual({
      ...CLOSED_MOUTH_TARGETS,
      oh: 0.4,
    });
  });

  it("falls back ee->ih and oh->ou when presets are missing", () => {
    expect(mouthWeightsFromViseme("ee", 1, false, true)).toEqual({
      ...CLOSED_MOUTH_TARGETS,
      ih: 1,
    });
    expect(mouthWeightsFromViseme("oh", 1, true, false)).toEqual({
      ...CLOSED_MOUTH_TARGETS,
      ou: 1,
    });
    // プリセットがあるときは振り替えない
    expect(mouthWeightsFromViseme("ee", 1, true, true).ee).toBe(1);
  });

  it("returns closed mouth for null or unknown visemes and clamps weight", () => {
    expect(mouthWeightsFromViseme(null, 1, true, true)).toEqual(
      CLOSED_MOUTH_TARGETS,
    );
    expect(mouthWeightsFromViseme("xx", 1, true, true)).toEqual(
      CLOSED_MOUTH_TARGETS,
    );
    expect(mouthWeightsFromViseme("aa", 2, true, true).aa).toBe(1);
  });
});

describe("approachMouthTargets", () => {
  const open = { ...CLOSED_MOUTH_TARGETS, aa: 1 };

  it("opens faster than it closes", () => {
    const opened = approachMouthTargets(CLOSED_MOUTH_TARGETS, open, 0.03);
    const closed = approachMouthTargets(open, CLOSED_MOUTH_TARGETS, 0.03);
    expect(opened.aa).toBeGreaterThan(0.5);
    expect(1 - closed.aa).toBeLessThan(0.5);
  });

  it("converges to the target and ignores negative delta", () => {
    const settled = approachMouthTargets(CLOSED_MOUTH_TARGETS, open, 10);
    expect(settled.aa).toBeCloseTo(1, 3);
    expect(approachMouthTargets(CLOSED_MOUTH_TARGETS, open, -1)).toEqual(
      CLOSED_MOUTH_TARGETS,
    );
  });
});
