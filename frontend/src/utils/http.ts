/**
 * バックエンド API 呼び出しの共通処理。
 *
 * - `requestJson`: fetch + JSON 取得。非 2xx は `ApiError` を投げる（204 は undefined）
 * - `ApiError`: FastAPI の `detail`（文字列 / `{message, code}` / バリデーション配列）を
 *   message と code に展開したエラー。UI 側は `instanceof ApiError` と `code` で分岐する
 * - `jsonInit`: JSON ボディ付きの RequestInit
 * - `apiErrorFromResponse`: blob / ストリームなど JSON 以外の応答を扱う関数から使う
 *
 * `apis/*` はすべてここを経由し、各モジュールでエラー解釈を再実装しない。
 */

/** エラーコード付きの API エラー（detail.code を保持する） */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** FastAPI のエラー応答から表示用メッセージを取り出す */
export function extractErrorMessage(
  payload: unknown,
  fallback: string,
): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
      const nested = (detail as { detail?: unknown }).detail;
      if (typeof nested === "string") return nested;
      // FastAPI のバリデーションエラー（配列）はそのまま文字列化する
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

/** FastAPI のエラー応答から detail.code を取り出す */
export function extractErrorCode(payload: unknown): string | null {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      const code = (detail as { code?: unknown }).code;
      return typeof code === "string" ? code : null;
    }
  }
  return null;
}

/** 非 2xx の Response を ApiError に変換する（本文は JSON として読み、失敗しても落とさない） */
export async function apiErrorFromResponse(
  response: Response,
  fallbackMessage?: string,
): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null);
  return new ApiError(
    extractErrorMessage(
      payload,
      fallbackMessage ?? (response.statusText || "Request failed"),
    ),
    response.status,
    extractErrorCode(payload),
  );
}

export interface RequestJsonOptions {
  /** detail が無い応答に使うメッセージ（既定は statusText） */
  fallbackMessage?: string;
}

/** fetch して JSON を返す。非 2xx は ApiError、204 は undefined */
export async function requestJson<T>(
  url: string,
  init?: RequestInit,
  options?: RequestJsonOptions,
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw await apiErrorFromResponse(response, options?.fallbackMessage);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** JSON ボディ付きの RequestInit（body 省略時はヘッダーだけ） */
export function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}
