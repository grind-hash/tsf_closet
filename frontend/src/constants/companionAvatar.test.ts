import { describe, expect, it } from "vitest";
import {
  AVATAR_EXPRESSION_DEFAULT,
  AVATAR_EXPRESSIONS,
  AVATAR_GESTURE_DEFAULT,
  AVATAR_GESTURES,
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "./companionAvatar";

describe("companionAvatar", () => {
  it("defaults belong to the vocabulary", () => {
    expect(AVATAR_EXPRESSIONS).toContain(AVATAR_EXPRESSION_DEFAULT);
    expect(AVATAR_GESTURES).toContain(AVATAR_GESTURE_DEFAULT);
  });

  it("normalizes expression keys", () => {
    expect(normalizeAvatarExpression(" HAPPY ")).toBe("happy");
    expect(normalizeAvatarExpression("Relaxed")).toBe("relaxed");
    expect(normalizeAvatarExpression("neutral")).toBe("neutral");
    expect(normalizeAvatarExpression("wave")).toBeNull();
    expect(normalizeAvatarExpression("")).toBeNull();
    expect(normalizeAvatarExpression(null)).toBeNull();
    expect(normalizeAvatarExpression(undefined)).toBeNull();
  });

  it("normalizes gesture keys", () => {
    expect(normalizeAvatarGesture("Shake-Head")).toBe("shake_head");
    expect(normalizeAvatarGesture("lean forward")).toBe("lean_forward");
    expect(normalizeAvatarGesture("Wave-Hand")).toBe("wave_hand");
    expect(normalizeAvatarGesture("double bounce")).toBe("double_bounce");
    expect(normalizeAvatarGesture("  Idle ")).toBe("idle");
    expect(normalizeAvatarGesture("wave")).toBeNull();
    expect(normalizeAvatarGesture(null)).toBeNull();
    expect(normalizeAvatarGesture(undefined)).toBeNull();
    expect(normalizeAvatarGesture(42)).toBeNull();
  });

  it("accepts every key of its own vocabulary", () => {
    for (const key of AVATAR_EXPRESSIONS) {
      expect(normalizeAvatarExpression(key)).toBe(key);
    }
    for (const key of AVATAR_GESTURES) {
      expect(normalizeAvatarGesture(key)).toBe(key);
    }
  });
});
