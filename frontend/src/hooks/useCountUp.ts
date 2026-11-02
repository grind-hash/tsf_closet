import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

export interface CountUpOptions {
  /** 最初に表示する値。省略時は target から始め、値が変わったときだけ数え上げる */
  from?: number;
  durationMs?: number;
  /** 数え始めるまでの待ち時間 */
  delayMs?: number;
}

/**
 * 数字を target まで数え上げた表示値を返す。
 * 動きを減らす設定のときは、すぐ target にする。
 */
export function useCountUp(
  target: number,
  { from, durationMs = 900, delayMs = 0 }: CountUpOptions = {},
): number {
  const reducedMotion = usePrefersReducedMotion();
  const [value, setValue] = useState(() =>
    reducedMotion ? target : (from ?? target),
  );
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    const start = valueRef.current;
    if (reducedMotion || start === target) {
      setValue(target);
      return;
    }
    let frame = 0;
    let began: number | null = null;
    const tick = (now: number) => {
      began ??= now;
      const progress = Math.min(1, (now - began) / durationMs);
      const eased = 1 - (1 - progress) ** 3;
      setValue(Math.round(start + (target - start) * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    const timer = window.setTimeout(() => {
      frame = requestAnimationFrame(tick);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(frame);
    };
  }, [target, reducedMotion, durationMs, delayMs]);

  return value;
}
