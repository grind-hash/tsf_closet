import { useEffect, useState } from "react";
import { fetchGallerySession } from "../apis/gallery";
import type { GallerySession } from "../types";

/**
 * セッション ID から、一覧用の情報(名前・枚数・開始日)を1件取得する。
 * 一覧の読み込み範囲によらず引ける。ID が空・取得中・見つからないときは null
 */
export function useGallerySessionInfo(
  sessionId: string | null | undefined,
): GallerySession | null {
  const [loaded, setLoaded] = useState<{
    sessionId: string;
    session: GallerySession | null;
  } | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    fetchGallerySession(sessionId)
      .then((session) => {
        if (!cancelled) setLoaded({ sessionId, session });
      })
      .catch((caught: unknown) => {
        console.warn("Failed to load gallery session info:", caught);
        if (!cancelled) setLoaded({ sessionId, session: null });
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return sessionId && loaded?.sessionId === sessionId ? loaded.session : null;
}
