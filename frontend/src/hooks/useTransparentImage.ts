import { useEffect, useState } from "react";
import {
  type RemoveBackgroundOptions,
  retainTransparentImage,
} from "../utils/imageAlpha";

interface TransparentImageResult {
  /** Processed URL. Keeps the previous result while a new source is processed. */
  url: string | null;
  processing: boolean;
}

/**
 * Strips the flat background of `src` (white by default) and returns a
 * transparent object URL. Falls back to the original source on failure.
 *
 * The URL is held for as long as the component uses it: a revoked blob URL
 * still renders in <img>, but "Save image as..." re-fetches it and fails.
 */
export function useTransparentImage(
  src: string | null | undefined,
  enabled = true,
  options?: RemoveBackgroundOptions,
): TransparentImageResult {
  const [url, setUrl] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const threshold = options?.threshold;
  const featherRadius = options?.featherRadius;

  useEffect(() => {
    if (!src) {
      setUrl(null);
      setProcessing(false);
      return;
    }
    if (!enabled) {
      setUrl(src);
      setProcessing(false);
      return;
    }

    let cancelled = false;
    setProcessing(true);

    const handle = retainTransparentImage(src, { threshold, featherRadius });
    handle.url
      .then((processedUrl) => {
        if (!cancelled) setUrl(processedUrl);
      })
      .catch((error) => {
        console.warn("Background removal failed, using original image", error);
        if (!cancelled) setUrl(src);
      })
      .finally(() => {
        if (!cancelled) setProcessing(false);
      });

    return () => {
      cancelled = true;
      handle.release();
    };
  }, [src, enabled, threshold, featherRadius]);

  return { url, processing };
}
