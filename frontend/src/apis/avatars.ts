/**
 * VRM アバターモデル API クライアント。
 *
 * バックエンド契約:
 * - GET    /api/avatars              -> { items: AvatarModel[] }
 * - POST   /api/avatars (multipart)  -> 201 AvatarModel
 *   エラーは { detail: { code, message } }(invalid_vrm / file_too_large 等)
 * - PATCH  /api/avatars/{id} {name}  -> AvatarModel
 * - DELETE /api/avatars/{id}         -> 204
 * - GET    /api/avatars/{id}/file    -> VRM バイナリ
 */

import { API_BASE } from "../utils/api";

export interface AvatarModelMeta {
  title: string | null;
  author: string | null;
  license: string | null;
  license_url: string | null;
  allowed_user: string | null;
  commercial: string | null;
}

export interface AvatarModel {
  id: string;
  name: string;
  file_size: number;
  vrm_spec_version: "0" | "1";
  meta: AvatarModelMeta;
  /** API_BASE 適用済みの取得 URL */
  file_url: string;
  created_at: string | null;
}

export class AvatarApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "AvatarApiError";
    this.status = status;
    this.code = code;
  }
}

export function avatarModelFileUrl(id: string): string {
  return `${API_BASE}/avatars/${encodeURIComponent(id)}/file`;
}

function withApiBase(url: string): string {
  if (url.startsWith(`${API_BASE}/`)) return url;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function normalizeMeta(meta: unknown): AvatarModelMeta {
  const source =
    meta && typeof meta === "object" ? (meta as Record<string, unknown>) : {};
  return {
    title: stringOrNull(source.title),
    author: stringOrNull(source.author),
    license: stringOrNull(source.license),
    license_url: stringOrNull(source.license_url),
    allowed_user: stringOrNull(source.allowed_user),
    commercial: stringOrNull(source.commercial),
  };
}

function normalizeModel(model: AvatarModel): AvatarModel {
  return {
    ...model,
    file_size: Number(model.file_size ?? 0),
    vrm_spec_version: model.vrm_spec_version === "1" ? "1" : "0",
    meta: normalizeMeta(model.meta),
    file_url: model.file_url
      ? withApiBase(model.file_url)
      : avatarModelFileUrl(model.id),
    created_at: model.created_at ?? null,
  };
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
      // FastAPI のバリデーションエラー(配列)はそのまま文字列化する
      if (Array.isArray(detail)) {
        const msgs = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : null,
          )
          .filter((m): m is string => Boolean(m));
        if (msgs.length > 0) return msgs.join(" / ");
      }
    }
  }
  return fallback;
}

function extractErrorCode(payload: unknown): string | null {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      const code = (detail as { code?: unknown }).code;
      return typeof code === "string" ? code : null;
    }
  }
  return null;
}

async function throwApiError(response: Response): Promise<never> {
  const payload: unknown = await response.json().catch(() => null);
  throw new AvatarApiError(
    extractErrorMessage(payload, response.statusText || "Request failed"),
    response.status,
    extractErrorCode(payload),
  );
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) return throwApiError(response);
  return (await response.json()) as T;
}

export async function listAvatarModels(): Promise<AvatarModel[]> {
  const payload = await requestJson<{ items?: AvatarModel[] }>(
    `${API_BASE}/avatars`,
  );
  return (payload.items ?? []).map(normalizeModel);
}

/**
 * VRM ファイルをアップロードする。Content-Type はブラウザが multipart 境界
 * 付きで設定するため明示しない。
 */
export async function uploadAvatarModel(
  file: File,
  name?: string,
): Promise<AvatarModel> {
  const form = new FormData();
  form.append("file", file, file.name);
  const trimmed = name?.trim();
  if (trimmed) form.append("name", trimmed);
  const model = await requestJson<AvatarModel>(`${API_BASE}/avatars`, {
    method: "POST",
    body: form,
  });
  return normalizeModel(model);
}

export async function renameAvatarModel(
  id: string,
  name: string,
): Promise<AvatarModel> {
  const model = await requestJson<AvatarModel>(
    `${API_BASE}/avatars/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
  );
  return normalizeModel(model);
}

export async function deleteAvatarModel(id: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/avatars/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!response.ok) await throwApiError(response);
}
