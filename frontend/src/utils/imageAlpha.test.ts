import { describe, expect, it } from "vitest";
import { hasMeaningfulAlpha } from "./imageAlpha";

function makePixels(
  count: number,
  alphaForIndex: (index: number) => number,
): Uint8ClampedArray {
  const data = new Uint8ClampedArray(count * 4);
  for (let i = 0; i < count; i += 1) {
    data[i * 4] = 255;
    data[i * 4 + 1] = 255;
    data[i * 4 + 2] = 255;
    data[i * 4 + 3] = alphaForIndex(i);
  }
  return data;
}

describe("hasMeaningfulAlpha", () => {
  it("returns false for a fully opaque image", () => {
    const data = makePixels(4096, () => 255);
    expect(hasMeaningfulAlpha(data)).toBe(false);
  });

  it("returns true for a V5-style transparent-background image", () => {
    // 周囲半分が完全透過（transparent background で生成された立ち絵を模す）
    const data = makePixels(4096, (i) => (i < 2048 ? 0 : 255));
    expect(hasMeaningfulAlpha(data)).toBe(true);
  });

  it("ignores a negligible amount of near-transparent noise", () => {
    // サンプル対象のうちごく一部だけ半透明（JPEG転送ノイズ等）
    const data = makePixels(65536, (i) => (i === 0 ? 128 : 255));
    expect(hasMeaningfulAlpha(data)).toBe(false);
  });

  it("handles empty input", () => {
    expect(hasMeaningfulAlpha(new Uint8ClampedArray(0))).toBe(false);
  });
});
