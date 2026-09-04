import { describe, expect, it } from "vitest";
import type { VisemeEvent } from "../apis/speechSynthesis";
import {
  CLOSED_VISEME_FRAME,
  createVisemeCursor,
  visemeAtTime,
} from "./visemeTimeline";

const timeline: VisemeEvent[] = [
  { t0: 0.1, t1: 0.3, viseme: "aa", w: 1 },
  { t0: 0.3, t1: 0.45, viseme: "ih", w: 1 },
  // 0.45..0.6 は閉口区間(pau)
  { t0: 0.6, t1: 0.8, viseme: "oh", w: 0.4 },
];

describe("visemeAtTime", () => {
  it("returns closed mouth for an empty timeline", () => {
    expect(visemeAtTime([], 0.2, createVisemeCursor())).toEqual(
      CLOSED_VISEME_FRAME,
    );
  });

  it("returns the event covering the time and closed mouth in gaps", () => {
    const cursor = createVisemeCursor();
    expect(visemeAtTime(timeline, 0.05, cursor).viseme).toBeNull();
    expect(visemeAtTime(timeline, 0.2, cursor)).toEqual({
      viseme: "aa",
      w: 1,
    });
    expect(visemeAtTime(timeline, 0.35, cursor)).toEqual({
      viseme: "ih",
      w: 1,
    });
    expect(visemeAtTime(timeline, 0.5, cursor).viseme).toBeNull();
    expect(visemeAtTime(timeline, 0.7, cursor)).toEqual({
      viseme: "oh",
      w: 0.4,
    });
    expect(visemeAtTime(timeline, 1.0, cursor).viseme).toBeNull();
  });

  it("advances the cursor monotonically", () => {
    const cursor = createVisemeCursor();
    visemeAtTime(timeline, 0.7, cursor);
    expect(cursor.index).toBe(2);
    visemeAtTime(timeline, 1.0, cursor);
    expect(cursor.index).toBe(3);
  });

  it("rescans from the start when time moves backwards", () => {
    const cursor = createVisemeCursor();
    visemeAtTime(timeline, 0.7, cursor);
    expect(visemeAtTime(timeline, 0.2, cursor)).toEqual({
      viseme: "aa",
      w: 1,
    });
    expect(cursor.index).toBe(0);
  });
});
