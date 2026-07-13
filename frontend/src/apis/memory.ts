/**
 * Memory API functions
 *
 * Manages the batch memory-generation job (start/status/cancel) and the
 * memory text (user preference/kink summary) CRUD used by the settings panel.
 */

import { API_BASE } from "../utils/api";

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
  const response = await fetch(`${API_BASE}/memory/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_limit: sessionLimit,
      regenerate_existing: regenerateExisting,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to start memory generation: ${detail}`);
  }
  return response.json();
}

/**
 * メモリ生成バッチジョブの進捗を取得する
 */
export async function getMemoryGenerationStatus(
  jobId: string,
): Promise<MemoryJobStatus> {
  const response = await fetch(`${API_BASE}/memory/generate/status/${jobId}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to fetch job status: ${detail}`);
  }
  return response.json();
}

/**
 * チャンク別のLLM分析用データをMarkdownとして保存する
 */
export async function downloadMemoryAnalysis(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/memory/generate/export/${jobId}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to download analysis data: ${detail}`);
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
  const response = await fetch(`${API_BASE}/memory/generate/cancel/${jobId}`, {
    method: "POST",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to cancel memory generation: ${detail}`);
  }
}

/**
 * 保存済みのメモリテキストを取得する
 */
export async function getMemoryText(): Promise<string | null> {
  const response = await fetch(`${API_BASE}/memory/text`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to fetch memory text: ${detail}`);
  }
  const data = await response.json();
  return data.memory_text ?? null;
}

/**
 * メモリテキストを保存する（手動編集を含む）
 */
export async function saveMemoryText(memoryText: string): Promise<string> {
  const response = await fetch(`${API_BASE}/memory/text`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ memory_text: memoryText }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to save memory text: ${detail}`);
  }
  const data = await response.json();
  return data.memory_text ?? "";
}

/**
 * メモリ生成対象となりうるセッション総数を取得する（推定時間表示用）
 */
export async function getSessionTotalCount(): Promise<number> {
  const response = await fetch(
    `${API_BASE}/gallery/sessions?page=1&page_size=1`,
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to fetch session count: ${detail}`);
  }
  const data = await response.json();
  return data.total ?? 0;
}
