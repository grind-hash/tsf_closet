import { API_BASE } from "../utils/api";
import { apiErrorFromResponse, jsonInit, requestJson } from "../utils/http";

export interface AivisStatus {
  process: string;
  pid: number | null;
  managed?: boolean;
  engine_http: string;
  engine_base_url: string;
  /** 実際に接続しているポート（ユーザー設定 > AIVIS_ENGINE_BASE_URL の順で解決） */
  engine_port: number;
  /** AIVIS_ENGINE_BASE_URL 由来の既定ポート */
  default_engine_port: number;
  engine_version: string | null;
  /** /engine_manifest の brand_name。同梱エンジンの判別だけに使い、画面には出さない */
  engine_brand: string | null;
  /** AivisSpeech 本体を示す brand_name。engine_brand との比較に使う */
  aivis_engine_brand: string;
  default_engine_download_url: string;
  default_model_url: string;
  default_model_dir: string;
  platform: "windows" | "linux" | "other";
  docker_hint?: string;
}

export interface AivisSpeakerStyle {
  id: number;
  name: string;
}

export interface AivisSpeaker {
  name: string;
  speaker_uuid: string;
  styles: AivisSpeakerStyle[];
}

interface DownloadPayload {
  url: string;
  target_dir: string;
}

interface ExtractPayload {
  zip_path: string;
  destination_dir: string;
}

interface StartPayload {
  engine_dir: string;
  use_gpu: boolean;
}

interface InstallModelPayload {
  model_path: string;
}

interface SynthesizePayload {
  text: string;
  speaker_id: string;
}

export async function getAivisStatus(): Promise<AivisStatus> {
  return requestJson<AivisStatus>(`${API_BASE}/aivisspeech/status`);
}

export async function getAivisDefaults(): Promise<{
  engine_download_url: string;
  model_download_url: string;
}> {
  return requestJson<{
    engine_download_url: string;
    model_download_url: string;
  }>(`${API_BASE}/aivisspeech/defaults`);
}

export async function downloadAivisEngine(payload: DownloadPayload): Promise<{
  path: string;
  size: string;
}> {
  return requestJson<{ path: string; size: string }>(
    `${API_BASE}/aivisspeech/download-engine`,
    jsonInit("POST", payload),
  );
}

export async function extractAivisEngine(payload: ExtractPayload): Promise<{
  destination: string;
  run_exe: string;
}> {
  return requestJson<{ destination: string; run_exe: string }>(
    `${API_BASE}/aivisspeech/extract-engine`,
    jsonInit("POST", payload),
  );
}

export async function startAivisEngine(payload: StartPayload): Promise<{
  status: string;
  pid?: number;
  run_exe?: string;
}> {
  return requestJson<{ status: string; pid?: number; run_exe?: string }>(
    `${API_BASE}/aivisspeech/start-engine`,
    jsonInit("POST", payload),
  );
}

export async function restartAivisEngine(payload: StartPayload): Promise<{
  status: string;
  pid?: number;
  run_exe?: string;
}> {
  return requestJson<{ status: string; pid?: number; run_exe?: string }>(
    `${API_BASE}/aivisspeech/restart-engine`,
    jsonInit("POST", payload),
  );
}

export async function stopAivisEngine(): Promise<{
  status: string;
  pid?: number;
}> {
  return requestJson<{ status: string; pid?: number }>(
    `${API_BASE}/aivisspeech/stop-engine`,
    { method: "POST" },
  );
}

/**
 * エンジンが起動していなければ起動する。再生・保存・スピーカー取得などの
 * 実行前に呼び出すことで、エンジン停止時にユーザーが手動で起動し直す手間を省く。
 */
export async function ensureAivisEngineRunning(
  engineDir: string,
  useGpu: boolean,
): Promise<AivisStatus> {
  const status = await getAivisStatus();
  if (status.process === "running" || status.engine_http === "ok") {
    return status;
  }

  if (status.platform === "linux") {
    // Linux環境ではエンジンはDocker Composeで管理するため、アプリからは起動しない。
    throw new Error(
      `AivisSpeech engine is not reachable. Start it with \`${status.docker_hint ?? "docker compose up -d aivis"}\`.`,
    );
  }

  await startAivisEngine({ engine_dir: engineDir, use_gpu: useGpu });
  return getAivisStatus();
}

export async function installAivisModel(payload: InstallModelPayload): Promise<{
  status: string;
}> {
  return requestJson<{ status: string }>(
    `${API_BASE}/aivisspeech/install-model`,
    jsonInit("POST", payload),
  );
}

export async function getAivisSpeakers(): Promise<AivisSpeaker[]> {
  return requestJson<AivisSpeaker[]>(`${API_BASE}/aivisspeech/speakers`);
}

/** 口パク用の口形状イベント。時刻は合成音声の先頭からの秒(メディア時刻) */
export interface VisemeEvent {
  t0: number;
  t1: number;
  viseme: string;
  w: number;
}

/** 合成音声と viseme タイムラインの対 */
export interface TimedSpeech {
  blob: Blob;
  timeline: VisemeEvent[];
  durationSec: number;
}

interface SynthesizeTimedResponse {
  audio_base64: string;
  content_type: string;
  duration_sec: number;
  timeline: VisemeEvent[];
}

/** 音声合成と口パク用タイムラインを同時に取得する(3D モデル表示用) */
export async function synthesizeSpeechTimed(
  payload: SynthesizePayload,
): Promise<TimedSpeech> {
  const data = await requestJson<SynthesizeTimedResponse>(
    `${API_BASE}/aivisspeech/synthesize-timed`,
    jsonInit("POST", payload),
  );
  const binary = atob(data.audio_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return {
    blob: new Blob([bytes], { type: data.content_type || "audio/wav" }),
    timeline: Array.isArray(data.timeline) ? data.timeline : [],
    durationSec: data.duration_sec ?? 0,
  };
}

export async function synthesizeSpeech(
  payload: SynthesizePayload,
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/aivisspeech/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw await apiErrorFromResponse(res);
  }

  return res.blob();
}
