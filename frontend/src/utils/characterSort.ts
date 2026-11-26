/**
 * キャラクター(キャラクターメイク)一覧の並び順。
 * 一覧画面と各選択モーダルのキャラクタータブで同じ並び順を使う。
 * バックエンドは名前の昇順で返すため、並べ替えはフロントエンドで行う。
 */

import type { CharacterPreset } from "../types";

export const CHARACTER_SORT_ORDERS = [
  "created_desc",
  "created_asc",
  "name_asc",
  "name_desc",
] as const;

export type CharacterSortOrder = (typeof CHARACTER_SORT_ORDERS)[number];

/** 作ったばかりのキャラクターが先頭に来るよう、作成日の新しい順を既定にする */
export const DEFAULT_CHARACTER_SORT_ORDER: CharacterSortOrder = "created_desc";

export function isCharacterSortOrder(
  value: unknown,
): value is CharacterSortOrder {
  return (
    typeof value === "string" &&
    (CHARACTER_SORT_ORDERS as readonly string[]).includes(value)
  );
}

type SortablePreset = Pick<CharacterPreset, "id" | "name" | "created_at">;

function createdTime(preset: SortablePreset): number {
  const time = Date.parse(preset.created_at);
  return Number.isNaN(time) ? 0 : time;
}

/** 並び順に従って並べ替えた新しい配列を返す(元の配列は変更しない)。同順位は id で決める */
export function sortCharacterPresets<T extends SortablePreset>(
  presets: readonly T[],
  order: CharacterSortOrder,
  locale: string,
): T[] {
  const collator = new Intl.Collator(locale, {
    numeric: true,
    sensitivity: "base",
  });
  const byId = (a: T, b: T) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const compare = (a: T, b: T): number => {
    switch (order) {
      case "created_desc":
        return createdTime(b) - createdTime(a);
      case "created_asc":
        return createdTime(a) - createdTime(b);
      case "name_asc":
        return collator.compare(a.name, b.name);
      case "name_desc":
        return collator.compare(b.name, a.name);
    }
  };
  return [...presets].sort((a, b) => compare(a, b) || byId(a, b));
}
