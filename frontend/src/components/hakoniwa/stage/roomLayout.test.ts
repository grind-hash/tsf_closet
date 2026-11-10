import { describe, expect, it } from "vitest";
import { affinityLevel, moodLevel } from "../hakoniwaLabels";
import {
  AVATAR_H,
  anchorRatio,
  DEPTH_SCALE_BACK,
  depthScale,
  FLOOR_BOTTOM,
  FLOOR_TOP,
  FOCUS_MIN_Y,
  FOCUS_SPACING,
  focusTargets,
  focusZone,
  GAME_H,
  GAME_W,
  initialPosition,
  isPathBlocked,
  NAME_HEIGHT,
  NAME_OFFSET,
  nearestWithin,
  PASSING_CLEARANCE,
  PASSING_SPACE_Y,
  PERSONAL_SPACE_X,
  pathClearance,
  pickWanderTarget,
  STROLL_MAX_DX,
  spaceDistance,
  stepToward,
  walkSpeedFactor,
} from "./roomLayout";

/** 再現できる乱数(線形合同法) */
function seededRandom(start = 0): () => number {
  let seed = start;
  return () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };
}

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

  it("picks wander targets outside others' personal space", () => {
    const from = { x: 300, y: 680 };
    const others = [{ x: 600, y: 680 }];
    const random = seededRandom();
    for (let i = 0; i < 20; i += 1) {
      const target = pickWanderTarget(from, others, 0, random);
      expect(target.y).toBeGreaterThanOrEqual(FLOOR_TOP);
      expect(target.y).toBeLessThanOrEqual(FLOOR_BOTTOM);
      expect(spaceDistance(target, others[0])).toBeGreaterThanOrEqual(1);
    }
  });

  it("does not walk straight through a standing resident", () => {
    const from = { x: 300, y: 680 };
    const other = { x: 600, y: 680 };
    const random = seededRandom(7);
    for (let i = 0; i < 30; i += 1) {
      const target = pickWanderTarget(from, [other], 0, random);
      expect(pathClearance(from, target, other)).toBeGreaterThanOrEqual(
        PASSING_CLEARANCE,
      );
    }
  });

  it("steps away from someone close by instead of pushing past them", () => {
    const from = { x: 300, y: 680 };
    const other = { x: 340, y: 680 };
    const start = spaceDistance(from, other, PASSING_SPACE_Y);
    const random = seededRandom(11);
    for (let i = 0; i < 30; i += 1) {
      const target = pickWanderTarget(from, [other], 0, random);
      const closest = pathClearance(from, target, other);
      expect(closest >= start - 0.01 || closest >= PASSING_CLEARANCE).toBe(
        true,
      );
    }
  });

  it("mostly strolls near where the resident stands", () => {
    const from = { x: 600, y: 680 };
    const random = seededRandom(3);
    let near = 0;
    for (let i = 0; i < 200; i += 1) {
      const target = pickWanderTarget(from, [], 0, random);
      if (Math.abs(target.x - from.x) <= STROLL_MAX_DX) near += 1;
    }
    expect(near).toBeGreaterThan(120);
  });

  it("stands side by side, but lets people pass in front or behind", () => {
    const base = { x: 500, y: 680 };
    expect(spaceDistance(base, { x: 600, y: 680 })).toBeLessThan(1);
    // 真ん前・真後ろに立つと体が隠れるので、奥行きが違っても間合いに入る
    expect(spaceDistance(base, { x: 500, y: FLOOR_BOTTOM })).toBeLessThan(1);
    expect(spaceDistance(base, { x: 690, y: FLOOR_BOTTOM })).toBeGreaterThan(1);
    // すれ違うだけなら、奥行きが離れていれば間合いの外
    expect(
      spaceDistance(base, { x: 500, y: FLOOR_BOTTOM }, PASSING_SPACE_Y),
    ).toBeGreaterThan(1);
  });

  it("keeps bystanders out of the spot where an event gathers", () => {
    const zone = focusZone([
      { x: 500, y: 700 },
      { x: 664, y: 700 },
    ]);
    expect(zone).toEqual({
      min: 500 - PERSONAL_SPACE_X,
      max: 664 + PERSONAL_SPACE_X,
    });
    for (const from of [
      { x: 200, y: 700 },
      { x: 580, y: 700 },
      { x: 1000, y: 700 },
    ]) {
      for (let i = 0; i < 30; i += 1) {
        const target = pickWanderTarget(from, [], 0, Math.random, zone);
        expect(target.x <= zone!.min || target.x >= zone!.max).toBe(true);
      }
    }
    expect(focusZone([])).toBeNull();
  });

  it("stops before walking into someone, but lets people walk away", () => {
    const other = { x: 600, y: 680 };
    expect(isPathBlocked({ x: 470, y: 680 }, { x: 900, y: 680 }, [other])).toBe(
      true,
    );
    expect(isPathBlocked({ x: 520, y: 680 }, { x: 200, y: 680 }, [other])).toBe(
      false,
    );
    // 奥行きが十分に離れていれば、前後をすれ違うだけなので止まらない
    expect(isPathBlocked({ x: 470, y: 780 }, { x: 900, y: 780 }, [other])).toBe(
      false,
    );
  });

  it("eases into a walk and slows down before arriving", () => {
    expect(walkSpeedFactor(0, 300)).toBeCloseTo(0.2);
    expect(walkSpeedFactor(200, 300)).toBeLessThan(1);
    expect(walkSpeedFactor(1000, 300)).toBe(1);
    expect(walkSpeedFactor(1000, 7)).toBeLessThan(1);
    expect(walkSpeedFactor(1000, 0)).toBeCloseTo(0.2);
  });

  it("finds the nearest neighbor to turn toward", () => {
    const others = [
      { x: 900, y: 700 },
      { x: 450, y: 700 },
    ];
    expect(nearestWithin({ x: 600, y: 700 }, others, 420)).toEqual(others[1]);
    expect(nearestWithin({ x: 0, y: 700 }, others, 420)).toBeNull();
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

  it("draws residents smaller toward the back of the floor", () => {
    expect(depthScale(FLOOR_BOTTOM)).toBeCloseTo(1);
    expect(depthScale(FLOOR_TOP)).toBeCloseTo(DEPTH_SCALE_BACK);
    expect(depthScale(FLOOR_TOP - 100)).toBeCloseTo(DEPTH_SCALE_BACK);
    const middle = depthScale((FLOOR_TOP + FLOOR_BOTTOM) / 2);
    expect(middle).toBeGreaterThan(DEPTH_SCALE_BACK);
    expect(middle).toBeLessThan(1);
    // 奥に立つ住民の吹き出しは、縮めた頭の上(手前より下がった位置)に置く
    const back = anchorRatio({ x: 100, y: FLOOR_TOP });
    expect(back.y).toBeCloseTo(
      (FLOOR_TOP - (AVATAR_H + NAME_OFFSET + NAME_HEIGHT) * DEPTH_SCALE_BACK) /
        GAME_H,
    );
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
