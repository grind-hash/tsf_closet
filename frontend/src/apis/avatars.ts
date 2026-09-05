/**
 * VRM アバターモデル API クライアント。
 *
 * バックエンド契約:
 * - GET    /api/avatars              -> { items: AvatarModel[] }
 * - POST   /api/avatars (multipart)  -> 201 AvatarModel
 *   file のほか name / character_name / variant_label / auto_classify(いずれも任意)。
 *   character_name 未指定ならファイル名 ``名前_衣装_….vrm`` から自動分類される
 *   (空のフォーム欄は未指定扱いになるため、未分類で登録するには auto_classify=false)
 *   エラーは { detail: { code, message } }(invalid_vrm / file_too_large 等)
 * - PATCH  /api/avatars/{id} {name?, character_name?, variant_label?} -> AvatarModel
 *   未指定の項目は据え置き。character_name / variant_label は "" で解除
 * - POST   /api/avatars/auto-classify -> { updated, updated_ids, items }
 *   未設定の項目だけをモデル名の規則で埋める(設定済みの分類は変えない)
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
  /** 同じキャラクターの衣装差分をまとめるグループ名。未分類は null */
  character_name: string | null;
  /** グループ内での差分の説明(「水着 髪束ねたVer」など)。無ければ null */
  variant_label: string | null;
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
    character_name: stringOrNull(model.character_name)?.trim() || null,
    variant_label: stringOrNull(model.variant_label)?.trim() || null,
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

export interface AvatarUploadOptions {
  name?: string;
  /** 未指定ならファイル名から自動分類。"" を渡すと未分類で登録する */
  characterName?: string;
  variantLabel?: string;
}

/**
 * VRM ファイルをアップロードする。Content-Type はブラウザが multipart 境界
 * 付きで設定するため明示しない。
 */
export async function uploadAvatarModel(
  file: File,
  options: AvatarUploadOptions = {},
): Promise<AvatarModel> {
  const form = new FormData();
  form.append("file", file, file.name);
  const trimmed = options.name?.trim();
  if (trimmed) form.append("name", trimmed);
  if (options.characterName !== undefined) {
    // 空文字は FastAPI で未指定に落ちるため、自動分類を止めて未分類にする
    form.append("character_name", options.characterName.trim());
    form.append("auto_classify", "false");
  }
  if (options.variantLabel !== undefined) {
    form.append("variant_label", options.variantLabel.trim());
  }
  const model = await requestJson<AvatarModel>(`${API_BASE}/avatars`, {
    method: "POST",
    body: form,
  });
  return normalizeModel(model);
}

export interface AvatarUpdateRequest {
  name?: string;
  /** "" で未分類に戻す */
  character_name?: string;
  /** "" でラベル無しに戻す */
  variant_label?: string;
}

export async function updateAvatarModel(
  id: string,
  update: AvatarUpdateRequest,
): Promise<AvatarModel> {
  const model = await requestJson<AvatarModel>(
    `${API_BASE}/avatars/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    },
  );
  return normalizeModel(model);
}

export function renameAvatarModel(
  id: string,
  name: string,
): Promise<AvatarModel> {
  return updateAvatarModel(id, { name });
}

export interface AvatarAutoClassifyResult {
  updated: number;
  updated_ids: string[];
  /** 更新後の全モデル */
  items: AvatarModel[];
}

/** 未設定のキャラクター名・差分ラベルだけをモデル名の規則で埋める */
export async function autoClassifyAvatarModels(): Promise<AvatarAutoClassifyResult> {
  const payload = await requestJson<{
    updated?: number;
    updated_ids?: string[];
    items?: AvatarModel[];
  }>(`${API_BASE}/avatars/auto-classify`, { method: "POST" });
  return {
    updated: Number(payload.updated ?? 0),
    updated_ids: payload.updated_ids ?? [],
    items: (payload.items ?? []).map(normalizeModel),
  };
}

/**
 * バックエンド classify_avatar_filename と同じ規則。
 * 「キャラクター名_衣装_髪型Ver」の最初の "_" までをキャラクター名、残り("_" は空白)を
 * 差分ラベルにする。規則に合わなければ null
 */
export function classifyAvatarFilename(
  stem: string,
): { characterName: string; variantLabel: string } | null {
  const match = /^([^_]+)_(.+)$/.exec(stem.trim());
  if (!match) return null;
  const characterName = match[1].trim().replace(/\s+/g, " ");
  const variantLabel = match[2].replace(/_/g, " ").trim().replace(/\s+/g, " ");
  if (!characterName || !variantLabel) return null;
  return { characterName, variantLabel };
}

/** グループ内で差分を区別する表示名。差分ラベルが無ければモデル名 */
export function avatarVariantLabel(model: AvatarModel): string {
  return model.variant_label || model.name;
}

export interface AvatarModelGroup {
  /** null は未分類のグループ */
  character: string | null;
  models: AvatarModel[];
}

/**
 * キャラクター名でまとめる。分類済みグループはキャラクター名順、未分類は末尾
 * (未分類内は API の並び=登録日の新しい順のまま)。グループ内は差分ラベル
 * (無ければ名前)の表示用ソート。LLM に見せる候補の並びはバックエンドの
 * list_avatar_variants が別に決めるため、ここは表示だけの都合でよい。
 */
export function groupAvatarModels(models: AvatarModel[]): AvatarModelGroup[] {
  const byCharacter = new Map<string, AvatarModel[]>();
  const ungrouped: AvatarModel[] = [];
  for (const model of models) {
    if (!model.character_name) {
      ungrouped.push(model);
      continue;
    }
    const bucket = byCharacter.get(model.character_name) ?? [];
    bucket.push(model);
    byCharacter.set(model.character_name, bucket);
  }
  const collator = new Intl.Collator(undefined, { numeric: true });
  const groups: AvatarModelGroup[] = [...byCharacter.entries()]
    .sort(([a], [b]) => collator.compare(a, b))
    .map(([character, items]) => ({
      character,
      models: [...items].sort((a, b) =>
        collator.compare(avatarVariantLabel(a), avatarVariantLabel(b)),
      ),
    }));
  if (ungrouped.length > 0) groups.push({ character: null, models: ungrouped });
  return groups;
}

export async function deleteAvatarModel(id: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/avatars/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!response.ok) await throwApiError(response);
}
