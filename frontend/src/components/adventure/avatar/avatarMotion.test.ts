import { describe, expect, it } from "vitest";
import {
  AVATAR_GESTURES,
  type AvatarGestureKey,
} from "../../../constants/companionAvatar";
import {
  addPose,
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  BLINK_TOTAL_SEC,
  blinkWeight,
  GESTURE_CLIPS,
  gestureDuration,
  idlePose,
  isBlinkDone,
  mouthWeightsFromLevel,
  nextBlinkDelay,
  POSE_KEYS,
  type PoseOffsets,
  sampleGesture,
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
    }
    expectZeroPose(idlePose(0));
  });

  it("adds poses channel-wise", () => {
    const sum = addPose(
      { headPitch: 1, headYaw: 2, headRoll: 3, spinePitch: 4, hipsY: 5 },
      { headPitch: 10, headYaw: 20, headRoll: 30, spinePitch: 40, hipsY: 50 },
    );
    expect(sum).toEqual({
      headPitch: 11,
      headYaw: 22,
      headRoll: 33,
      spinePitch: 44,
      hipsY: 55,
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
