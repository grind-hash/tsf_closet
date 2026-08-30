/**
 * Removes a flat background color (typically white) from generated character
 * images and returns an object URL pointing at a transparent PNG.
 *
 * The pixel work (CIE Lab color distance, edge flood fill, feathering) runs in
 * a Web Worker so the UI thread stays responsive.
 */

export interface RemoveBackgroundOptions {
  /** Background color to strip. Defaults to pure white. */
  targetColor?: { r: number; g: number; b: number } | null;
  /** Lab color distance below which a pixel counts as background. */
  threshold?: number;
  /** Alpha feather radius in pixels. 0 disables feathering. */
  featherRadius?: number;
  /** Worker timeout in milliseconds. */
  timeout?: number;
}

const DEFAULT_OPTIONS: Required<
  Omit<RemoveBackgroundOptions, "targetColor">
> & {
  targetColor: { r: number; g: number; b: number };
} = {
  targetColor: { r: 255, g: 255, b: 255 },
  threshold: 8,
  featherRadius: 1.8,
  timeout: 30000,
};

const WORKER_SOURCE = `
"use strict";

function rgbToLab(r, g, b) {
  let rN = r / 255, gN = g / 255, bN = b / 255;
  rN = rN > 0.04045 ? Math.pow((rN + 0.055) / 1.055, 2.4) : rN / 12.92;
  gN = gN > 0.04045 ? Math.pow((gN + 0.055) / 1.055, 2.4) : gN / 12.92;
  bN = bN > 0.04045 ? Math.pow((bN + 0.055) / 1.055, 2.4) : bN / 12.92;
  let x = rN * 0.4124564 + gN * 0.3575761 + bN * 0.1804375;
  let y = rN * 0.2126729 + gN * 0.7151522 + bN * 0.0721750;
  let z = rN * 0.0193339 + gN * 0.1191920 + bN * 0.9503041;
  x /= 0.95047; z /= 1.08883;
  const f = (t) => (t > 0.008856 ? Math.pow(t, 1 / 3) : 7.787 * t + 16 / 116);
  const fx = f(x), fy = f(y), fz = f(z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function detectBackgroundColor(data, width, height) {
  const sampleSize = Math.max(1, Math.min(20, Math.floor(Math.min(width, height) / 10)));
  const corners = [
    [0, 0],
    [width - sampleSize, 0],
    [0, height - sampleSize],
    [width - sampleSize, height - sampleSize],
  ];
  const counts = new Map();
  for (const [cx, cy] of corners) {
    for (let dy = 0; dy < sampleSize; dy++) {
      for (let dx = 0; dx < sampleSize; dx++) {
        const i = ((cy + dy) * width + (cx + dx)) * 4;
        const key =
          (Math.floor(data[i] / 8) * 8) * 65536 +
          (Math.floor(data[i + 1] / 8) * 8) * 256 +
          Math.floor(data[i + 2] / 8) * 8;
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    }
  }
  let best = -1;
  let bestCount = 0;
  counts.forEach((count, key) => {
    if (count > bestCount) {
      bestCount = count;
      best = key;
    }
  });
  if (best < 0) return { r: 255, g: 255, b: 255 };
  return {
    r: Math.floor(best / 65536),
    g: Math.floor(best / 256) % 256,
    b: best % 256,
  };
}

function buildBackgroundMask(data, width, height, bg, threshold) {
  const total = width * height;
  const mask = new Uint8Array(total);
  const bgLab = rgbToLab(bg.r, bg.g, bg.b);
  // Cache Lab distances per quantized color; generated images reuse few tones.
  const cache = new Map();
  for (let i = 0; i < total; i++) {
    const di = i * 4;
    const key = data[di] * 65536 + data[di + 1] * 256 + data[di + 2];
    let hit = cache.get(key);
    if (hit === undefined) {
      const lab = rgbToLab(data[di], data[di + 1], data[di + 2]);
      const dl = lab[0] - bgLab[0];
      const da = lab[1] - bgLab[1];
      const db = lab[2] - bgLab[2];
      hit = Math.sqrt(dl * dl + da * da + db * db) < threshold ? 1 : 0;
      cache.set(key, hit);
    }
    mask[i] = hit;
  }
  return mask;
}

function floodFillFromEdges(mask, width, height) {
  const total = width * height;
  const alpha = new Float32Array(total).fill(1);
  const visited = new Uint8Array(total);
  const stack = new Int32Array(total);
  let top = 0;
  for (let x = 0; x < width; x++) {
    stack[top++] = x;
    stack[top++] = (height - 1) * width + x;
  }
  for (let y = 1; y < height - 1; y++) {
    stack[top++] = y * width;
    stack[top++] = y * width + width - 1;
  }
  let cleared = 0;
  while (top > 0) {
    const idx = stack[--top];
    if (visited[idx]) continue;
    visited[idx] = 1;
    if (!mask[idx]) continue;
    alpha[idx] = 0;
    cleared++;
    const x = idx % width;
    const y = (idx - x) / width;
    if (x > 0) stack[top++] = idx - 1;
    if (x < width - 1) stack[top++] = idx + 1;
    if (y > 0) stack[top++] = idx - width;
    if (y < height - 1) stack[top++] = idx + width;
  }
  return { alpha: alpha, cleared: cleared };
}

function featherAlpha(alpha, width, height, radius) {
  const out = new Float32Array(alpha);
  const ceilR = Math.ceil(radius);
  const sigma = radius / 2;
  const weights = [];
  for (let d = 0; d <= ceilR; d++) {
    weights.push(Math.exp(-(d * d) / (2 * sigma * sigma)));
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const ci = y * width + x;
      const base = alpha[ci];
      let isEdge = false;
      for (let dy = -1; dy <= 1 && !isEdge; dy++) {
        for (let dx = -1; dx <= 1 && !isEdge; dx++) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
          if (Math.abs(alpha[ny * width + nx] - base) > 0.5) isEdge = true;
        }
      }
      if (!isEdge) continue;
      let sum = 0;
      let weight = 0;
      for (let dy = -ceilR; dy <= ceilR; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -ceilR; dx <= ceilR; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= width) continue;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > radius) continue;
          const w = weights[Math.round(dist)];
          sum += alpha[ny * width + nx] * w;
          weight += w;
        }
      }
      out[ci] = weight > 0 ? sum / weight : base;
    }
  }
  return out;
}

self.onmessage = function (event) {
  const payload = event.data;
  const data = new Uint8ClampedArray(payload.buffer);
  const width = payload.width;
  const height = payload.height;
  const bg = payload.targetColor || detectBackgroundColor(data, width, height);
  const mask = buildBackgroundMask(data, width, height, bg, payload.threshold);
  const filled = floodFillFromEdges(mask, width, height);
  const alpha =
    payload.featherRadius > 0
      ? featherAlpha(filled.alpha, width, height, payload.featherRadius)
      : filled.alpha;
  for (let i = 0; i < alpha.length; i++) {
    data[i * 4 + 3] = Math.round(Math.max(0, Math.min(1, alpha[i])) * 255);
  }
  self.postMessage(
    { buffer: data.buffer, cleared: filled.cleared, total: width * height },
    [data.buffer],
  );
};
`;

let workerUrl: string | null = null;

function getWorkerUrl(): string {
  if (!workerUrl) {
    workerUrl = URL.createObjectURL(
      new Blob([WORKER_SOURCE], { type: "application/javascript" }),
    );
  }
  return workerUrl;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const absolute = new URL(src, window.location.href);
    if (absolute.origin !== window.location.origin) {
      image.crossOrigin = "anonymous";
    }
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    image.src = src;
  });
}

function runWorker(
  imageData: ImageData,
  options: Required<RemoveBackgroundOptions>,
): Promise<Uint8ClampedArray> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(getWorkerUrl());
    const timer = window.setTimeout(() => {
      worker.terminate();
      reject(new Error("Background removal timed out"));
    }, options.timeout);

    worker.onmessage = (event: MessageEvent) => {
      window.clearTimeout(timer);
      worker.terminate();
      resolve(new Uint8ClampedArray(event.data.buffer));
    };
    worker.onerror = (event) => {
      window.clearTimeout(timer);
      worker.terminate();
      reject(new Error(event.message || "Background removal worker failed"));
    };

    const buffer = imageData.data.buffer.slice(0);
    worker.postMessage(
      {
        buffer,
        width: imageData.width,
        height: imageData.height,
        threshold: options.threshold,
        featherRadius: options.featherRadius,
        targetColor: options.targetColor,
      },
      [buffer],
    );
  });
}

/**
 * 画像が既に意味のある透過（アルファ）を持つかを判定する。
 * V5モデルはtransparent background指示で透過PNGをネイティブ生成するため、
 * その画像をworkerへ通すと透過が破壊される。既に透過を持つ画像は
 * 背景除去をスキップして原本をそのまま使う（4.5/V5混在履歴も画像単位で判定できる）。
 */
export function hasMeaningfulAlpha(
  data: Uint8ClampedArray,
  sampleStep = 16,
): boolean {
  let transparentSamples = 0;
  let totalSamples = 0;
  for (let i = 3; i < data.length; i += 4 * sampleStep) {
    totalSamples += 1;
    if (data[i] < 250) transparentSamples += 1;
  }
  if (totalSamples === 0) return false;
  return transparentSamples / totalSamples > 0.005;
}

async function process(
  src: string,
  options: Required<RemoveBackgroundOptions>,
): Promise<string> {
  const image = await loadImage(src);
  if (image.naturalWidth === 0 || image.naturalHeight === 0) {
    throw new Error("Invalid image dimensions");
  }
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D context is unavailable");
  context.drawImage(image, 0, 0);
  const imageData = context.getImageData(0, 0, canvas.width, canvas.height);

  // 既に透過を持つ画像（V5のネイティブ透過等）は原本をそのまま返す
  if (hasMeaningfulAlpha(imageData.data)) {
    return src;
  }

  const processed = await runWorker(imageData, options);
  const output = context.createImageData(canvas.width, canvas.height);
  output.data.set(processed);
  context.putImageData(output, 0, 0);

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/png"),
  );
  if (!blob) throw new Error("Failed to encode transparent image");
  return URL.createObjectURL(blob);
}

export interface TransparentImageHandle {
  /** Resolves to the transparent object URL, or to `src` itself when the image already has alpha. */
  url: Promise<string>;
  /** Drops this consumer's hold. Calling it more than once is a no-op. */
  release: () => void;
}

interface CacheEntry {
  url: Promise<string>;
  /** Consumers currently displaying the URL. Held entries are never evicted. */
  refs: number;
}

type BackgroundProcessor = (
  src: string,
  options: Required<RemoveBackgroundOptions>,
) => Promise<string>;

function resolveOptions(
  options: RemoveBackgroundOptions,
): Required<RemoveBackgroundOptions> {
  return {
    targetColor:
      options.targetColor === undefined
        ? DEFAULT_OPTIONS.targetColor
        : options.targetColor,
    threshold: options.threshold ?? DEFAULT_OPTIONS.threshold,
    featherRadius: options.featherRadius ?? DEFAULT_OPTIONS.featherRadius,
    timeout: options.timeout ?? DEFAULT_OPTIONS.timeout,
  };
}

function cacheKey(
  src: string,
  options: Required<RemoveBackgroundOptions>,
): string {
  return [
    src,
    options.threshold,
    options.featherRadius,
    options.targetColor
      ? `${options.targetColor.r},${options.targetColor.g},${options.targetColor.b}`
      : "auto",
  ].join("|");
}

function revokeIfObjectUrl(url: string): void {
  if (url.startsWith("blob:")) URL.revokeObjectURL(url);
}

/**
 * Memoizes processed URLs per source + option set.
 *
 * Evicting an entry revokes its object URL. The browser re-fetches that URL
 * when the user picks "Save image as..." or follows an <a download> link, and
 * a revoked blob URL fails there as a network error even though the <img>
 * keeps showing the decoded bitmap. Entries are therefore only evicted while
 * no consumer holds them; the cache may temporarily exceed `limit` when
 * everything in it is on screen.
 */
export function createTransparentImageCache(
  processor: BackgroundProcessor,
  limit: number,
) {
  const entries = new Map<string, CacheEntry>();

  /** Drops unheld entries (oldest first) until the cache fits, keeping the newcomer. */
  function trim(newestKey: string): void {
    for (const [key, entry] of entries) {
      if (entries.size <= limit) return;
      if (entry.refs > 0 || key === newestKey) continue;
      entries.delete(key);
      void entry.url.then(revokeIfObjectUrl).catch(() => {});
    }
  }

  function lookup(src: string, options: RemoveBackgroundOptions): CacheEntry {
    const resolved = resolveOptions(options);
    const key = cacheKey(src, resolved);
    const existing = entries.get(key);
    if (existing) return existing;

    const entry: CacheEntry = {
      refs: 0,
      url: processor(src, resolved).catch((error) => {
        // Failed results are not memoized so the next request retries.
        if (entries.get(key) === entry) entries.delete(key);
        throw error;
      }),
    };
    entries.set(key, entry);
    trim(key);
    return entry;
  }

  return {
    /** Returns the processed URL and keeps it alive until `release` is called. */
    retain(
      src: string,
      options: RemoveBackgroundOptions = {},
    ): TransparentImageHandle {
      const entry = lookup(src, options);
      entry.refs += 1;
      let released = false;
      return {
        url: entry.url,
        release: () => {
          if (released) return;
          released = true;
          entry.refs -= 1;
        },
      };
    },
    /** Returns the processed URL without holding it; a later eviction may revoke it. */
    resolve(
      src: string,
      options: RemoveBackgroundOptions = {},
    ): Promise<string> {
      return lookup(src, options).url;
    },
    get size(): number {
      return entries.size;
    },
  };
}

// Entries still on screen are held by useTransparentImage and survive
// eviction, so this only bounds the number of off-screen results kept around.
const CACHE_LIMIT = 48;

const defaultCache = createTransparentImageCache(process, CACHE_LIMIT);

/**
 * Returns an object URL of `src` with its outer background made transparent
 * and holds it for the caller. Release the handle once the URL leaves the
 * screen so the cache can reclaim it.
 */
export function retainTransparentImage(
  src: string,
  options: RemoveBackgroundOptions = {},
): TransparentImageHandle {
  return defaultCache.retain(src, options);
}

/**
 * Returns an object URL of `src` with its outer background made transparent.
 * The result is not held; prefer `retainTransparentImage` when it is displayed.
 */
export function removeImageBackground(
  src: string,
  options: RemoveBackgroundOptions = {},
): Promise<string> {
  return defaultCache.resolve(src, options);
}
