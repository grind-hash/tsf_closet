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
  use_play_memory?: boolean;
  respect_clothing_layers?: boolean;
  use_history_lookback?: boolean;
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

// spec 004: パラメータ逆適用情報
export interface ParameterRevert {
  stat_name: "bloom" | "shame" | "adaptation";
  delta: number;
  prev_value: number;
  new_value: number;
}

// 最新履歴削除 レスポンス
export interface DeleteLatestHistoryResponse {
  deleted_history_id: string;
  restored_instruction: string;
  restored_instruction_type: string;
  current_image_path: string | null;
  restored_history_id: string | null;
  parameter_reverts?: ParameterRevert[];
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

// 指示テキスト生成 レスポンス
export interface SuggestInstructionResponse {
  suggestion: string;
}

/**
 * 過去のhistory/conversationと現在のセッション状態を踏まえ、
 * 次に送信できる指示テキストをLLMで生成する（送信はしない）
 */
export async function suggestInstruction(
  sessionId: string,
  instructionType: InstructionType | "all",
  language: string,
  keyword?: string,
  useMemory?: boolean,
  usePlayMemory?: boolean,
): Promise<string> {
  const response = await fetch(`${API_BASE}/game/suggest-instruction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      instruction_type: instructionType === "all" ? null : instructionType,
      keyword: keyword?.trim() ? keyword.trim() : null,
      language,
      use_memory: useMemory ?? false,
      use_play_memory: usePlayMemory ?? false,
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Suggest failed: ${response.status}`);
  }

  const data: SuggestInstructionResponse = await response.json();
  return data.suggestion;
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

// 個別会話メッセージ削除 レスポンス
export interface DeleteConversationMessageResponse {
  success: boolean;
  deleted_conversation_id: string;
}

/**
 * 個別の会話メッセージレコードを削除する（画像は無関係）
 */
export async function deleteConversationMessage(
  conversationId: string,
  sessionId: string,
): Promise<DeleteConversationMessageResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  const response = await fetch(
    `${API_BASE}/game/conversation/message/${encodeURIComponent(conversationId)}?${params}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.detail?.message ||
        `Delete conversation message failed: ${response.status}`,
    );
  }

  return response.json();
}

export interface DeleteHistoryEntryResponse {
  success: boolean;
  deleted_history_id: string;
  restored_history_id: string;
  parameter_reverts?: ParameterRevert[];
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
