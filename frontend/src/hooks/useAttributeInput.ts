import { type KeyboardEvent, useState } from "react";
import { useSubmitTextarea } from "./useSubmitTextarea";

interface UseAttributeInputOptions {
  addAttribute: (text: string) => Promise<void>;
  updateAttribute: (id: string, text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
}

/**
 * 属性の追加・編集・削除の入力状態。右パネルと人物パネルで同じ挙動を共有する。
 * 編集は元の属性の文言を置き換える（失敗しても元の属性は消えない）。
 * 入力欄は現実改変ほどの長文も全文見えるよう、内容に合わせて縦に伸びる複数行にする
 * （Enter で確定、Shift+Enter で改行、Escape で取り消し）。
 */
export function useAttributeInput({
  addAttribute,
  updateAttribute,
  removeAttribute,
}: UseAttributeInputOptions) {
  const [showInput, setShowInput] = useState(false);
  const [text, setText] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const cancel = () => {
    setShowInput(false);
    setText("");
    setEditingId(null);
  };

  const submit = async () => {
    if (!text.trim() || isAdding) return;
    setIsAdding(true);
    try {
      if (editingId) {
        await updateAttribute(editingId, text.trim());
      } else {
        await addAttribute(text.trim());
      }
      setText("");
      setEditingId(null);
      setShowInput(false);
    } catch (error) {
      console.error("Failed to save attribute:", error);
    } finally {
      setIsAdding(false);
    }
  };

  const field = useSubmitTextarea({
    value: text,
    canSubmit: text.trim() !== "" && !isAdding,
    onSubmit: () => void submit(),
  });

  const remove = async (id: string) => {
    try {
      await removeAttribute(id);
      if (editingId === id) {
        setEditingId(null);
        setText("");
      }
    } catch (error) {
      console.error("Failed to remove attribute:", error);
    }
  };

  const beginEdit = (id: string, currentText: string) => {
    setEditingId(id);
    setText(currentText);
    setShowInput(true);
    setTimeout(() => field.ref.current?.focus(), 0);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      cancel();
      return;
    }
    field.onKeyDown(e);
  };

  return {
    showInput,
    setShowInput,
    text,
    setText,
    isAdding,
    editingId,
    setEditingId,
    inputRef: field.ref,
    submit,
    remove,
    beginEdit,
    onKeyDown,
    cancel,
  };
}
