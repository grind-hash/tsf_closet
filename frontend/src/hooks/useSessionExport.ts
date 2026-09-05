import { useCallback, useEffect, useRef, useState } from "react";
import { exportSessionMarkdown, exportSessionNovelHtml } from "../apis/gallery";
import type { ChatMessage } from "../types";
import {
  downloadBlob,
  downloadFile,
  type ExportSessionInfo,
  exportAsCsv,
  exportAsJson,
  exportAsMarkdown,
  exportAsNovel,
  exportAsPlainText,
} from "../utils/exportChat";

export type ChatExportFormat =
  | "markdown"
  | "csv"
  | "json"
  | "clipboard"
  | "novel"
  | "markdown_images"
  | "novel_html_zip";

/** 画像同梱エクスポート(Markdown / Novel HTML zip)のダウンロード進捗 */
export interface ChatExportProgress {
  format: "markdown_images" | "novel_html_zip";
  loaded: number;
  total: number | null;
}

interface UseSessionExportOptions {
  messages: ChatMessage[];
  sessionId: string | null;
  characterName: string | undefined;
}

/**
 * チャットのエクスポートメニュー。テキスト系はクライアントで組み立てて
 * ダウンロードし、画像同梱系はバックエンドの zip を進捗付きで取得する。
 */
export function useSessionExport({
  messages,
  sessionId,
  characterName,
}: UseSessionExportOptions) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState<ChatExportProgress | null>(null);

  // メニューの外側クリックで閉じる
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const toggleMenu = useCallback(() => setMenuOpen((prev) => !prev), []);

  const exportAs = useCallback(
    async (format: ChatExportFormat) => {
      const info: ExportSessionInfo = {
        sessionId: sessionId ?? "unknown",
        characterName,
      };
      if (format === "clipboard") {
        const content = exportAsPlainText(messages, info);
        void navigator.clipboard.writeText(content);
        setMenuOpen(false);
        return;
      }
      const ts = new Date().toISOString().slice(0, 10);
      const base = `chat_${ts}_${info.sessionId.slice(0, 8)}`;
      switch (format) {
        case "markdown": {
          const content = exportAsMarkdown(messages, info);
          downloadFile(content, `${base}.md`, "text/markdown;charset=utf-8");
          break;
        }
        case "csv": {
          const content = exportAsCsv(messages, info);
          downloadFile(content, `${base}.csv`, "text/csv;charset=utf-8");
          break;
        }
        case "json": {
          const content = exportAsJson(messages, info);
          downloadFile(
            content,
            `${base}.json`,
            "application/json;charset=utf-8",
          );
          break;
        }
        case "novel": {
          const content = exportAsNovel(messages);
          downloadFile(
            content,
            `${base}_novel.txt`,
            "text/plain;charset=utf-8",
          );
          break;
        }
        case "markdown_images": {
          if (!sessionId) break;
          setMenuOpen(false);
          setProgress({ format: "markdown_images", loaded: 0, total: null });
          try {
            const { blob, filename } = await exportSessionMarkdown(
              sessionId,
              (loaded, total) =>
                setProgress({ format: "markdown_images", loaded, total }),
            );
            downloadBlob(blob, filename);
          } catch (err) {
            console.error("Markdown export failed", err);
          } finally {
            setProgress(null);
          }
          break;
        }
        case "novel_html_zip": {
          if (!sessionId) break;
          setMenuOpen(false);
          setProgress({ format: "novel_html_zip", loaded: 0, total: null });
          try {
            const { blob, filename } = await exportSessionNovelHtml(
              sessionId,
              (loaded, total) =>
                setProgress({ format: "novel_html_zip", loaded, total }),
            );
            downloadBlob(blob, filename);
          } catch (err) {
            console.error("Novel HTML export failed", err);
          } finally {
            setProgress(null);
          }
          break;
        }
      }
      setMenuOpen(false);
    },
    [messages, sessionId, characterName],
  );

  return { menuOpen, toggleMenu, menuRef, progress, exportAs };
}
