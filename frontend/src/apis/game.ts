/**
 * Game API functions
 * プロンプトプレビュー・最新履歴削除など
 */

import type { Character, InstructionType } from "../types";
import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

// プロンプトプレビュー リクエスト
export interface PreviewPromptRequest {
  session_id: string;
  instruction: string;
  transformation_type?: string;
  instruction_type?: InstructionType | string;
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
  return requestJson<PreviewPromptResponse>(
    `${API_BASE}/game/preview/prompt`,
    jsonInit("POST", request),
    { fallbackMessage: "Preview failed" },
  );
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
  const data = await requestJson<SuggestInstructionResponse>(
    `${API_BASE}/game/suggest-instruction`,
    jsonInit("POST", {
      session_id: sessionId,
      instruction_type: instructionType === "all" ? null : instructionType,
      keyword: keyword?.trim() ? keyword.trim() : null,
      language,
      use_memory: useMemory ?? false,
      use_play_memory: usePlayMemory ?? false,
    }),
    { fallbackMessage: "Suggest failed" },
  );
  return data.suggestion;
}

/**
 * 最新の履歴エントリを削除する
 */
export async function deleteLatestHistory(
  sessionId: string,
): Promise<DeleteLatestHistoryResponse> {
  return requestJson<DeleteLatestHistoryResponse>(
    `${API_BASE}/game/session/${sessionId}/latest-history`,
    { method: "DELETE" },
    { fallbackMessage: "Delete failed" },
  );
}

export interface StandingPortraitResponse {
  image: string;
  cost_usd: number | null;
}

/**
 * 現在の姿を全身立ち絵として再生成する（履歴には保存されない）
 */
export async function generateStandingPortrait(
  sessionId: string,
  nsfwMode?: boolean,
): Promise<StandingPortraitResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  if (nsfwMode !== undefined) {
    params.set("nsfw_mode", String(nsfwMode));
  }
  return requestJson<StandingPortraitResponse>(
    `${API_BASE}/game/standing-portrait?${params}`,
    { method: "POST" },
    { fallbackMessage: "Standing portrait failed" },
  );
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
  return requestJson<DeleteConversationMessageResponse>(
    `${API_BASE}/game/conversation/message/${encodeURIComponent(conversationId)}?${params}`,
    { method: "DELETE" },
    { fallbackMessage: "Delete conversation message failed" },
  );
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
  return requestJson<DeleteHistoryEntryResponse>(
    `${API_BASE}/game/history/${encodeURIComponent(historyId)}?${params}`,
    { method: "DELETE" },
    { fallbackMessage: "Delete history entry failed" },
  );
}

/** 履歴画像から新規セッション分岐のレスポンス（SessionResponse 互換 + メタ） */
export interface BranchSessionResponse {
  session_id: string;
  character_id?: string | null;
  current_image_url: string;
  transformation_count?: number;
  history?: Array<Record<string, unknown>>;
  stats?: Record<string, unknown> | null;
  attributes?: Array<{ id: string; text?: string; attribute_text?: string }>;
  conversation_history?: Array<Record<string, unknown>>;
  self_mode?: boolean;
  play_memory?: Record<string, unknown>;
  branch_summary?: string;
  source_session_id?: string | null;
  source_history_id?: string | null;
  inherit_stats?: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * 指定履歴の画像状態から新規セッションを分岐開始する。
 * 状況サマリー生成のため待ちが発生しうる。
 */
export async function branchSessionFromHistory(
  historyId: string,
  options?: { inheritStats?: boolean; selfMode?: boolean },
): Promise<BranchSessionResponse> {
  return requestJson<BranchSessionResponse>(
    `${API_BASE}/game/history/${encodeURIComponent(historyId)}/branch-session`,
    jsonInit("POST", {
      inherit_stats: options?.inheritStats ?? true,
      ...(options?.selfMode !== undefined
        ? { self_mode: options.selfMode }
        : {}),
    }),
    { fallbackMessage: "Branch session failed" },
  );
}

// ----------------------------------------------------------------
// セッション / キャラクター / 属性 / プレイメモ（GameContext から使う）
// ----------------------------------------------------------------

/**
 * GET /game/session と POST /game/sessions/{id}/restore の応答。
 * 項目の解釈は GameContext.mapSessionResponse が担う
 */
export type GameSessionResponse = Record<string, unknown> & {
  session_id: string;
};

export interface PlayMemoryApiResponse {
  system_enabled: boolean;
  user_enabled: boolean;
  system_text: string | null;
  user_text: string | null;
  system_updated_at: string | null;
}

export interface PlayMemoryUpdate {
  system_enabled?: boolean;
  user_enabled?: boolean;
  user_text?: string | null;
}

export async function fetchCharacters(): Promise<Character[]> {
  const data = await requestJson<{ characters?: Character[] }>(
    `${API_BASE}/game/characters`,
    undefined,
    { fallbackMessage: "キャラクター一覧の取得に失敗しました" },
  );
  return data.characters ?? [];
}

/** アクティブセッションを取得する（無ければ 404 の ApiError） */
export async function fetchActiveSession(): Promise<GameSessionResponse> {
  return requestJson<GameSessionResponse>(`${API_BASE}/game/session`);
}

export async function restoreSession(
  sessionId: string,
): Promise<GameSessionResponse> {
  return requestJson<GameSessionResponse>(
    `${API_BASE}/game/sessions/${sessionId}/restore`,
    { method: "POST" },
  );
}

/**
 * アクティブセッションを終了する。ローカル状態は応答に関わらず破棄するため、
 * バックエンド側の失敗（非 2xx）は無視し、通信エラーだけを投げる
 */
export async function deleteActiveSession(): Promise<void> {
  await fetch(`${API_BASE}/game/session`, { method: "DELETE" });
}

export async function addSessionAttribute(
  sessionId: string,
  text: string,
): Promise<{
  attribute: { id: string; attribute_text: string; text?: string };
}> {
  const params = new URLSearchParams({
    session_id: sessionId,
    attribute_text: text,
  });
  return requestJson(
    `${API_BASE}/game/attributes?${params.toString()}`,
    { method: "POST" },
    { fallbackMessage: "Failed to add attribute" },
  );
}

export async function removeSessionAttribute(id: string): Promise<void> {
  await requestJson<unknown>(
    `${API_BASE}/game/attributes/${id}`,
    { method: "DELETE" },
    { fallbackMessage: "Failed to remove attribute" },
  );
}

export async function updatePlayMemory(
  sessionId: string,
  updates: PlayMemoryUpdate,
): Promise<PlayMemoryApiResponse> {
  return requestJson<PlayMemoryApiResponse>(
    `${API_BASE}/game/sessions/${sessionId}/play-memory`,
    jsonInit("PATCH", updates),
    { fallbackMessage: "プレイメモの保存に失敗しました" },
  );
}

export async function regeneratePlayMemory(
  sessionId: string,
  language: string,
): Promise<PlayMemoryApiResponse> {
  const params = new URLSearchParams({ language });
  return requestJson<PlayMemoryApiResponse>(
    `${API_BASE}/game/sessions/${sessionId}/play-memory/regenerate?${params}`,
    { method: "POST" },
    { fallbackMessage: "自動メモの再生成に失敗しました" },
  );
}
