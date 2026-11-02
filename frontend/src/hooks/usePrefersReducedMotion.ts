import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function canMatch(): boolean {
  return (
    typeof window !== "undefined" && typeof window.matchMedia === "function"
  );
}

function subscribe(onChange: () => void): () => void {
  if (!canMatch()) return () => {};
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return canMatch() && window.matchMedia(QUERY).matches;
}

/** OS の「視差効果を減らす」(prefers-reduced-motion: reduce)を購読する */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
