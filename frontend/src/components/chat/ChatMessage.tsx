/**
 * ChatMessage - 個別メッセージコンポーネント
 * 007-chat-interactive-ux
 *
 * User/System/Character メッセージを区別して表示
 */

import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../../types";
import "./ChatMessage.css";

interface ChatMessageProps {
  message: ChatMessage;
  isHighlighted?: boolean;
}

const ChatMessageItem = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, isHighlighted = false }, ref) => {
    const { t, i18n } = useTranslation();
    const isUser = message.role === "user";
    const isSystem = message.role === "system";

    const getRoleLabel = () => {
      switch (message.role) {
        case "user":
          return t("chat.message.roleYou");
        case "system":
          // システムからのメッセージは「キャラクター」として表示
          return t("chat.message.roleCharacter");
        case "character":
          return t("chat.message.roleCharacter");
        default:
          return message.role;
      }
    };

    const getInstructionTypeLabel = () => {
      if (!message.instructionType) return null;
      switch (message.instructionType) {
        case "dress_up":
          return t("chat.instructionType.dressUp");
        case "reality_alter":
          return t("chat.instructionType.realityAlter");
        case "conversation":
          return t("chat.instructionType.conversation");
        default:
          return message.instructionType;
      }
    };

    return (
      <div
        ref={ref}
        className={`chat-message ${isUser ? "chat-message--user" : ""} ${
          isSystem ? "chat-message--system" : ""
        } ${isHighlighted ? "chat-message--highlighted" : ""} ${
          message.isStreaming ? "chat-message--streaming" : ""
        }`}
      >
        {/* ヘッダー: 送信者とタイプ */}
        <div className="chat-message__header">
          <span className="chat-message__role">{getRoleLabel()}</span>
          {message.instructionType && (
            <span className="chat-message__type">
              {getInstructionTypeLabel()}
            </span>
          )}
          <span className="chat-message__time">
            {formatTime(message.createdAt, i18n.language)}
          </span>
        </div>

        {/* コンテンツ */}
        <div className="chat-message__content">
          {message.content}
          {message.isStreaming && (
            <span className="chat-message__cursor">▌</span>
          )}
        </div>

        {/* 添付画像 */}
        {message.attachedImageUrl && (
          <div className="chat-message__attachment">
            <img
              src={message.attachedImageUrl}
              alt={t("chat.message.attachedImageAlt")}
              className="chat-message__attachment-image"
            />
          </div>
        )}
      </div>
    );
  },
);

ChatMessageItem.displayName = "ChatMessageItem";

function formatTime(isoString: string, language: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString(language === "en" ? "en-US" : "ja-JP", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default ChatMessageItem;
