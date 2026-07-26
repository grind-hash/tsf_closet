/**
 * useInfiniteScroll - スクロール末尾検知で追加読み込みを発火する
 * IntersectionObserver を使用（root はスクロールコンテナを指定）
 */

import { type RefObject, useEffect, useRef } from "react";

export interface UseInfiniteScrollOptions {
  /** 監視を有効にするか（hasMore && !isLoading 等） */
  enabled: boolean;
  /** 末尾到達時に呼ぶ追加読み込み */
  onLoadMore: () => void;
  /** スクロールコンテナ。null の間は監視しない */
  root: Element | null;
  /** 先読み余白。例: "200px 0px" */
  rootMargin?: string;
  threshold?: number;
}

/**
 * @returns リスト末尾に置く sentinel 要素への ref
 */
export function useInfiniteScroll({
  enabled,
  onLoadMore,
  root,
  rootMargin = "200px 0px",
  threshold = 0,
}: UseInfiniteScrollOptions): RefObject<HTMLDivElement | null> {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const onLoadMoreRef = useRef(onLoadMore);

  useEffect(() => {
    onLoadMoreRef.current = onLoadMore;
  }, [onLoadMore]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!enabled || !root || !sentinel) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          onLoadMoreRef.current();
        }
      },
      {
        root,
        rootMargin,
        threshold,
      },
    );

    observer.observe(sentinel);

    return () => {
      observer.disconnect();
    };
  }, [enabled, root, rootMargin, threshold]);

  return sentinelRef;
}
