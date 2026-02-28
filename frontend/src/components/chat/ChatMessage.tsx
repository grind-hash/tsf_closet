/**
 * ChatMessage - 個別メッセージコンポーネント
 * 007-chat-interactive-ux
 *
 * User/System/Character メッセージを区別して表示
 */

import { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { ChatMessage } from "../../types";
import "./ChatMessage.css";

interface ChatMessageProps {
  message: ChatMessage;
  isHighlighted?: boolean;
  onSurroundingsImageClick?: (imageUrl: string) => void;
}

const ChatMessageItem = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, isHighlighted = false, onSurroundingsImageClick }, ref) => {
    const { t, i18n } = useTranslation();
    const { state } = useGame();
    const { selfProfile } = useSettings();
    const isUser = message.role === "user";
    const isSystem = message.role === "system";

    const getRoleLabel = () => {
      switch (message.role) {
        case "user":
          return state.selfMode
            ? t("chat.message.roleInstruction")
            : t("chat.message.roleYou");
        case "system":
        case "character":
          if (state.selfMode && selfProfile?.display_name) {
            return selfProfile.display_name;
          }
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
        case "action":
          return t("chat.instructionType.action");
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

        {/* US2: 周囲状況画像サムネイル */}
        {message.surroundingsImageUrl && (
          <div
            className="chat-message__surroundings"
            onClick={() =>
              onSurroundingsImageClick?.(message.surroundingsImageUrl!)
            }
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                onSurroundingsImageClick?.(message.surroundingsImageUrl!);
              }
            }}
          >
            <img
              src={message.surroundingsImageUrl}
              alt={t("chat.message.surroundingsImageAlt", {
                defaultValue: "周囲状況",
              })}
              className="chat-message__surroundings-image"
            />
            <span className="chat-message__surroundings-label">
              {t("chat.message.surroundingsLabel", {
                defaultValue: "📍 周囲状況",
              })}
            </span>
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
