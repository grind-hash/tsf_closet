/**
 * ChatContainer - チャットエリアのメインコンテナ
 * 007-chat-interactive-ux
 *
 * 構成:
 * - CharacterStatePanel (上部): キャラクター状態とパラメータ
 * - ChatMessageList (中央): メッセージ一覧
 * - ChatInput (下部): 入力エリア
 */

import { useCallback, useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import ChatMessageList from "./ChatMessageList";
import ChatInput from "./ChatInput";
import WelcomeScreen from "./WelcomeScreen";
import {
  exportAsMarkdown,
  exportAsCsv,
  exportAsJson,
  exportAsPlainText,
  exportAsNovel,
  downloadFile,
} from "../../utils/exportChat";
import type { ExportSessionInfo } from "../../utils/exportChat";
import "./ChatContainer.css";

interface ChatContainerProps {
  onSendMessage?: (message: string, instructionType: string) => void;
}

export default function ChatContainer({ onSendMessage }: ChatContainerProps) {
  const { t } = useTranslation();
  const { state: gameState } = useGame();
  const { state: chatState, messageListRef } = useChat();
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  const isSessionActive = gameState.sessionId !== null;
  const hasMessages = chatState.messages.length > 0;

  // Close menu on outside click
  useEffect(() => {
    if (!exportMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (
        exportMenuRef.current &&
        !exportMenuRef.current.contains(e.target as Node)
      ) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen]);

  const buildSessionInfo = useCallback((): ExportSessionInfo => {
    return {
      sessionId: gameState.sessionId ?? "unknown",
      characterName: gameState.character?.name,
    };
  }, [gameState.sessionId, gameState.character]);

  const handleExport = useCallback(
    (format: "markdown" | "csv" | "json" | "clipboard" | "novel") => {
      const info = buildSessionInfo();
      if (format === "clipboard") {
        const content = exportAsPlainText(chatState.messages, info);
        void navigator.clipboard.writeText(content);
        setExportMenuOpen(false);
        return;
      }
      const ts = new Date().toISOString().slice(0, 10);
      const base = `chat_${ts}_${info.sessionId.slice(0, 8)}`;
      switch (format) {
        case "markdown": {
          const content = exportAsMarkdown(chatState.messages, info);
          downloadFile(content, `${base}.md`, "text/markdown;charset=utf-8");
          break;
        }
        case "csv": {
          const content = exportAsCsv(chatState.messages, info);
          downloadFile(content, `${base}.csv`, "text/csv;charset=utf-8");
          break;
        }
        case "json": {
          const content = exportAsJson(chatState.messages, info);
          downloadFile(
            content,
            `${base}.json`,
            "application/json;charset=utf-8",
          );
          break;
        }
        case "novel": {
          const content = exportAsNovel(chatState.messages);
          downloadFile(
            content,
            `${base}_novel.txt`,
            "text/plain;charset=utf-8",
          );
          break;
        }
      }
      setExportMenuOpen(false);
    },
    [chatState.messages, buildSessionInfo],
  );

  return (
    <div className="chat-container">
      {/* セッションがない場合はウェルカム画面を表示 */}
      {!isSessionActive ? (
        <WelcomeScreen />
      ) : (
        <>
          {/* Export header */}
          {hasMessages && (
            <div className="chat-export-header" ref={exportMenuRef}>
              <button
                className="chat-export-header__btn"
                onClick={() => setExportMenuOpen((prev) => !prev)}
                title={t("chat.export.button")}
                data-open={exportMenuOpen}
              >
                ↗ {t("chat.export.button")}
              </button>
              {exportMenuOpen && (
                <div className="chat-export-header__menu">
                  <button onClick={() => handleExport("clipboard")}>
                    {t("chat.export.clipboard")}
                  </button>
                  <hr />
                  <button onClick={() => handleExport("markdown")}>
                    {t("chat.export.markdown")}
                  </button>
                  <button onClick={() => handleExport("csv")}>
                    {t("chat.export.csv")}
                  </button>
                  <button onClick={() => handleExport("json")}>
                    {t("chat.export.json")}
                  </button>
                  <hr />
                  <button onClick={() => handleExport("novel")}>
                    {t("chat.export.novel")}
                  </button>
                  <button onClick={() => handleExport("json")}>
                    {t("chat.export.json")}
                  </button>
                </div>
              )}
            </div>
          )}
          {/* Message list */}
          <div className="chat-container__messages" ref={messageListRef}>
            <ChatMessageList
              messages={chatState.messages}
              highlightedMessageId={chatState.highlightedMessageId}
              scrollToMessageId={chatState.scrollToMessageId}
            />
          </div>

          {/* 入力エリア */}
          <div className="chat-container__input">
            <ChatInput
              onSendMessage={onSendMessage}
              disabled={gameState.isTransforming || chatState.isStreaming}
            />
          </div>
        </>
      )}
    </div>
  );
}
