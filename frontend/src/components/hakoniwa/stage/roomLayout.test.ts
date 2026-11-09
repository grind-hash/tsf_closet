import { describe, expect, it } from "vitest";
import { affinityLevel, moodLevel } from "../hakoniwaLabels";
import {
  AVATAR_H,
  anchorRatio,
  FLOOR_BOTTOM,
  FLOOR_TOP,
  FOCUS_MIN_Y,
  FOCUS_SPACING,
  focusTargets,
  focusZone,
  GAME_H,
  GAME_W,
  initialPosition,
  MIN_SPACING,
  pickWanderTarget,
  stepToward,
} from "./roomLayout";

describe("roomLayout", () => {
  it("spreads residents across the floor", () => {
    const positions = [0, 1, 2, 3, 4].map((index) => initialPosition(index, 5));
    for (const point of positions) {
      expect(point.x).toBeGreaterThanOrEqual(80);
      expect(point.x).toBeLessThanOrEqual(GAME_W - 80);
      expect(point.y).toBeGreaterThanOrEqual(FLOOR_TOP);
      expect(point.y).toBeLessThanOrEqual(FLOOR_BOTTOM);
    }
    const xs = positions.map((point) => point.x);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
  });

  it("picks wander targets away from others when possible", () => {
    const others = [{ x: 600, y: 680 }];
    let seed = 0;
    const random = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };
    for (let i = 0; i < 20; i += 1) {
      const target = pickWanderTarget(others, 0, random);
      expect(target.y).toBeGreaterThanOrEqual(FLOOR_TOP);
      expect(target.y).toBeLessThanOrEqual(FLOOR_BOTTOM);
      expect(Math.hypot(target.x - 600, target.y - 680)).toBeGreaterThanOrEqual(
        MIN_SPACING,
      );
    }
  });

  it("keeps bystanders out of the spot where an event gathers", () => {
    const zone = focusZone([
      { x: 500, y: 700 },
      { x: 664, y: 700 },
    ]);
    expect(zone).toEqual({ min: 370, max: 794 });
    for (let i = 0; i < 30; i += 1) {
      const target = pickWanderTarget([], 0, Math.random, zone);
      expect(target.x < 370 || target.x > 794).toBe(true);
    }
    expect(focusZone([])).toBeNull();
  });

  it("lines a group up facing the middle, keeping left-to-right order", () => {
    const targets = focusTargets([
      { x: 900, y: 600 },
      { x: 200, y: 700 },
      { x: 500, y: 760 },
    ]);
    // 左から 2人目(x=200)、3人目(x=500)、1人目(x=900) の順に並ぶ
    expect(targets[1].x).toBeLessThan(targets[2].x);
    expect(targets[2].x).toBeLessThan(targets[0].x);
    expect(targets[2].x - targets[1].x).toBe(FOCUS_SPACING);
    expect(targets.every((target) => target.y >= FOCUS_MIN_Y)).toBe(true);
    expect(targets[1].flip).toBe(false);
    expect(targets[2].flip).toBe(false);
    expect(targets[0].flip).toBe(true);
  });

  it("keeps a single resident near where they stand", () => {
    const [target] = focusTargets([{ x: 100, y: 600 }]);
    expect(target.flip).toBe(false);
    expect(target.y).toBe(FOCUS_MIN_Y);
  });

  it("points bubble anchors above the name tag", () => {
    const anchor = anchorRatio({ x: GAME_W / 2, y: FLOOR_BOTTOM });
    expect(anchor.x).toBeCloseTo(0.5);
    expect(anchor.y).toBeLessThan((FLOOR_BOTTOM - AVATAR_H) / GAME_H);
  });

  it("steps toward a target and reports arrival", () => {
    const moving = stepToward({ x: 0, y: 0 }, { x: 100, y: 0 }, 1000, 58);
    expect(moving.arrived).toBe(false);
    expect(moving.position.x).toBeCloseTo(58);
    const arrived = stepToward({ x: 99, y: 0 }, { x: 100, y: 0 }, 1000, 58);
    expect(arrived.arrived).toBe(true);
    expect(arrived.position).toEqual({ x: 100, y: 0 });
  });

  it("labels moods and affinities in five steps", () => {
    expect([90, 70, 50, 30, 5].map(moodLevel)).toEqual([
      "great",
      "good",
      "normal",
      "down",
      "low",
    ]);
    expect([-40, -10, 0, 20, 45].map(affinityLevel)).toEqual([
      "hostile",
      "awkward",
      "neutral",
      "friendly",
      "close",
    ]);
  });
});
