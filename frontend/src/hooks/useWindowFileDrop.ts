/**
 * useWindowFileDrop - 画面全体（window）へのファイルのドラッグ＆ドロップ検知
 *
 * ファイルを含むドラッグのときだけ反応し、ドラッグ中かどうかを返す（オーバーレイ表示用）。
 * drop は window で受けるので、画面内のどこへ落としても onFiles に届く。
 * 画面内の個別ドロップゾーン（React の onDrop で preventDefault 済み）が処理した drop は
 * defaultPrevented で見分けて二重処理しない。
 */

import { useEffect, useRef, useState } from "react";

interface UseWindowFileDropOptions {
  /** false の間はリスナーを外し、ブラウザ既定の挙動に任せる */
  enabled: boolean;
  /** ドロップされたファイル（1 件以上） */
  onFiles: (files: File[]) => void;
}

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

export function useWindowFileDrop({
  enabled,
  onFiles,
}: UseWindowFileDropOptions): boolean {
  const [isDragging, setIsDragging] = useState(false);
  const depthRef = useRef(0);
  const staleTimerRef = useRef<number | null>(null);
  // コールバックが変わってもリスナーを張り直さない（ドラッグ中に状態が消えるのを防ぐ）
  const onFilesRef = useRef(onFiles);
  useEffect(() => {
    onFilesRef.current = onFiles;
  }, [onFiles]);

  useEffect(() => {
    if (!enabled) return;

    const clearStaleTimer = () => {
      if (staleTimerRef.current !== null) {
        window.clearTimeout(staleTimerRef.current);
        staleTimerRef.current = null;
      }
    };
    const hide = () => {
      depthRef.current = 0;
      clearStaleTimer();
      setIsDragging(false);
    };
    // ウィンドウ外へ抜けた際に dragleave が届かない環境向けの保険
    const refreshStaleTimer = () => {
      clearStaleTimer();
      staleTimerRef.current = window.setTimeout(hide, 1000);
    };
    const onDragEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depthRef.current += 1;
      setIsDragging(true);
      refreshStaleTimer();
    };
    const onDragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      refreshStaleTimer();
    };
    const onDragLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depthRef.current = Math.max(0, depthRef.current - 1);
      if (depthRef.current === 0) hide();
    };
    const onDrop = (e: DragEvent) => {
      const handledElsewhere = e.defaultPrevented;
      hide();
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (handledElsewhere) return;
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (files.length === 0) return;
      onFilesRef.current(files);
    };

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragend", hide);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragend", hide);
      hide();
    };
  }, [enabled]);

  return isDragging;
}
