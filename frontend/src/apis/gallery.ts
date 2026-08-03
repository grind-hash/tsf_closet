/**
 * Gallery API functions
 * 007-chat-interactive-ux
 */

import type { GalleryItem, GallerySession } from "../types";
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

interface DeleteItemResponse {
  success: boolean;
  deleted_count: number;
  message: string;
}

export interface GallerySessionsResponse {
  sessions: GallerySession[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

/**
 * ギャラリーのセッション一覧を取得（q 指定時はやり取りを横断検索）
 */
export async function fetchGallerySessions(
  page: number = 1,
  pageSize: number = 20,
  q?: string,
): Promise<GallerySessionsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  const query = q?.trim();
  if (query) {
    params.append("q", query);
  }

  const response = await fetch(`${API_BASE}/gallery/sessions?${params}`);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "セッション一覧の取得に失敗しました");
  }

  return response.json();
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
 * 変身前後比較用に、セッション内の全アイテムを時系列昇順で取得
 * 先頭要素が起点（初期状態）の画像に相当する
 */
export async function fetchSessionFrames(
  sessionId: string,
): Promise<GalleryItem[]> {
  const maxPageSize = 100;
  const items: GalleryItem[] = [];
  let page = 1;
  let hasMore = true;
  while (hasMore) {
    const data = await fetchGalleryList(page, maxPageSize, sessionId);
    items.push(...data.items);
    hasMore = data.has_more;
    page += 1;
  }
  return items.sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
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
    is_favorited: Boolean(item.is_favorited),
  };
}

/**
 * ギャラリーアイテムを個別削除
 */
export async function deleteGalleryItem(
  itemId: string,
): Promise<DeleteItemResponse> {
  const response = await fetch(`${API_BASE}/gallery/${itemId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("アイテムが見つかりません");
    }
    const error = await response.text();
    throw new Error(error || "アイテムの削除に失敗しました");
  }

  return response.json();
}

// Play Summary types
export interface PlaySummaryResponse {
  session_id: string;
  title: string;
  summary: string;
  timeline: Array<{ label: string; type: string }>;
  created_at: string | null;
  updated_at: string | null;
}

/**
 * Get existing play summary for a session
 */
export async function getSessionSummary(
  sessionId: string,
): Promise<PlaySummaryResponse | null> {
  const response = await fetch(
    `${API_BASE}/gallery/sessions/${sessionId}/summary`,
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message || `Failed to fetch summary: ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Generate play summary for a session using LLM
 */
export async function generateSessionSummary(
  sessionId: string,
  language: string = "ja",
): Promise<PlaySummaryResponse> {
  const response = await fetch(
    `${API_BASE}/gallery/sessions/${sessionId}/summary?language=${language}`,
    { method: "POST" },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message ||
        error.detail ||
        `Summary generation failed: ${response.status}`,
    );
  }

  return response.json();
}

// ----------------------------------------------------------------
// Chat history export (Markdown / Novel HTML zip)
// ----------------------------------------------------------------

export interface ExportDownload {
  blob: Blob;
  filename: string;
}

function parseFilenameFromHeaders(headers: Headers, fallback: string): string {
  const cd = headers.get("Content-Disposition");
  if (!cd) return fallback;
  // RFC 5987: filename*=UTF-8''<percent-encoded>
  const starMatch = cd.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (starMatch) {
    try {
      return decodeURIComponent(starMatch[1].trim());
    } catch {
      // fall through to filename=
    }
  }
  const quotedMatch = cd.match(/filename\s*=\s*"([^"]+)"/i);
  if (quotedMatch) return quotedMatch[1];
  const bareMatch = cd.match(/filename\s*=\s*([^;]+)/i);
  if (bareMatch) return bareMatch[1].trim();
  return fallback;
}

export type ExportProgressCallback = (
  loaded: number,
  total: number | null,
) => void;

async function downloadExport(
  url: string,
  fallbackFilename: string,
  onProgress?: ExportProgressCallback,
): Promise<ExportDownload> {
  const response = await fetch(url);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message ||
        error.detail ||
        `Export failed: ${response.status}`,
    );
  }
  const filename = parseFilenameFromHeaders(response.headers, fallbackFilename);

  // 進捗コールバックが無い、またはストリーム読み取りに対応していない場合は通常のblob取得
  if (!onProgress || !response.body) {
    const blob = await response.blob();
    return { blob, filename };
  }

  const contentLengthHeader = response.headers.get("Content-Length");
  const total = contentLengthHeader ? Number(contentLengthHeader) : null;
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      loaded += value.length;
      onProgress(loaded, total);
    }
  }

  const blob = new Blob(chunks as BlobPart[]);
  return { blob, filename };
}

/**
 * Download Markdown export (.md) with base64-embedded images.
 */
export async function exportSessionMarkdown(
  sessionId: string,
  onProgress?: ExportProgressCallback,
): Promise<ExportDownload> {
  return downloadExport(
    `${API_BASE}/gallery/sessions/${sessionId}/export/markdown`,
    `chat_${sessionId.slice(0, 8)}.md`,
    onProgress,
  );
}

/**
 * Download novel-style HTML zip (HTML + CSS + images).
 */
export async function exportSessionNovelHtml(
  sessionId: string,
  onProgress?: ExportProgressCallback,
): Promise<ExportDownload> {
  return downloadExport(
    `${API_BASE}/gallery/sessions/${sessionId}/export/novel-html`,
    `chat_${sessionId.slice(0, 8)}_novel.zip`,
    onProgress,
  );
}
