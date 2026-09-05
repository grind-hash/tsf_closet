/**
 * Memory API functions
 *
 * Manages the batch memory-generation job (start/status/cancel) and the
 * memory text (user preference/kink summary) CRUD used by the settings panel.
 */

import { API_BASE } from "../utils/api";
import { apiErrorFromResponse, jsonInit, requestJson } from "../utils/http";

export interface MemoryJobStatus {
  job_id: string;
  status:
    | "running"
    | "completed"
    | "completed_with_errors"
    | "failed"
    | "cancelled";
  phase: "summarizing" | "analyzing" | "merging" | "done";
  total: number;
  processed: number;
  current_session_id: string | null;
  memory_chunk_total: number;
  memory_chunk_processed: number;
  errors: string[];
  regenerate_existing: boolean;
  started_at: string;
  finished_at: string | null;
}

/**
 * メモリ生成バッチジョブを開始する
 */
export async function startMemoryGeneration(
  sessionLimit: number | null,
  regenerateExisting: boolean,
): Promise<{ job_id: string }> {
  return requestJson<{ job_id: string }>(
    `${API_BASE}/memory/generate`,
    jsonInit("POST", {
      session_limit: sessionLimit,
      regenerate_existing: regenerateExisting,
    }),
    { fallbackMessage: "Failed to start memory generation" },
  );
}

/**
 * メモリ生成バッチジョブの進捗を取得する
 */
export async function getMemoryGenerationStatus(
  jobId: string,
): Promise<MemoryJobStatus> {
  return requestJson<MemoryJobStatus>(
    `${API_BASE}/memory/generate/status/${jobId}`,
    undefined,
    { fallbackMessage: "Failed to fetch job status" },
  );
}

/**
 * チャンク別のLLM分析用データをMarkdownとして保存する
 */
export async function downloadMemoryAnalysis(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/memory/generate/export/${jobId}`);
  if (!response.ok) {
    throw await apiErrorFromResponse(
      response,
      "Failed to download analysis data",
    );
  }

  const disposition = response.headers.get("Content-Disposition");
  const filenameMatch = disposition?.match(/filename="?([^";]+)"?/i);
  const filename =
    filenameMatch?.[1] ?? `memory-analysis-${jobId.slice(0, 8)}.md`;
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;

  try {
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }
}

/**
 * メモリ生成バッチジョブのキャンセルを要求する
 */
export async function cancelMemoryGeneration(jobId: string): Promise<void> {
  await requestJson<unknown>(
    `${API_BASE}/memory/generate/cancel/${jobId}`,
    { method: "POST" },
    { fallbackMessage: "Failed to cancel memory generation" },
  );
}

/**
 * 保存済みのメモリテキストを取得する
 */
export async function getMemoryText(): Promise<string | null> {
  const data = await requestJson<{ memory_text?: string | null }>(
    `${API_BASE}/memory/text`,
    undefined,
    { fallbackMessage: "Failed to fetch memory text" },
  );
  return data.memory_text ?? null;
}

/**
 * メモリテキストを保存する（手動編集を含む）
 */
export async function saveMemoryText(memoryText: string): Promise<string> {
  const data = await requestJson<{ memory_text?: string | null }>(
    `${API_BASE}/memory/text`,
    jsonInit("PUT", { memory_text: memoryText }),
    { fallbackMessage: "Failed to save memory text" },
  );
  return data.memory_text ?? "";
}

/**
 * メモリ生成対象となりうるセッション総数を取得する（推定時間表示用）
 */
export async function getSessionTotalCount(): Promise<number> {
  const data = await requestJson<{ total?: number }>(
    `${API_BASE}/gallery/sessions?page=1&page_size=1`,
    undefined,
    { fallbackMessage: "Failed to fetch session count" },
  );
  return data.total ?? 0;
}
