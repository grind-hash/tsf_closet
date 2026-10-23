/**
 * お気に入りプロンプトの表示順と、ドラッグ＆ドロップによる移動の計算。
 *
 * 表示順は「未分類 → カテゴリーの並び順」で、各グループの中は sort_order 順。
 */

import type {
  FavoritePrompt,
  FavoritePromptCategory,
  FavoritePromptPlacement,
} from "../apis/favoritePrompts";

export interface FavoritePromptGroups {
  uncategorized: FavoritePrompt[];
  byCategory: Map<string, FavoritePrompt[]>;
}

/** ドロップ先 */
export interface FavoritePromptDropTarget {
  /** null は未分類 */
  categoryId: string | null;
  /** この ID のプロンプトの直前へ入れる。null ならグループの末尾 */
  beforeId: string | null;
}

/**
 * prompts は sort_order 順で渡す。存在しないカテゴリーを指すものは未分類として扱う。
 */
export function groupFavoritePrompts(
  prompts: FavoritePrompt[],
  categories: FavoritePromptCategory[],
): FavoritePromptGroups {
  const known = new Set(categories.map((c) => c.id));
  const byCategory = new Map<string, FavoritePrompt[]>();
  const uncategorized: FavoritePrompt[] = [];
  for (const prompt of prompts) {
    if (prompt.category_id && known.has(prompt.category_id)) {
      const list = byCategory.get(prompt.category_id) ?? [];
      list.push(prompt);
      byCategory.set(prompt.category_id, list);
    } else {
      uncategorized.push(prompt);
    }
  }
  return { uncategorized, byCategory };
}

function toPlacements(
  groups: Map<string | null, string[]>,
): FavoritePromptPlacement[] {
  const placements: FavoritePromptPlacement[] = [];
  for (const [categoryId, ids] of groups) {
    for (const id of ids) placements.push({ id, category_id: categoryId });
  }
  return placements;
}

/**
 * promptId を target へ移したあとの全体の並びを返す。並びが変わらないとき、
 * または対象が見つからないときは null。
 */
export function moveFavoritePrompt(
  prompts: FavoritePrompt[],
  categories: FavoritePromptCategory[],
  promptId: string,
  target: FavoritePromptDropTarget,
): FavoritePromptPlacement[] | null {
  const { uncategorized, byCategory } = groupFavoritePrompts(
    prompts,
    categories,
  );
  const groups = new Map<string | null, string[]>();
  groups.set(
    null,
    uncategorized.map((p) => p.id),
  );
  for (const category of categories) {
    groups.set(
      category.id,
      (byCategory.get(category.id) ?? []).map((p) => p.id),
    );
  }

  const before = toPlacements(groups);
  const source = [...groups.values()].find((ids) => ids.includes(promptId));
  const destination = groups.get(target.categoryId);
  if (!source || !destination || target.beforeId === promptId) return null;

  source.splice(source.indexOf(promptId), 1);
  const index =
    target.beforeId === null ? -1 : destination.indexOf(target.beforeId);
  destination.splice(index >= 0 ? index : destination.length, 0, promptId);

  const after = toPlacements(groups);
  const unchanged = after.every(
    (p, i) => p.id === before[i].id && p.category_id === before[i].category_id,
  );
  return unchanged ? null : after;
}
