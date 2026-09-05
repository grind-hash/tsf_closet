import { useCallback, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import type { ChatMessage, InstructionType } from "../types";

/**
 * セッション復元時にチャット欄を組み直す。history(変身履歴)と
 * conversationHistory(会話)を時系列に統合し、初回のみ setMessages する。
 * ギャラリーからの遷移(?historyId=)では対象メッセージと画像へ移動する。
 */
export function useRestoredChatMessages(isNewGameRoute: boolean) {
  const location = useLocation();
  const { state: gameState, navigateToHistoryById } = useGame();
  const { setMessages, scrollToMessage } = useChat();
  const sessionId = gameState.sessionId;
  const history = gameState.history;
  const chatHistory = gameState.conversationHistory;

  // /play/new の場合は新規ゲームなので復元しない
  const hasRestoredMessagesRef = useRef(false);
  useEffect(() => {
    // 新規ゲームルートの場合は復元しない
    if (isNewGameRoute) {
      return;
    }
    // 初回のみ復元
    if (!sessionId || hasRestoredMessagesRef.current) {
      return;
    }

    const allMessages: ChatMessage[] = [];

    // 1. history(変身履歴)からメッセージを復元
    if (history && history.length > 0) {
      for (const h of history) {
        // ユーザーの指示メッセージ
        allMessages.push({
          id: `user-${h.id}`,
          sessionId: sessionId,
          role: "user",
          content: h.instruction,
          createdAt: h.timestamp,
          relatedHistoryId: h.id,
          instructionType: (h.instructionType || "dress_up") as InstructionType,
        });
        // US2: Attach surroundings image to the character's feeling text message
        if (h.feelingText && h.feelingText !== "(画質改善)") {
          allMessages.push({
            id: `feeling-${h.id}`,
            sessionId: sessionId,
            role: "system",
            content: `💭 ${h.feelingText}`,
            createdAt: h.timestamp,
            isFeelingText: true,
            relatedHistoryId: h.id,
            surroundingsImageUrl: h.surroundingsImageUrl,
          });
        }
      }
    }

    // 2. chatHistory(会話履歴)からメッセージを復元
    if (chatHistory && chatHistory.length > 0) {
      for (const msg of chatHistory) {
        allMessages.push({
          id: msg.id,
          sessionId: sessionId,
          role: msg.role === "user" ? ("user" as const) : ("system" as const),
          content: msg.content,
          createdAt: msg.createdAt || new Date().toISOString(),
          instructionType:
            msg.role === "user"
              ? ((msg.instruction_type || "conversation") as InstructionType)
              : undefined,
          attachedImageUrl: undefined,
          isStreaming: false,
          conversationId: msg.id,
        });
      }
    }

    // 3. タイムスタンプ順にソート
    if (allMessages.length > 0) {
      allMessages.sort((a, b) => {
        const dateA = new Date(a.createdAt).getTime();
        const dateB = new Date(b.createdAt).getTime();
        return dateA - dateB;
      });

      // ギャラリーからの遷移時は対象メッセージへのスクロールを予約(自動スクロールを抑制)
      const params = new URLSearchParams(location.search);
      const galleryHistoryId = params.get("historyId");
      if (galleryHistoryId) {
        scrollToMessage(`user-${galleryHistoryId}`);
      }

      setMessages(allMessages);
      hasRestoredMessagesRef.current = true;
    }
  }, [
    sessionId,
    history,
    chatHistory,
    setMessages,
    isNewGameRoute,
    location.search,
    scrollToMessage,
  ]);

  // ギャラリーからの遷移時: historyIdクエリパラメータで指定画像にナビゲート
  const hasNavigatedToHistoryRef = useRef(false);
  useEffect(() => {
    if (hasNavigatedToHistoryRef.current) return;
    if (!history || history.length === 0) return;
    const params = new URLSearchParams(location.search);
    const targetHistoryId = params.get("historyId");
    if (!targetHistoryId) return;
    const success = navigateToHistoryById(targetHistoryId);
    if (success) {
      hasNavigatedToHistoryRef.current = true;
    }
  }, [history, location.search, navigateToHistoryById]);

  /** 次の復元で history + chatHistory からメッセージを組み直させる */
  const resetRestoration = useCallback(() => {
    hasRestoredMessagesRef.current = false;
  }, []);

  return { resetRestoration };
}
