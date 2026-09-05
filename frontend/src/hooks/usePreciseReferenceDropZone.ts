import { useCallback, useRef, useState } from "react";
import { usePreciseReferenceFiles } from "./usePreciseReferenceFiles";

/**
 * 右パネルの精密参照ドロップゾーン。クリック選択(hidden input)と
 * ドラッグ＆ドロップの両方を受け、検証エラーを表示用に持つ。
 * ドラッグ中の判定は子要素の enter/leave を深さで数えて揺れを防ぐ。
 */
export function usePreciseReferenceDropZone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  // 検証・追加は画面全体ドロップ(GamePlayScreen)と共通のフックに委譲
  const { addFiles: addPreciseReferenceFiles } = usePreciseReferenceFiles();
  const addFiles = useCallback(
    async (files: File[]) => {
      setError(null);
      const { error: nextError } = await addPreciseReferenceFiles(files);
      setError(nextError);
    },
    [addPreciseReferenceFiles],
  );

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;
      void addFiles(Array.from(files));
      e.target.value = "";
    },
    [addFiles],
  );

  const onDragEnter = useCallback((e: React.DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    dragDepthRef.current += 1;
    setDragging(true);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setDragging(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLButtonElement>) => {
      e.preventDefault();
      dragDepthRef.current = 0;
      setDragging(false);
      void addFiles(Array.from(e.dataTransfer.files));
    },
    [addFiles],
  );

  const openPicker = useCallback(() => inputRef.current?.click(), []);

  return {
    inputRef,
    error,
    dragging,
    openPicker,
    onFileChange,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
  };
}
