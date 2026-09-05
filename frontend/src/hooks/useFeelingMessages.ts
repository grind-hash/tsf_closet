import { useEffect, useRef } from "react";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import type { ChatMessage } from "../types";

/**
 * 心境テキスト(feelingText)をチャットメッセージとして追加・更新する。
 * 変身のストリーミング中は既存の心境メッセージを更新し、完了時に確定する。
 * 周囲状況画像が届いたら、画像を持たない最新の心境メッセージへ紐づける。
 */
export function useFeelingMessages() {
  const { state: gameState, setLastSurroundingsImage } = useGame();
  const {
    state: chatState,
    addMessage,
    updateMessage,
    setMessageStreaming,
    attachFeelingMessage,
    getLatestPendingIdentity,
  } = useChat();
  const sessionId = gameState.sessionId;
  const feelingText = gameState.feelingText;
  const isTransforming = gameState.isTransforming;

  const prevFeelingRef = useRef<string | null>(null);
  const currentFeelingIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (feelingText && sessionId) {
      // 変身中(ストリーミング中)の場合
      if (isTransforming) {
        if (currentFeelingIdRef.current) {
          // 既存のfeelingメッセージを更新
          updateMessage(currentFeelingIdRef.current, `💭 ${feelingText}`);
        } else {
          // 新しいfeelingメッセージを作成(ストリーミング開始時)
          const pendingIdentity = getLatestPendingIdentity();
          if (!pendingIdentity) {
            return;
          }
          const newId = `feeling-${pendingIdentity.tempToken}`;
          currentFeelingIdRef.current = newId;
          const feelingMsg: ChatMessage = {
            id: newId,
            sessionId: sessionId,
            role: "system",
            content: `💭 ${feelingText}`,
            createdAt: new Date().toISOString(),
            isFeelingText: true,
            isStreaming: true,
            pendingToken: pendingIdentity.tempToken,
          };
          addMessage(feelingMsg);
          attachFeelingMessage(pendingIdentity.tempToken, newId);
        }
        prevFeelingRef.current = feelingText;
      } else if (!isTransforming && prevFeelingRef.current !== feelingText) {
        // 変身完了時、最終的なfeelingを確定
        if (currentFeelingIdRef.current) {
          updateMessage(currentFeelingIdRef.current, `💭 ${feelingText}`);
          // ストリーミング状態を解除(カーソル点滅を停止)
          setMessageStreaming(currentFeelingIdRef.current, false);
        } else if (feelingText !== prevFeelingRef.current) {
          // 変身なしでの心境更新(初回表示など)
          const feelingMsg: ChatMessage = {
            id: `feeling-${Date.now()}`,
            sessionId: sessionId,
            role: "system",
            content: `💭 ${feelingText}`,
            createdAt: new Date().toISOString(),
            isFeelingText: true,
          };
          addMessage(feelingMsg);
        }
        prevFeelingRef.current = feelingText;
        currentFeelingIdRef.current = null;
      }
    }
    // isTransformingがfalseになった時点でリセット
    if (!isTransforming && currentFeelingIdRef.current) {
      // ストリーミング状態を確実に解除
      setMessageStreaming(currentFeelingIdRef.current, false);
      currentFeelingIdRef.current = null;
    }
  }, [
    feelingText,
    sessionId,
    addMessage,
    attachFeelingMessage,
    getLatestPendingIdentity,
    updateMessage,
    setMessageStreaming,
    isTransforming,
  ]);

  // 周囲状況画像をフィーリングメッセージに紐づけ
  useEffect(() => {
    const surroundings = gameState.lastSurroundingsImage;
    if (!surroundings || !sessionId) return;

    const { imageBase64 } = surroundings;
    const feelingMsg = [...chatState.messages]
      .reverse()
      .find(
        (m) =>
          m.role === "system" && m.isFeelingText && !m.surroundingsImageUrl,
      );
    if (feelingMsg) {
      const dataUrl = `data:image/png;base64,${imageBase64}`;
      updateMessage(feelingMsg.id, feelingMsg.content, {
        surroundingsImageUrl: dataUrl,
      });
      setLastSurroundingsImage(null);
    }
  }, [
    gameState.lastSurroundingsImage,
    sessionId,
    chatState.messages,
    updateMessage,
    setLastSurroundingsImage,
  ]);
}
