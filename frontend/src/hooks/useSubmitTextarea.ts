import { type KeyboardEvent, useLayoutEffect, useRef } from "react";

interface UseSubmitTextareaOptions {
  value: string;
  /** Enter で送信してよいか(空欄・送信中は false) */
  canSubmit: boolean;
  onSubmit: () => void;
}

/**
 * 送信欄の複数行入力(textarea)。内容に合わせて高さを伸縮し(上限は CSS の
 * max-height、超えた分は欄の中でスクロール)、Enter で送信・Shift+Enter で改行にする。
 * 変換中の Enter は確定に使い、タッチ端末(pointer: coarse)では通常プレイの
 * 入力欄と同じく Enter を改行にする。
 */
export function useSubmitTextarea({
  value,
  canSubmit,
  onSubmit,
}: UseSubmitTextareaOptions) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // 音声入力や送信後のクリアで値が変わったときも高さを合わせる
  useLayoutEffect(() => {
    const field = ref.current;
    if (!field) return;
    // value の変更をトリガーに高さを再計算する
    void value;
    field.style.height = "auto";
    // 隠している間(display: none)は測れないため、1 行の高さのままにする
    if (field.scrollHeight === 0) return;
    // box-sizing: border-box なので、内容の高さに上下の枠線を足す
    field.style.height = `${field.scrollHeight + field.offsetHeight - field.clientHeight}px`;
  }, [value]);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing ||
      !window.matchMedia("(pointer: fine)").matches
    ) {
      return;
    }
    event.preventDefault();
    if (canSubmit) onSubmit();
  };

  return { ref, onKeyDown };
}
