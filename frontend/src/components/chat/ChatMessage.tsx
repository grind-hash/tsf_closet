/**
 * ChatMessage - 個別メッセージコンポーネント
 * 007-chat-interactive-ux
 *
 * User/System/Character メッセージを区別して表示
 */

import { forwardRef, useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { ChatMessage } from "../../types";
import "./ChatMessage.css";

interface ChatMessageProps {
  message: ChatMessage;
  isHighlighted?: boolean;
  isLatestUserMessage?: boolean;
  onSurroundingsImageClick?: (imageUrl: string) => void;
  onDeleteMessage?: (messageId: string) => void;
  onEditMessage?: (messageId: string, content: string) => void;
}

const ChatMessageItem = forwardRef<HTMLDivElement, ChatMessageProps>(
  (
    {
      message,
      isHighlighted = false,
      isLatestUserMessage = false,
      onSurroundingsImageClick,
      onDeleteMessage,
      onEditMessage,
    },
    ref,
  ) => {
    const { t, i18n } = useTranslation();
    const { state } = useGame();
    const { state: chatState } = useChat();
    const { selfProfile } = useSettings();
    const isBusy = state.isTransforming || chatState.isStreaming;
    const [copied, setCopied] = useState(false);
    const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(null);
    const isUser = message.role === "user";

    const handleCopy = useCallback(() => {
      navigator.clipboard.writeText(message.content).then(() => {
        setCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
      });
    }, [message.content]);
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

        {/* ホバー時アクションバー (Discord/Slack 風) */}
        <div className="chat-message__actions">
          <button
            type="button"
            className={`chat-message__action-btn${
              copied ? " chat-message__action-btn--copied" : ""
            }`}
            onClick={handleCopy}
            aria-label={t("chat.message.copy")}
            title={t("chat.message.copy")}
          >
            {copied ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
          </button>
          {isUser && message.id.startsWith("user-") && onDeleteMessage && (
            <button
              type="button"
              className="chat-message__action-btn chat-message__action-btn--delete"
              onClick={() => onDeleteMessage(message.id)}
              disabled={isBusy || !message.relatedHistoryId}
              aria-label={t("gameplay.deleteMessageTitle")}
              title={t("gameplay.deleteMessageTitle")}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          )}
          {isUser && isLatestUserMessage && state.selfMode && onEditMessage && (
            <button
              type="button"
              className="chat-message__action-btn chat-message__action-btn--edit"
              onClick={() => onEditMessage(message.id, message.content)}
              disabled={isBusy || !message.relatedHistoryId}
              aria-label={t("gameplay.editMessageTitle")}
              title={t("gameplay.editMessageTitle")}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          )}
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
