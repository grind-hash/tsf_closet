/**
 * Game API functions
 * プロンプトプレビュー・最新履歴削除など
 */

import { API_BASE } from "../utils/api";
import type { InstructionType, PreserveElement, ChangeScope } from "../types";

// プロンプトプレビュー リクエスト
export interface PreviewPromptRequest {
  session_id: string;
  instruction: string;
  transformation_type?: string;
  instruction_type?: InstructionType | string;
  preserve_elements?: PreserveElement[];
  change_scope?: ChangeScope;
  custom_preserve_text?: string;
}

// プロンプトプレビュー レスポンス
export interface PreviewPromptResponse {
  image_edit_prompt: string;
  feeling_system_prompt: string;
  feeling_user_prompt: string;
  instruction_type: string;
  novelai_tag_prompt: string | null;
  surroundings_system_prompt?: string;
  surroundings_user_prompt?: string;
}

// 最新履歴削除 レスポンス
export interface DeleteLatestHistoryResponse {
  deleted_history_id: string;
  restored_instruction: string;
  restored_instruction_type: string;
  current_image_path: string | null;
  restored_history_id: string | null;
}

/**
 * プロンプトプレビューを取得する
 */
export async function previewPrompt(
  request: PreviewPromptRequest,
): Promise<PreviewPromptResponse> {
  const response = await fetch(`${API_BASE}/game/preview/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message || `Preview failed: ${response.status}`,
    );
  }

  return response.json();
}

/**
 * 最新の履歴エントリを削除する
 */
export async function deleteLatestHistory(
  sessionId: string,
): Promise<DeleteLatestHistoryResponse> {
  const response = await fetch(
    `${API_BASE}/game/session/${sessionId}/latest-history`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message || `Delete failed: ${response.status}`,
    );
  }

  return response.json();
}

// 会話テキスト削除 レスポンス
export interface DeleteConversationResponse {
  success: boolean;
  deleted_count: number;
  message: string;
}

/**
 * 指定履歴IDに紐づく会話テキストのみを削除する（履歴レコードと画像は保持）
 */
export async function deleteConversation(
  historyId: string,
  sessionId: string,
): Promise<DeleteConversationResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(
    `${API_BASE}/game/conversation/${encodeURIComponent(historyId)}?${params}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message || `Delete conversation failed: ${response.status}`,
    );
  }

  return response.json();
}

export interface DeleteHistoryEntryResponse {
  success: boolean;
  deleted_history_id: string;
  restored_history_id: string;
}

/**
 * 指定履歴IDの履歴エントリを完全削除する（History + 画像 + 会話テキスト）
 */
export async function deleteHistoryEntry(
  historyId: string,
  sessionId: string,
): Promise<DeleteHistoryEntryResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(
    `${API_BASE}/game/history/${encodeURIComponent(historyId)}?${params}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message ||
        `Delete history entry failed: ${response.status}`,
    );
  }

  return response.json();
}
