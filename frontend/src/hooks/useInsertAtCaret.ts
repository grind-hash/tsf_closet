import { type RefObject, useCallback } from "react";
import { insertPromptText } from "../utils/insertPromptText";

/**
 * 入力欄のキャレット位置へ文字列を差し込むコールバックを返す。
 *
 * 挿入後は欄へフォーカスを戻し、差し込んだ文字列の直後にキャレットを置く。
 * 一度もキャレットを置いていない欄（選択位置が先頭のまま）では末尾に追記する。
 */
export function useInsertAtCaret(
  ref: RefObject<HTMLTextAreaElement | HTMLInputElement | null>,
  value: string,
  setValue: (next: string) => void,
  separator = ", ",
): (insert: string) => void {
  return useCallback(
    (insert: string) => {
      const el = ref.current;
      let start = el?.selectionStart ?? value.length;
      let end = el?.selectionEnd ?? value.length;
      if (start === 0 && end === 0) {
        start = value.length;
        end = value.length;
      }
      const { text, caret } = insertPromptText(
        value,
        insert,
        start,
        end,
        separator,
      );
      setValue(text);
      requestAnimationFrame(() => {
        const target = ref.current;
        if (!target) return;
        target.focus();
        target.setSelectionRange(caret, caret);
      });
    },
    [ref, value, setValue, separator],
  );
}
