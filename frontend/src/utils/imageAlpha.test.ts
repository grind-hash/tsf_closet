// @vitest-environment node

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createTransparentImageCache, hasMeaningfulAlpha } from "./imageAlpha";

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

// revoke は解決済み promise の then で走るので、マクロタスクを 1 つ挟めば観測できる
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
const toBlobUrl = async (src: string) => `blob:${src}`;

describe("createTransparentImageCache", () => {
  const revoked: string[] = [];

  beforeEach(() => {
    revoked.length = 0;
    vi.spyOn(URL, "revokeObjectURL").mockImplementation((url) => {
      revoked.push(url);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never revokes a URL that is still held, even past the limit", async () => {
    const cache = createTransparentImageCache(toBlobUrl, 2);
    const held = cache.retain("a");
    void cache.resolve("b");
    void cache.resolve("c");
    await flush();

    expect(await held.url).toBe("blob:a");
    expect(revoked).toEqual(["blob:b"]);
    expect(cache.size).toBe(2);
  });

  it("keeps the newest entry and reclaims released ones on the next insert", async () => {
    const cache = createTransparentImageCache(toBlobUrl, 1);
    const held = cache.retain("a");
    void cache.resolve("b");
    await flush();
    expect(revoked).toEqual([]);

    held.release();
    void cache.resolve("c");
    await flush();
    expect([...revoked].sort()).toEqual(["blob:a", "blob:b"]);
    expect(cache.size).toBe(1);
  });

  it("shares one result between holders and counts each hold once", async () => {
    const processor = vi.fn(toBlobUrl);
    const cache = createTransparentImageCache(processor, 1);
    const first = cache.retain("a");
    const second = cache.retain("a");
    expect(processor).toHaveBeenCalledTimes(1);

    first.release();
    first.release();
    void cache.resolve("b");
    await flush();
    expect(revoked).toEqual([]);

    second.release();
    void cache.resolve("c");
    await flush();
    expect(revoked).toContain("blob:a");
  });

  it("leaves pass-through URLs alone when evicting", async () => {
    const cache = createTransparentImageCache(async (src) => src, 1);
    void cache.resolve("/api/a.png");
    void cache.resolve("/api/b.png");
    await flush();

    expect(revoked).toEqual([]);
    expect(cache.size).toBe(1);
  });

  it("does not memoize a failed result", async () => {
    const processor = vi.fn(async () => {
      throw new Error("boom");
    });
    const cache = createTransparentImageCache(processor, 4);

    await expect(cache.retain("a").url).rejects.toThrow("boom");
    await expect(cache.retain("a").url).rejects.toThrow("boom");
    expect(processor).toHaveBeenCalledTimes(2);
    expect(cache.size).toBe(0);
  });
});
