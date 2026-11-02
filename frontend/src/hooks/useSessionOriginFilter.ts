import { useCallback, useState } from "react";
import type { GallerySessionOrigin } from "../apis/gallery";

// 画面を閉じて開き直したときに直前の絞り込みへ戻す(アプリを開いている間だけ。永続化はしない)
const lastSelections = new Map<string, GallerySessionOrigin>();

/**
 * セッション一覧の絞り込み(すべて / 通常プレイ / サロン経営)の選択。
 * scope ごとに、同じアプリ起動中の直前の選択を復元する。
 */
export function useSessionOriginFilter(
  scope: string,
): [GallerySessionOrigin, (origin: GallerySessionOrigin) => void] {
  const [origin, setOriginState] = useState<GallerySessionOrigin>(
    () => lastSelections.get(scope) ?? "all",
  );
  const setOrigin = useCallback(
    (next: GallerySessionOrigin) => {
      lastSelections.set(scope, next);
      setOriginState(next);
    },
    [scope],
  );
  return [origin, setOrigin];
}
