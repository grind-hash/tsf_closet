import { API_BASE } from "../utils/api";

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

interface ApiErrorResponse {
  detail?: unknown;
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = (await res.json()) as ApiErrorResponse;
      if (data?.detail) {
        message = String(data.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export async function getAivisStatus(): Promise<AivisStatus> {
  const res = await fetch(`${API_BASE}/aivisspeech/status`);
  return parseJsonOrThrow<AivisStatus>(res);
}

export async function getAivisDefaults(): Promise<{
  engine_download_url: string;
  model_download_url: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/defaults`);
  return parseJsonOrThrow<{
    engine_download_url: string;
    model_download_url: string;
  }>(res);
}

export async function downloadAivisEngine(payload: DownloadPayload): Promise<{
  path: string;
  size: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/download-engine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ path: string; size: string }>(res);
}

export async function extractAivisEngine(payload: ExtractPayload): Promise<{
  destination: string;
  run_exe: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/extract-engine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ destination: string; run_exe: string }>(res);
}

export async function startAivisEngine(payload: StartPayload): Promise<{
  status: string;
  pid?: number;
  run_exe?: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/start-engine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ status: string; pid?: number; run_exe?: string }>(
    res,
  );
}

export async function restartAivisEngine(payload: StartPayload): Promise<{
  status: string;
  pid?: number;
  run_exe?: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/restart-engine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ status: string; pid?: number; run_exe?: string }>(
    res,
  );
}

export async function stopAivisEngine(): Promise<{
  status: string;
  pid?: number;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/stop-engine`, {
    method: "POST",
  });
  return parseJsonOrThrow<{ status: string; pid?: number }>(res);
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

export async function downloadAivisModel(payload: DownloadPayload): Promise<{
  path: string;
  size: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/download-model`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ path: string; size: string }>(res);
}

export async function installAivisModel(payload: InstallModelPayload): Promise<{
  status: string;
}> {
  const res = await fetch(`${API_BASE}/aivisspeech/install-model`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<{ status: string }>(res);
}

export async function getAivisSpeakers(): Promise<AivisSpeaker[]> {
  const res = await fetch(`${API_BASE}/aivisspeech/speakers`);
  return parseJsonOrThrow<AivisSpeaker[]>(res);
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
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        message = String(data.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return res.blob();
}
