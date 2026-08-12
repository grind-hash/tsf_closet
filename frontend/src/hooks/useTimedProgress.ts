import { useEffect, useMemo, useRef, useState } from "react";

export interface TimedProgressSegment {
  key: string;
  budgetMs: number;
}

const UPDATE_INTERVAL_MS = 100;
// 完了イベントが届くまでセグメントを満了させない上限
const SEGMENT_CEILING = 0.95;

/**
 * 実進捗が取得できない処理向けの時間ベース進捗値（0..1）を返す。
 *
 * segments の budgetMs を見なし所要時間として、アクティブなセグメント内は
 * 指数関数で上限へ漸近させる。activeKey が次のセグメントへ進むと、
 * それまでのセグメント分は満額としてスナップする。
 * segments または activeKey が null の間は 0 を返して停止する。
 */
export function useTimedProgress(
  segments: TimedProgressSegment[] | null,
  activeKey: string | null,
): number {
  const [progress, setProgress] = useState(0);
  const segmentStartRef = useRef(0);
  const lastKeyRef = useRef<string | null>(null);

  const active = useMemo(() => {
    if (!segments || segments.length === 0 || !activeKey) return null;
    const index = segments.findIndex((segment) => segment.key === activeKey);
    if (index < 0) return null;
    return { index, segments };
  }, [segments, activeKey]);

  useEffect(() => {
    if (!active) {
      lastKeyRef.current = null;
      setProgress(0);
      return;
    }
    if (lastKeyRef.current !== activeKey) {
      lastKeyRef.current = activeKey;
      segmentStartRef.current = performance.now();
    }
    const { index, segments: list } = active;
    const totalBudget = list.reduce((sum, item) => sum + item.budgetMs, 0);
    if (totalBudget <= 0) {
      setProgress(0);
      return;
    }
    const doneBudget = list
      .slice(0, index)
      .reduce((sum, item) => sum + item.budgetMs, 0);
    const budget = list[index].budgetMs;
    const update = () => {
      const elapsed = performance.now() - segmentStartRef.current;
      const within =
        SEGMENT_CEILING * (1 - Math.exp(-elapsed / (budget * 0.4)));
      setProgress((doneBudget + within * budget) / totalBudget);
    };
    update();
    const timer = window.setInterval(update, UPDATE_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [active, activeKey]);

  return progress;
}
