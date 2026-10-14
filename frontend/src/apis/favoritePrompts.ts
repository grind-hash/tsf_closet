/**
 * お気に入りプロンプト API
 *
 * TSF Closet の DB にだけ保存する。NovelAI のプロンプトチャンクとは同期しない。
 */

import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

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
