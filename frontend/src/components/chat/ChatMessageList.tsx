/**
 * ChatMessageList - メッセージ一覧コンポーネント
 * 007-chat-interactive-ux
 */

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../../types";
import ChatMessageItem from "./ChatMessage";
import "./ChatMessageList.css";

interface ChatMessageListProps {
  messages: ChatMessage[];
  highlightedMessageId: string | null;
  scrollToMessageId: string | null;
  isTyping?: boolean;
  onSurroundingsImageClick?: (imageUrl: string) => void;
  onDeleteMessage?: (messageId: string) => void;
}

export default function ChatMessageList({
  messages,
  highlightedMessageId,
  scrollToMessageId,
  isTyping = false,
  onSurroundingsImageClick,
  onDeleteMessage,
}: ChatMessageListProps) {
  const { t } = useTranslation();
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const listEndRef = useRef<HTMLDivElement>(null);

  // 新しいメッセージが追加されたら自動スクロール
  useEffect(() => {
    if (messages.length > 0) {
      listEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length]);

  // 特定のメッセージへスクロール
  useEffect(() => {
    if (scrollToMessageId) {
      const element = messageRefs.current.get(scrollToMessageId);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [scrollToMessageId]);

  const setMessageRef = (id: string, element: HTMLDivElement | null) => {
    if (element) {
      messageRefs.current.set(id, element);
    } else {
      messageRefs.current.delete(id);
    }
  };

  if (messages.length === 0) {
    return (
      <div className="chat-message-list chat-message-list--empty">
        <p className="chat-message-list__empty-text">
          {t("chat.list.emptyLine1")}
          <br />
          {t("chat.list.emptyLine2")}
        </p>
      </div>
    );
  }

  return (
    <div className="chat-message-list">
      {messages.map((message) => (
        <ChatMessageItem
          key={message.id}
          message={message}
          isHighlighted={message.id === highlightedMessageId}
          ref={(el) => setMessageRef(message.id, el)}
          onSurroundingsImageClick={onSurroundingsImageClick}
          onDeleteMessage={onDeleteMessage}
        />
      ))}
      {/* タイピングインジケーター - AI応答待ち中に表示 */}
      {isTyping && (
        <div className="chat-message-list__typing-indicator">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      )}
      <div ref={listEndRef} />
    </div>
  );
}
