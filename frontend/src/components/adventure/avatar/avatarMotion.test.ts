import { Quaternion, Vector3 } from "three";
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
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  BLINK_TOTAL_SEC,
  blinkWeight,
  DOWN,
  FINGER_CURL,
  FINGER_NAMES,
  FINGER_SEGMENTS,
  fingerBoneName,
  GESTURE_CLIPS,
  gestureDuration,
  idlePose,
  isBlinkDone,
  mouthWeightsFromLevel,
  nextBlinkDelay,
  POSE_KEYS,
  type PoseOffsets,
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

  it("keeps every sample finite and within +-0.5", () => {
    for (const key of CLIP_KEYS) {
      for (let step = 0; step <= 20; step++) {
        const pose = sampleGesture(key, step / 20);
        for (const channel of POSE_KEYS) {
          const value = pose[channel];
          expect(Number.isFinite(value)).toBe(true);
          expect(Math.abs(value)).toBeLessThanOrEqual(0.5);
        }
      }
    }
  });

  it("reaches the keyframe peak in the middle of a nod", () => {
    expect(sampleGesture("nod", 0.3).headPitch).toBeCloseTo(0.35, 9);
    expect(sampleGesture("look_away", 0.5).headYaw).toBeCloseTo(0.45, 9);
    expect(GESTURE_CLIPS.look_away.releaseLookAt).toBe(true);
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
      {
        headPitch: 1,
        headYaw: 2,
        headRoll: 3,
        spinePitch: 4,
        hipsY: 5,
        armLift: 6,
      },
      {
        headPitch: 10,
        headYaw: 20,
        headRoll: 30,
        spinePitch: 40,
        hipsY: 50,
        armLift: 60,
      },
    );
    expect(sum).toEqual({
      headPitch: 11,
      headYaw: 22,
      headRoll: 33,
      spinePitch: 44,
      hipsY: 55,
      armLift: 66,
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
