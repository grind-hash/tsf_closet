import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import { useNotification } from "../contexts/NotificationContext";
import { useSettings } from "../contexts/SettingsContext";
import type { ChatMessage, ConversationMessage } from "../types";
import { API_BASE } from "../utils/api";
import { isHistoryLookbackEnabled } from "../utils/historyLookback";
import { readSseEvents } from "../utils/sse";

/**
 * 会話のみ(instruction_type=conversation)の送信。chat/stream を SSE で読み、
 * キャラクターの返事をストリーミング表示してから会話履歴へ確定する。
 */
export function useConversationStream() {
  const { t } = useTranslation();
  const { showNotification } = useNotification();
  const {
    state: gameState,
    setConversationHistory,
    restoreActiveSession,
  } = useGame();
  const { addMessage, updateMessage, setMessageStreaming } = useChat();
  const { state: settingsState } = useSettings();
  const sessionId = gameState.sessionId;
  const chatHistory = gameState.conversationHistory;

  const streamConversation = useCallback(
    async (message: string, userMsg: ChatMessage) => {
      if (!sessionId) return;
      const charMsgId = `char-${Date.now()}`;
      const charNow = new Date().toISOString();

      // キャラクターメッセージをストリーミング状態で追加
      const charMsg: ChatMessage = {
        id: charMsgId,
        sessionId,
        role: "system",
        content: "",
        createdAt: charNow,
        isStreaming: true,
      };
      addMessage(charMsg);

      try {
        const params = new URLSearchParams({
          session_id: sessionId,
          message,
          language: settingsState.language,
          use_history_lookback: String(
            isHistoryLookbackEnabled(
              settingsState.historyLookbackTargets,
              "conversation",
            ),
          ),
        });
        if (settingsState.enableMultiplePeople) {
          params.set("enable_multiple_people", "true");
        }
        if (settingsState.playMemoryEnabled) {
          params.set("use_play_memory", "true");
        }
        const response = await fetch(
          `${API_BASE}/game/chat/stream?${params.toString()}`,
        );

        if (response.ok && response.body) {
          let fullResponse = "";
          let userConversationId: string | undefined;
          let charConversationId: string | undefined;

          for await (const { data: raw } of readSseEvents(response.body)) {
            try {
              const data = JSON.parse(raw);
              if (data.type === "text" && data.chunk) {
                fullResponse += data.chunk;
                updateMessage(charMsgId, fullResponse);
              } else if (data.type === "done") {
                // ストリーミング完了 - 会話IDを保存
                setMessageStreaming(charMsgId, false);
                if (data.user_conversation_id) {
                  userConversationId = data.user_conversation_id;
                }
                if (data.character_conversation_id) {
                  charConversationId = data.character_conversation_id;
                }
                if (data.play_memory_update === "failed") {
                  showNotification(
                    "warning",
                    t("settings.playMemory.sectionTitle"),
                    t("settings.playMemory.updateWarning"),
                  );
                } else if (data.play_memory_update === "updated") {
                  void restoreActiveSession();
                }
              } else if (data.type === "error" && data.fallback) {
                // エラー時はフォールバック応答を表示
                fullResponse = data.fallback;
                updateMessage(charMsgId, fullResponse);
                setMessageStreaming(charMsgId, false);
                if (data.user_conversation_id) {
                  userConversationId = data.user_conversation_id;
                }
                if (data.character_conversation_id) {
                  charConversationId = data.character_conversation_id;
                }
                if (data.play_memory_update === "updated") {
                  void restoreActiveSession();
                } else if (data.play_memory_update === "failed") {
                  showNotification(
                    "warning",
                    t("settings.playMemory.sectionTitle"),
                    t("settings.playMemory.updateWarning"),
                  );
                }
              }
            } catch {
              // JSON解析エラーは無視
            }
          }

          // ストリーミング完了後の処理
          setMessageStreaming(charMsgId, false);

          // 会話IDをメッセージに反映
          if (userConversationId) {
            updateMessage(userMsg.id, message, {
              conversationId: userConversationId,
            });
          }
          if (charConversationId) {
            updateMessage(charMsgId, fullResponse, {
              conversationId: charConversationId,
            });
          }

          // 既存のchatHistoryにも追加
          const userConvMsg: ConversationMessage = {
            id: userConversationId || userMsg.id,
            role: "user",
            content: message,
            createdAt: userMsg.createdAt,
          };
          const charConvMsg: ConversationMessage = {
            id: charConversationId || charMsgId,
            role: "character",
            content: fullResponse,
            createdAt: charNow,
          };
          setConversationHistory([...chatHistory, userConvMsg, charConvMsg]);
        } else {
          // エラー時
          setMessageStreaming(charMsgId, false);
          updateMessage(charMsgId, t("gameplay.chatFetchFailed"));
        }
      } catch (err) {
        console.error("Failed to send chat:", err);
        setMessageStreaming(charMsgId, false);
        updateMessage(charMsgId, t("gameplay.chatNetworkError"));
      }
    },
    [
      sessionId,
      addMessage,
      updateMessage,
      setMessageStreaming,
      chatHistory,
      setConversationHistory,
      settingsState.language,
      settingsState.enableMultiplePeople,
      settingsState.playMemoryEnabled,
      settingsState.historyLookbackTargets,
      showNotification,
      t,
      restoreActiveSession,
    ],
  );

  return { streamConversation };
}
