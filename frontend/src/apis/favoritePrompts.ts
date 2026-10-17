/**
 * お気に入りプロンプト API
 *
 * TSF Closet の DB にだけ保存する。NovelAI のプロンプトチャンクとは同期しない。
 */

import { API_BASE } from "../utils/api";
import { downloadBlob } from "../utils/exportChat";
import { apiErrorFromResponse, jsonInit, requestJson } from "../utils/http";

export interface FavoritePrompt {
  id: string;
  category_id: string | null;
  label: string;
  content: string;
  color: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface FavoritePromptCategory {
  id: string;
  label: string;
  color: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface FavoritePromptList {
  categories: FavoritePromptCategory[];
  prompts: FavoritePrompt[];
}

export interface FavoritePromptInput {
  label: string;
  content: string;
  color: string;
  category_id: string | null;
}

export interface FavoritePromptCategoryInput {
  label: string;
  color: string;
}

/** インポート / エクスポートのファイル形式（CSV は Excel 等で編集する人向け） */
export type FavoritePromptFileFormat = "csv" | "json";

/** CSV の列見出しの言語 */
export type FavoritePromptCsvLanguage = "ja" | "en";

/** 上書き対象（カテゴリーは名前で照合する。null は未分類） */
export interface FavoritePromptImportTarget {
  category: string | null;
  label: string;
}

export interface FavoritePromptImportPreview {
  create_count: number;
  overwrites: FavoritePromptImportTarget[];
  new_categories: string[];
}

/** 取り込み結果と、取り込み後の一覧 */
export interface FavoritePromptImportResult
  extends FavoritePromptImportPreview,
    FavoritePromptList {}

const BASE = `${API_BASE}/favorite-prompts`;

export async function fetchFavoritePrompts(): Promise<FavoritePromptList> {
  const data = await requestJson<Partial<FavoritePromptList>>(BASE, undefined, {
    fallbackMessage: "お気に入りプロンプトの取得に失敗しました",
  });
  return {
    categories: data.categories ?? [],
    prompts: data.prompts ?? [],
  };
}

export function createFavoritePrompt(
  input: FavoritePromptInput,
): Promise<FavoritePrompt> {
  return requestJson<FavoritePrompt>(BASE, jsonInit("POST", input), {
    fallbackMessage: "お気に入りプロンプトの保存に失敗しました",
  });
}

/** 渡した項目だけを更新する（category_id: null で未分類へ移動） */
export function updateFavoritePrompt(
  promptId: string,
  changes: Partial<FavoritePromptInput>,
): Promise<FavoritePrompt> {
  return requestJson<FavoritePrompt>(
    `${BASE}/${encodeURIComponent(promptId)}`,
    jsonInit("PATCH", changes),
    { fallbackMessage: "お気に入りプロンプトの更新に失敗しました" },
  );
}

export async function deleteFavoritePrompt(promptId: string): Promise<void> {
  await requestJson<unknown>(
    `${BASE}/${encodeURIComponent(promptId)}`,
    { method: "DELETE" },
    { fallbackMessage: "お気に入りプロンプトの削除に失敗しました" },
  );
}

export function createFavoritePromptCategory(
  input: FavoritePromptCategoryInput,
): Promise<FavoritePromptCategory> {
  return requestJson<FavoritePromptCategory>(
    `${BASE}/categories`,
    jsonInit("POST", input),
    { fallbackMessage: "カテゴリーの保存に失敗しました" },
  );
}

export function updateFavoritePromptCategory(
  categoryId: string,
  changes: Partial<FavoritePromptCategoryInput>,
): Promise<FavoritePromptCategory> {
  return requestJson<FavoritePromptCategory>(
    `${BASE}/categories/${encodeURIComponent(categoryId)}`,
    jsonInit("PATCH", changes),
    { fallbackMessage: "カテゴリーの更新に失敗しました" },
  );
}

/** カテゴリーを削除する。中のプロンプトはバックエンドで未分類へ移る */
export async function deleteFavoritePromptCategory(
  categoryId: string,
): Promise<void> {
  await requestJson<unknown>(
    `${BASE}/categories/${encodeURIComponent(categoryId)}`,
    { method: "DELETE" },
    { fallbackMessage: "カテゴリーの削除に失敗しました" },
  );
}

function exportFileName(format: FavoritePromptFileFormat): string {
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("");
  return `tsf-closet-favorite-prompts-${date}.${format}`;
}

/** すべてのお気に入りプロンプトとカテゴリーをファイルとして保存する */
export async function exportFavoritePrompts(
  format: FavoritePromptFileFormat,
  language: FavoritePromptCsvLanguage,
): Promise<void> {
  const params = new URLSearchParams({ format, lang: language });
  const response = await fetch(`${BASE}/export?${params.toString()}`);
  if (!response.ok) {
    throw await apiErrorFromResponse(
      response,
      "お気に入りプロンプトの書き出しに失敗しました",
    );
  }
  downloadBlob(await response.blob(), exportFileName(format));
}

/**
 * ファイルをそのまま送る（文字コードや CSV / JSON の判別はバックエンドで行う）。
 * Content-Type はブラウザが multipart 境界付きで設定するため明示しない。
 */
function fileInit(file: File): RequestInit {
  const form = new FormData();
  form.append("file", file, file.name);
  return { method: "POST", body: form };
}

/** 書き込まずに、追加・上書きされる内容を確認する */
export function previewFavoritePromptImport(
  file: File,
): Promise<FavoritePromptImportPreview> {
  return requestJson<FavoritePromptImportPreview>(
    `${BASE}/import/preview`,
    fileInit(file),
    { fallbackMessage: "ファイルを読み込めませんでした" },
  );
}

/** 同じカテゴリー・同じ名前のものは上書きし、無いカテゴリーは作成する */
export function importFavoritePrompts(
  file: File,
): Promise<FavoritePromptImportResult> {
  return requestJson<FavoritePromptImportResult>(
    `${BASE}/import`,
    fileInit(file),
    { fallbackMessage: "ファイルを読み込めませんでした" },
  );
}
