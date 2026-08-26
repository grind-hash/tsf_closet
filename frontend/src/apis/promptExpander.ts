/**
 * Prompt Expander API クライアント
 *
 * バックエンド routes/prompt_expander_router.py のミラー。
 * レスポンスのフィールド名はバックエンドに合わせてスネークケースを許容する。
 */

import type {
  PromptExpanderImageSize,
  PromptExpanderMangaLayout,
  PromptExpanderMangaReadingDirection,
  PromptExpanderMangaTextLanguage,
  PromptExpanderSourceKind,
  PromptExpandMode,
} from "../constants/promptExpander";
import type { AnlasBalance } from "../types";
import { API_BASE } from "../utils/api";
import { parseAnlasUsage } from "./anlas";

// ----------------------------------------------------------------
// 型定義
// ----------------------------------------------------------------

export interface PromptExpanderSettings {
  text_model: string;
  image_model: string;
  image_size: PromptExpanderImageSize;
  i2i_strength: number;
  i2i_noise: number;
  seed: number | null;
  /** 「欄へ復元」でエントリの seed も生成パラメータへ戻すか */
  restore_seed: boolean;
  memory_text: string;
  use_memory: boolean;
  confirm_before_generate: boolean;
  inherit_source_prompts: boolean;
  /** 漫画モード（V5 のコマ割り・吹き出し）。拡張時の LLM 指示にだけ効く */
  manga_mode: boolean;
  /** コマ数（0 = おまかせ） */
  manga_panel_count: number;
  manga_layout: PromptExpanderMangaLayout;
  manga_dialogue: boolean;
  manga_text_language: PromptExpanderMangaTextLanguage;
  manga_sound_effects: boolean;
  manga_reading_direction: PromptExpanderMangaReadingDirection;
  /** 【】が無くても LLM がナレーション枠を足してよいか（記法で書いたものは常に描く） */
  manga_narration: boolean;
}

export type PromptExpanderSettingsPatch = Partial<PromptExpanderSettings>;

/** 拡張リクエストに載せる漫画モードの詳細 */
export interface PromptExpanderMangaOptions {
  panel_count: number;
  layout: PromptExpanderMangaLayout;
  dialogue: boolean;
  text_language: PromptExpanderMangaTextLanguage;
  sound_effects: boolean;
  reading_direction: PromptExpanderMangaReadingDirection;
  narration: boolean;
}

export interface PromptExpanderTextModelOption {
  id: string;
  label: string;
}

export interface PromptExpanderSettingsResponse {
  settings: PromptExpanderSettings;
  text_model_options: PromptExpanderTextModelOption[];
  image_model_options: string[];
  max_character_prompts: Record<string, number>;
  image_sizes: PromptExpanderImageSize[];
  novelai_configured: boolean;
}

export interface PromptExpanderSession {
  id: string;
  title: string;
  entry_count: number;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
}

export type PromptExpanderEntryKind = "generated" | "uploaded";
export type PromptExpanderEntryExpandMode = "off" | PromptExpandMode;

export interface PromptExpanderEntry {
  id: string;
  session_id: string;
  kind: PromptExpanderEntryKind;
  instruction: string | null;
  positive_expand_mode: PromptExpanderEntryExpandMode;
  negative_expand_mode: PromptExpanderEntryExpandMode;
  character_mode: boolean;
  final_prompt: string;
  final_negative_prompt: string;
  character_prompts: string[];
  image_model: string | null;
  text_model: string | null;
  seed: number | null;
  i2i_strength: number | null;
  i2i_noise: number | null;
  image_size: PromptExpanderImageSize | null;
  manga_mode: boolean;
  /** 漫画モードで指定したコマ数（null = おまかせ／非漫画） */
  manga_panel_count: number | null;
  source_kind: PromptExpanderSourceKind;
  source_history_id: string | null;
  source_entry_id: string | null;
  /** "/prompt-expander/images/{id}" 形式。表示時は promptExpanderImageUrl で API_BASE を付ける */
  image_url: string;
  nsfw: boolean | null;
  created_at: string;
}

export interface PromptExpanderSessionDetailResponse {
  session: PromptExpanderSession;
  entries: PromptExpanderEntry[];
}

export interface PromptExpanderEntriesResponse {
  items: PromptExpanderEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface PromptExpandRequest {
  instruction: string;
  expand_positive?: boolean;
  positive_mode: PromptExpandMode;
  character_mode: boolean;
  expand_negative: boolean;
  negative_mode: PromptExpandMode;
  negative_instruction?: string;
  image_model: string;
  text_model: string;
  language: "ja" | "en";
  source_kind: PromptExpanderSourceKind;
  source_history_id?: string;
  source_entry_id?: string;
  inherit_source_prompts: boolean;
  current_prompt?: string;
  current_character_prompts: string[];
  current_negative?: string;
  manga_mode?: boolean;
  manga?: PromptExpanderMangaOptions;
}

export interface PromptExpandResponse {
  positive_prompt: string | null;
  character_prompts: string[] | null;
  negative_prompt: string | null;
  text_model: string;
}

export interface PromptExpanderGenerateRequest {
  prompt: string;
  negative_prompt?: string;
  character_prompts: string[];
  character_mode: boolean;
  instruction?: string | null;
  positive_expand_mode: PromptExpanderEntryExpandMode;
  negative_expand_mode: PromptExpanderEntryExpandMode;
  image_model: string;
  text_model?: string;
  image_size: PromptExpanderImageSize;
  seed?: number;
  i2i_strength?: number;
  i2i_noise?: number;
  source_kind: PromptExpanderSourceKind;
  source_history_id?: string;
  source_entry_id?: string;
  /** source_kind="upload" のときに必須（base64 または data URL） */
  source_image?: string;
  manga_mode?: boolean;
  manga_panel_count?: number | null;
}

interface AnlasPayload {
  fixed_anlas: number | null;
  purchased_anlas: number | null;
  total_anlas: number | null;
  usage?: {
    percent: number;
    is_negative?: boolean;
    time_until_next_percent?: number;
  } | null;
}

interface PromptExpanderGenerateRawResponse {
  entry: PromptExpanderEntry;
  anlas: AnlasPayload | null;
}

export interface PromptExpanderGenerateResponse {
  entry: PromptExpanderEntry;
  anlas: AnlasBalance | null;
}

export interface PromptExpanderSuggestRequest {
  text_model: string;
  image_model: string;
  mode: PromptExpandMode;
  count: number;
  language: "ja" | "en";
  /** 入力欄の下書き。メモリに加えて提案の方向付けに使う（空なら送らない） */
  input_text?: string;
}

export interface PromptExpanderSuggestion {
  title: string;
  prompt: string;
}

export interface PromptExpanderSuggestResponse {
  suggestions: PromptExpanderSuggestion[];
  text_model: string;
}

// ----------------------------------------------------------------
// 共通
// ----------------------------------------------------------------

/** エラーコード付きの API エラー（detail.code を保持する） */
export class PromptExpanderApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "PromptExpanderApiError";
    this.status = status;
    this.code = code;
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
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

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new PromptExpanderApiError(
      extractErrorMessage(payload, response.statusText || "Request failed"),
      response.status,
      extractErrorCode(payload),
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

const BASE = `${API_BASE}/prompt-expander`;

/** エントリ画像 URL（相対パス）に API_BASE を付けて返す */
export function promptExpanderImageUrl(
  entryOrUrl: PromptExpanderEntry | string,
): string {
  const url =
    typeof entryOrUrl === "string" ? entryOrUrl : entryOrUrl.image_url;
  if (!url) return "";
  if (
    url.startsWith("data:") ||
    url.startsWith("blob:") ||
    url.startsWith("http://") ||
    url.startsWith("https://") ||
    url.startsWith(`${API_BASE}/`)
  ) {
    return url;
  }
  return url.startsWith("/") ? `${API_BASE}${url}` : `${API_BASE}/${url}`;
}

// ----------------------------------------------------------------
// 設定
// ----------------------------------------------------------------

export async function fetchPromptExpanderSettings(): Promise<PromptExpanderSettingsResponse> {
  return requestJson<PromptExpanderSettingsResponse>(`${BASE}/settings`);
}

export async function updatePromptExpanderSettings(
  patch: PromptExpanderSettingsPatch,
): Promise<PromptExpanderSettingsResponse> {
  return requestJson<PromptExpanderSettingsResponse>(
    `${BASE}/settings`,
    jsonInit("PUT", patch),
  );
}

// ----------------------------------------------------------------
// セッション
// ----------------------------------------------------------------

export async function fetchPromptExpanderSessions(): Promise<
  PromptExpanderSession[]
> {
  const payload = await requestJson<{ sessions: PromptExpanderSession[] }>(
    `${BASE}/sessions`,
  );
  return payload.sessions;
}

export async function createPromptExpanderSession(
  title?: string,
): Promise<PromptExpanderSession> {
  return requestJson<PromptExpanderSession>(
    `${BASE}/sessions`,
    jsonInit("POST", title ? { title } : {}),
  );
}

export async function renamePromptExpanderSession(
  id: string,
  title: string,
): Promise<PromptExpanderSession> {
  return requestJson<PromptExpanderSession>(
    `${BASE}/sessions/${encodeURIComponent(id)}`,
    jsonInit("PATCH", { title }),
  );
}

export async function deletePromptExpanderSession(id: string): Promise<void> {
  await requestJson<void>(`${BASE}/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function fetchPromptExpanderSession(
  id: string,
): Promise<PromptExpanderSessionDetailResponse> {
  return requestJson<PromptExpanderSessionDetailResponse>(
    `${BASE}/sessions/${encodeURIComponent(id)}`,
  );
}

// ----------------------------------------------------------------
// エントリ
// ----------------------------------------------------------------

export async function fetchPromptExpanderEntries(
  page: number = 1,
  pageSize: number = 24,
): Promise<PromptExpanderEntriesResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return requestJson<PromptExpanderEntriesResponse>(
    `${BASE}/entries?${params}`,
  );
}

export async function fetchPromptExpanderEntry(
  id: string,
): Promise<PromptExpanderEntry> {
  return requestJson<PromptExpanderEntry>(
    `${BASE}/entries/${encodeURIComponent(id)}`,
  );
}

export async function deletePromptExpanderEntry(id: string): Promise<void> {
  await requestJson<void>(`${BASE}/entries/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function uploadPromptExpanderImage(
  sessionId: string,
  imageBase64: string,
  instruction?: string,
): Promise<PromptExpanderEntry> {
  const body: { image: string; instruction?: string } = { image: imageBase64 };
  if (instruction?.trim()) {
    body.instruction = instruction.trim();
  }
  return requestJson<PromptExpanderEntry>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/uploads`,
    jsonInit("POST", body),
  );
}

// ----------------------------------------------------------------
// 拡張 / 生成 / 提案
// ----------------------------------------------------------------

export async function expandPrompt(
  req: PromptExpandRequest,
): Promise<PromptExpandResponse> {
  return requestJson<PromptExpandResponse>(
    `${BASE}/expand`,
    jsonInit("POST", req),
  );
}

function convertAnlas(payload: AnlasPayload | null): AnlasBalance | null {
  if (
    !payload ||
    payload.fixed_anlas === null ||
    payload.purchased_anlas === null ||
    payload.total_anlas === null
  ) {
    return null;
  }
  return {
    fixedAnlas: payload.fixed_anlas,
    purchasedAnlas: payload.purchased_anlas,
    totalAnlas: payload.total_anlas,
    usage: parseAnlasUsage(payload.usage),
  };
}

export async function generatePromptExpanderImage(
  sessionId: string,
  req: PromptExpanderGenerateRequest,
): Promise<PromptExpanderGenerateResponse> {
  const payload = await requestJson<PromptExpanderGenerateRawResponse>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/generate`,
    jsonInit("POST", req),
  );
  return {
    entry: payload.entry,
    anlas: convertAnlas(payload.anlas),
  };
}

export async function suggestCharacterPrompts(
  req: PromptExpanderSuggestRequest,
): Promise<PromptExpanderSuggestResponse> {
  return requestJson<PromptExpanderSuggestResponse>(
    `${BASE}/suggest-characters`,
    jsonInit("POST", req),
  );
}
