/**
 * ChatContainer - チャットエリアのメインコンテナ
 * 007-chat-interactive-ux
 *
 * 構成:
 * - CharacterStatePanel (上部): キャラクター状態とパラメータ
 * - ChatMessageList (中央): メッセージ一覧
 * - ChatInput (下部): 入力エリア
 */

import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import ChatMessageList from "./ChatMessageList";
import ChatInput from "./ChatInput";
import WelcomeScreen from "./WelcomeScreen";
import "./ChatContainer.css";

interface ChatContainerProps {
  onSendMessage?: (message: string, instructionType: string) => void;
}

export default function ChatContainer({ onSendMessage }: ChatContainerProps) {
  const { state: gameState } = useGame();
  const { state: chatState, messageListRef } = useChat();

  const isSessionActive = gameState.sessionId !== null;

  return (
    <div className="chat-container">
      {/* セッションがない場合はウェルカム画面を表示 */}
      {!isSessionActive ? (
        <WelcomeScreen />
      ) : (
        <>
          {/* メッセージ一覧 */}
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
