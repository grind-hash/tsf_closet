import { describe, expect, it } from "vitest";
import { live2dPortraitFrame } from "./costumes";

describe("live2dPortraitFrame", () => {
  it("frames the bunny costume lower, since the ears push the face down", () => {
    const [x, y, width, height] = live2dPortraitFrame("bunny");
    const [defaultX, , defaultWidth] = live2dPortraitFrame("dress");
    // 顔の中心(449)に合わせた横位置で、耳の先(y=23)を切らない
    expect(x + width / 2).toBe(449);
    expect(x).toBeGreaterThan(defaultX);
    expect(width).toBe(defaultWidth);
    expect(y).toBeLessThan(23);
    expect(height).toBeGreaterThan(0);
  });

  it("falls back to the default framing for a costume it does not know", () => {
    expect(live2dPortraitFrame("tuxedo")).toEqual(live2dPortraitFrame("dress"));
    expect(live2dPortraitFrame(null)).toEqual(live2dPortraitFrame("dress"));
    expect(live2dPortraitFrame(undefined)).toEqual(
      live2dPortraitFrame("dress"),
    );
  });
});
