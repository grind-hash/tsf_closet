import { type KeyboardEvent, useRef, useState } from "react";

interface UseAttributeInputOptions {
  addAttribute: (text: string) => Promise<void>;
  removeAttribute: (id: string) => Promise<void>;
}

/**
 * 属性の追加・編集・削除の入力状態。右パネルと人物パネルで同じ挙動を共有する。
 * 編集中は「元の属性を削除してから新しい文言を追加」で置き換える。
 */
export function useAttributeInput({
  addAttribute,
  removeAttribute,
}: UseAttributeInputOptions) {
  const [showInput, setShowInput] = useState(false);
  const [text, setText] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
        await removeAttribute(editingId);
      }
      await addAttribute(text.trim());
      setText("");
      setEditingId(null);
      setShowInput(false);
    } catch (error) {
      console.error("Failed to add attribute:", error);
    } finally {
      setIsAdding(false);
    }
  };

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
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void submit();
    } else if (e.key === "Escape") {
      cancel();
    }
  };

  return {
    showInput,
    setShowInput,
    text,
    setText,
    isAdding,
    editingId,
    setEditingId,
    inputRef,
    submit,
    remove,
    beginEdit,
    onKeyDown,
    cancel,
  };
}
