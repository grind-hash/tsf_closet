import {
  type CharacterSortOrder,
  DEFAULT_CHARACTER_SORT_ORDER,
  isCharacterSortOrder,
} from "../utils/characterSort";
import { usePersistedState } from "./usePersistedState";

/** キャラクター一覧の並び順を保持する localStorage のキー(一覧画面と選択モーダルで共有) */
export const CHARACTER_SORT_ORDER_STORAGE_KEY = "character_sort_order";

/**
 * キャラクター一覧の並び順。一覧画面と選択モーダルのキャラクタータブで共有する。
 * 保存値が不正なときは既定(作成日の新しい順)に戻す。
 */
export function useCharacterSortOrder() {
  return usePersistedState<CharacterSortOrder>(
    CHARACTER_SORT_ORDER_STORAGE_KEY,
    DEFAULT_CHARACTER_SORT_ORDER,
    {
      serialize: (value) => value,
      deserialize: (raw) => {
        if (!isCharacterSortOrder(raw)) {
          throw new Error(`invalid character sort order: ${raw}`);
        }
        return raw;
      },
    },
  );
}
