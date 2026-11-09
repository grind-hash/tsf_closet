import { useEffect, useMemo, useState } from "react";
import {
  type RemoveBackgroundOptions,
  retainTransparentImage,
} from "../utils/imageAlpha";

/**
 * 複数の画像の単色背景を抜き、元の URL -> 透過済み URL の対応を返す。
 *
 * 既にアルファを持つ画像(V5 の透過生成や同梱素材)はそのまま返る。処理中や失敗時は
 * 元の URL を使う。表示に使っている間は透過済みの URL を保持し、外れたら手放す。
 */
export function useTransparentImages(
  sources: (string | null | undefined)[],
  options?: RemoveBackgroundOptions,
): Record<string, string> {
  const key = useMemo(
    () =>
      [...new Set(sources.filter((src): src is string => Boolean(src)))]
        .sort()
        .join("\n"),
    [sources],
  );
  const [processed, setProcessed] = useState<Record<string, string>>({});
  const threshold = options?.threshold;
  const featherRadius = options?.featherRadius;
  const targetColor = options?.targetColor;

  useEffect(() => {
    const unique = key ? key.split("\n") : [];
    let cancelled = false;
    const handles = unique.map((src) => {
      const handle = retainTransparentImage(src, {
        targetColor,
        threshold,
        featherRadius,
      });
      handle.url
        .then((url) => {
          if (!cancelled) {
            setProcessed((current) =>
              current[src] === url ? current : { ...current, [src]: url },
            );
          }
        })
        .catch((error) => {
          console.warn(
            "Background removal failed, using original image",
            error,
          );
          if (!cancelled) {
            setProcessed((current) =>
              current[src] === src ? current : { ...current, [src]: src },
            );
          }
        });
      return handle;
    });
    // 一覧から外れた画像の対応は消す(保持も手放す)
    setProcessed((current) => {
      const next: Record<string, string> = {};
      for (const src of unique) {
        if (current[src]) next[src] = current[src];
      }
      return next;
    });
    return () => {
      cancelled = true;
      for (const handle of handles) handle.release();
    };
  }, [key, targetColor, threshold, featherRadius]);

  return processed;
}
