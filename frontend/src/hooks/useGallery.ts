/**
 * useGallery - ギャラリーフック
 * 007-chat-interactive-ux
 */

import { useCallback, useEffect, useState } from "react";
import { fetchGalleryItem, fetchGalleryList } from "../apis/gallery";
import type { GalleryItem } from "../types";

interface UseGalleryOptions {
  pageSize?: number;
  sessionId?: string;
  autoFetch?: boolean;
}

interface UseGalleryReturn {
  items: GalleryItem[];
  isLoading: boolean;
  error: string | null;
  total: number;
  page: number;
  hasMore: boolean;
  fetchPage: (pageNum: number) => Promise<void>;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  getItem: (itemId: string) => Promise<{
    item: GalleryItem;
    prevId: string | null;
    nextId: string | null;
  } | null>;
}

export function useGallery(options: UseGalleryOptions = {}): UseGalleryReturn {
  const { pageSize = 20, sessionId, autoFetch = true } = options;

  const [items, setItems] = useState<GalleryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  // 指定ページを取得
  const fetchPage = useCallback(
    async (pageNum: number) => {
      try {
        setIsLoading(true);
        setError(null);

        const response = await fetchGalleryList(pageNum, pageSize, sessionId);

        setItems((prev) =>
          pageNum === 1 ? response.items : [...prev, ...response.items],
        );
        setTotal(response.total);
        setPage(pageNum);
        setHasMore(response.has_more);
      } catch (err) {
        setError(err instanceof Error ? err.message : "取得に失敗しました");
      } finally {
        setIsLoading(false);
      }
    },
    [pageSize, sessionId],
  );

  // 追加読み込み
  const loadMore = useCallback(async () => {
    if (!isLoading && hasMore) {
      await fetchPage(page + 1);
    }
  }, [isLoading, hasMore, page, fetchPage]);

  // リフレッシュ
  const refresh = useCallback(async () => {
    setItems([]);
    await fetchPage(1);
  }, [fetchPage]);

  // 個別アイテム取得
  const getItem = useCallback(async (itemId: string) => {
    try {
      const response = await fetchGalleryItem(itemId);
      return {
        item: response.item,
        prevId: response.prev_id,
        nextId: response.next_id,
      };
    } catch (err) {
      console.error("Failed to fetch gallery item:", err);
      return null;
    }
  }, []);

  // 初回自動取得
  useEffect(() => {
    if (autoFetch) {
      fetchPage(1);
    }
  }, [autoFetch, fetchPage]);

  return {
    items,
    isLoading,
    error,
    total,
    page,
    hasMore,
    fetchPage,
    loadMore,
    refresh,
    getItem,
  };
}
