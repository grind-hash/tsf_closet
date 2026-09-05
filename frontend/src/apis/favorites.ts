/**
 * お気に入り衣装スナップショット API (spec 009)
 */

import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

export interface FavoriteItem {
  id: string;
  history_id: string;
  session_id: string;
  label: string | null;
  image_url: string;
  instruction: string;
  costume_category: string | null;
  history_created_at: string | null;
  created_at: string;
}

export interface FavoriteListResponse {
  items: FavoriteItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

function convertFavoriteItem(item: Record<string, unknown>): FavoriteItem {
  return {
    id: String(item.id),
    history_id: String(item.history_id || ""),
    session_id: String(item.session_id || ""),
    label: item.label != null && item.label !== "" ? String(item.label) : null,
    image_url: String(item.image_url || ""),
    instruction: String(item.instruction || ""),
    costume_category:
      item.costume_category != null ? String(item.costume_category) : null,
    history_created_at:
      item.history_created_at != null ? String(item.history_created_at) : null,
    created_at: String(item.created_at || new Date().toISOString()),
  };
}

export async function fetchFavorites(
  page: number = 1,
  pageSize: number = 20,
): Promise<FavoriteListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const data = await requestJson<Record<string, unknown>>(
    `${API_BASE}/favorites?${params}`,
    undefined,
    { fallbackMessage: "お気に入り一覧の取得に失敗しました" },
  );
  return {
    items: ((data.items as Record<string, unknown>[] | undefined) || []).map(
      (item) => convertFavoriteItem(item),
    ),
    total: Number(data.total || 0),
    page: Number(data.page || page),
    page_size: Number(data.page_size || pageSize),
    has_more: Boolean(data.has_more),
  };
}

export async function addFavorite(
  historyId: string,
  label?: string,
): Promise<FavoriteItem> {
  const data = await requestJson<Record<string, unknown>>(
    `${API_BASE}/favorites`,
    jsonInit("POST", {
      history_id: historyId,
      ...(label !== undefined ? { label } : {}),
    }),
    { fallbackMessage: "お気に入りの追加に失敗しました" },
  );
  return convertFavoriteItem(data);
}

export async function updateFavoriteLabel(
  favoriteId: string,
  label: string | null,
): Promise<FavoriteItem> {
  const data = await requestJson<Record<string, unknown>>(
    `${API_BASE}/favorites/${encodeURIComponent(favoriteId)}`,
    jsonInit("PATCH", { label }),
    { fallbackMessage: "ラベルの更新に失敗しました" },
  );
  return convertFavoriteItem(data);
}

export async function deleteFavoriteByHistory(
  historyId: string,
): Promise<boolean> {
  const data = await requestJson<{ deleted?: boolean }>(
    `${API_BASE}/favorites/by-history/${encodeURIComponent(historyId)}`,
    { method: "DELETE" },
    { fallbackMessage: "お気に入りの削除に失敗しました" },
  );
  return Boolean(data.deleted);
}

/** お気に入り状態をトグルする。戻り値は新しい isFavorited */
export async function toggleFavorite(
  historyId: string,
  currentlyFavorited: boolean,
): Promise<boolean> {
  if (currentlyFavorited) {
    await deleteFavoriteByHistory(historyId);
    return false;
  }
  await addFavorite(historyId);
  return true;
}
