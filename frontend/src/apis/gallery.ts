/**
 * Gallery API functions
 * 007-chat-interactive-ux
 */

import type { GalleryItem } from "../types";
import { API_BASE } from "../utils/api";

// レスポンス型
interface GalleryListResponse {
  items: GalleryItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

interface GalleryDetailResponse {
  item: GalleryItem;
  prev_id: string | null;
  next_id: string | null;
}

/**
 * ギャラリー一覧を取得
 */
export async function fetchGalleryList(
  page: number = 1,
  pageSize: number = 20,
  sessionId?: string,
): Promise<GalleryListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  if (sessionId) {
    params.append("session_id", sessionId);
  }

  const response = await fetch(`${API_BASE}/gallery?${params}`);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "ギャラリーの取得に失敗しました");
  }

  const data = await response.json();

  // スネークケース→キャメルケース変換
  return {
    items: data.items.map(convertGalleryItem),
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    has_more: data.has_more,
  };
}

/**
 * ギャラリーアイテムの詳細を取得
 */
export async function fetchGalleryItem(
  itemId: string,
): Promise<GalleryDetailResponse> {
  const response = await fetch(`${API_BASE}/gallery/${itemId}`);

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("アイテムが見つかりません");
    }
    const error = await response.text();
    throw new Error(error || "アイテムの取得に失敗しました");
  }

  const data = await response.json();

  return {
    item: convertGalleryItem(data.item),
    prev_id: data.prev_id,
    next_id: data.next_id,
  };
}

/**
 * APIレスポンスをフロントエンド型に変換
 */
function convertGalleryItem(item: Record<string, unknown>): GalleryItem {
  return {
    id: String(item.id),
    session_id: String(item.session_id || ""),
    image_url: String(item.image_url || ""),
    instruction: String(item.instruction || ""),
    feeling_text: item.feeling_text ? String(item.feeling_text) : null,
    before_description: item.before_description
      ? String(item.before_description)
      : null,
    after_description: item.after_description
      ? String(item.after_description)
      : null,
    timestamp: String(item.timestamp || new Date().toISOString()),
    costume_category: item.costume_category
      ? String(item.costume_category)
      : null,
    exposure_level: item.exposure_level ? String(item.exposure_level) : null,
  };
}
