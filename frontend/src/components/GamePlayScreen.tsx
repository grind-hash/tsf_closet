/**
 * GamePlayScreen - 3カラムレイアウトのゲームプレイ画面
 * 007-chat-interactive-ux
 *
 * MainLayout を使用した新UIで、既存のGameScreen機能を統合
 *
 * レイアウト構成:
 * ┌─────────────────────────────────────────────────────────────┐
 * │ ┌────────┐ ┌─────────────────────────────┐ ┌─────────────┐ │
 * │ │        │ │   CharacterStatePanel        │ │             │ │
 * │ │ メニュー │ │   ChatMessageList            │ │  RightPanel │ │
 * │ │        │ │   ChatInput                  │ │  (開閉式)   │ │
 * │ └────────┘ └─────────────────────────────┘ └─────────────┘ │
 * └─────────────────────────────────────────────────────────────┘
 */

import React, { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import MainLayout from "./layout/MainLayout";
import RightPanel from "./layout/RightPanel";
import CharacterStatePanel from "./panel/CharacterStatePanel";
import ChatMessageList from "./chat/ChatMessageList";
import ChatInput from "./chat/ChatInput";
import WelcomeScreen from "./chat/WelcomeScreen";
import InpaintModal from "./InpaintModal";
import ImagePreviewModal from "./ImagePreviewModal";
import { useGame } from "../contexts/GameContext";
import { useChat } from "../contexts/ChatContext";
import { useSettings } from "../contexts/SettingsContext";
import { API_BASE } from "../utils/api";
import type {
  ChangeSettings,
  ConversationMessage,
  ChatMessage,
  HistoryItem,
} from "../types";
import "./GamePlayScreen.css";

const DEFAULT_SHAME_VALUE = 50;

interface GamePlayScreenProps {
  // 既存のGameScreen からのprops
  sessionId: string | null;
  currentImageUrl: string | null;
  stats: {
    bloom: number;
    shame: number;
    adaptation: number;
    nsfwMode?: boolean;
    enablePromptPreview?: boolean;
  };
  transformationCount: number;
  history: HistoryItem[];
  attributes: Array<{ id: string; text: string }>;
  feelingText: string;
  isTransforming: boolean;
  chatHistory: ConversationMessage[];
  onChatHistoryChange: (history: ConversationMessage[]) => void;
  onTransform: (
    instruction: string,
    costumeImage?: string,
    changeSettings?: ChangeSettings,
    transformationType?: string,
    options?: {
      maskImage?: string;
      maskId?: string;
      inpaintStrength?: number;
      inpaintNoise?: number;
      negativePrompt?: string;
      promptOverride?: string;
    },
  ) => void;
  changeSettings: ChangeSettings;
  onChangeSettingsUpdate: (settings: ChangeSettings) => void;
  onImproveQuality: () => void;
  onReset: () => void;
  onSelectHistory: (historyId: string) => void;
  onAddAttribute: (text: string) => void;
  onRemoveAttribute: (id: string) => void;
  totalCost: number;
  onResetCost: () => void;
  showCost: boolean;
  imageProvider: "selfhost" | "openrouter" | "novelai";
  // 007: セッション開始時のコールバック（App.tsx側でuseSession.restoreSession()を呼ぶため）
  onSessionStart?: () => void;
}

/* eslint-disable @typescript-eslint/no-unused-vars */
// 未使用の props と変数は将来のリファクタリングで使用予定
export default function GamePlayScreen({
  sessionId,
  currentImageUrl,
  // 以下の props は将来的に RightPanel で使用予定
  stats: _stats,
  transformationCount: _transformationCount,
  history,
  attributes,
  feelingText,
  isTransforming,
  chatHistory,
  onChatHistoryChange,
  onTransform,
  changeSettings,
  onChangeSettingsUpdate: _onChangeSettingsUpdate,
  onImproveQuality: _onImproveQuality,
  onReset: _onReset,
  onSelectHistory: _onSelectHistory,
  onAddAttribute: _onAddAttribute,
  onRemoveAttribute: _onRemoveAttribute,
  totalCost,
  onResetCost,
  showCost,
  imageProvider,
  onSessionStart,
}: GamePlayScreenProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const isNewGameRoute = location.pathname === "/play/new";

  const {
    state: gameState,
    restoreSession,
    updateStats: updateGameStats,
    setCurrentImage,
    setHistory: setGameHistory,
    setAttributes: setGameAttributes,
    navigatePrevHistory,
    navigateNextHistory,
  } = useGame();
  const {
    state: chatState,
    setMessages,
    addMessage,
    updateMessage,
    setMessageStreaming,
    appendToMessage: _appendToMessage,
    setStreaming: _setStreaming,
    messageListRef,
  } = useChat();
  const {
    state: settingsState,
    setInpaintSettings,
    setInpaintMask,
    clearInpaintMask,
    togglePanel,
  } = useSettings();

  // 右パネル開閉状態はSettingsContext経由でlocalStorageに保存
  const showRightPanel = settingsState.rightPanelOpen;
  const uiText = useMemo(
    () => ({
      apiCost: t("gameplay.apiCost"),
      resetCost: t("gameplay.resetCost"),
      maskConfigured: t("gameplay.maskConfigured"),
      chatFetchFailed: t("gameplay.chatFetchFailed"),
      chatNetworkError: t("gameplay.chatNetworkError"),
      imageAlt: t("gameplay.imageAlt"),
      anlasTitle: t("gameplay.anlasTitle"),
      anlasCancel: t("gameplay.anlasCancel"),
      anlasProceed: t("gameplay.anlasProceed"),
    }),
    [t],
  );

  // NovelAI インペイント関連
  const [showInpaintModal, setShowInpaintModal] = useState(false);
  const { maskDataUrl, selectedMaskId } = settingsState.inpaintMask;
  // inpaintSettingsはSettingsContextから取得（RightPanelと同期するため）
  const inpaintSettings = settingsState.inpaintSettings;

  // T031: 画像拡大プレビューモーダル
  const [showImagePreviewModal, setShowImagePreviewModal] = useState(false);

  // Anlas cost confirmation dialog for precise references
  const [anlasConfirmPending, setAnlasConfirmPending] = useState<{
    message: string;
    changeSettings: ChangeSettings;
    transformationType: string;
    transformOptions: Record<string, unknown> | undefined;
    anlasCost: number;
  } | null>(null);

  // チャット履歴を統合して復元（history + chatHistory を時系列順に統合）
  // /play/new の場合は新規ゲームなので復元しない
  const hasRestoredMessagesRef = React.useRef(false);
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

    // 1. history（変身履歴）からメッセージを復元
    if (history && history.length > 0) {
      for (const h of history) {
        // ユーザーの指示メッセージ
        allMessages.push({
          id: `user-${h.id}`,
          sessionId: sessionId,
          role: "user",
          content: h.instruction,
          createdAt: h.timestamp,
          instructionType: "dress_up" as const,
        });
        // 心境テキスト（存在し、画質改善でない場合）
        if (h.feelingText && h.feelingText !== "(画質改善)") {
          allMessages.push({
            id: `feeling-${h.id}`,
            sessionId: sessionId,
            role: "system",
            content: `💭 ${h.feelingText}`,
            createdAt: h.timestamp,
            isFeelingText: true,
          });
        }
      }
    }

    // 2. chatHistory（会話履歴）からメッセージを復元
    if (chatHistory && chatHistory.length > 0) {
      for (const msg of chatHistory) {
        allMessages.push({
          id: msg.id,
          sessionId: sessionId,
          role: msg.role === "user" ? ("user" as const) : ("system" as const),
          content: msg.content,
          createdAt: msg.createdAt || new Date().toISOString(),
          instructionType:
            msg.role === "user" ? ("conversation" as const) : undefined,
          attachedImageUrl: undefined,
          isStreaming: false,
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
      setMessages(allMessages);
      hasRestoredMessagesRef.current = true;
    }
  }, [sessionId, history, chatHistory, setMessages, isNewGameRoute]);

  // GameContextに履歴を同期（既存のhistory propsをGameContext形式に変換）
  // 注: GameContext.setHistoryはHistoryItem[]を期待するが、props.historyは部分的な型
  // ここでは直接同期せず、GameContext側で独自に管理させる
  // useEffect(() => {
  //   if (history.length > 0) {
  //     // 型変換が複雑なため、GameContextへの直接同期はスキップ
  //   }
  // }, [history, setHistory]);

  // GameContextに現在の画像を同期
  useEffect(() => {
    if (currentImageUrl) {
      setCurrentImage(currentImageUrl);
    }
  }, [currentImageUrl, setCurrentImage]);

  // 007: GameContextに履歴を同期（CharacterStatePanelの履歴ナビゲーション用）
  useEffect(() => {
    // historyが配列であれば同期（空配列も含む）
    if (Array.isArray(history)) {
      setGameHistory(history);
    }
  }, [history, setGameHistory]);

  // 007: GameContextに属性を同期（RightPanelがuseGame()経由で属性を操作できるように）
  useEffect(() => {
    if (attributes && attributes.length > 0) {
      setGameAttributes(attributes);
    }
  }, [attributes, setGameAttributes]);

  // 007: GameContextにパラメータを同期（CharacterStatePanelの表示更新用）
  useEffect(() => {
    updateGameStats({
      bloom: _stats.bloom ?? 0,
      shame: _stats.shame ?? DEFAULT_SHAME_VALUE,
      adaptation: _stats.adaptation ?? 0,
      nsfwMode: _stats.nsfwMode ?? false,
      enablePromptPreview: _stats.enablePromptPreview ?? false,
    });
  }, [_stats, updateGameStats]);

  // 007: GameContextにセッション情報を同期（sessionIdが必要な操作のため）
  useEffect(() => {
    if (sessionId && currentImageUrl) {
      // GameContextのrestoreSessionを呼び出してsessionIdを設定
      // 最小限の情報のみ渡す（history, statsは別途同期されるため空データ）
      const fullStats = {
        bloom: _stats.bloom ?? 0,
        shame: _stats.shame ?? 50,
        adaptation: _stats.adaptation ?? 0,
        passedCriticalPoints: [],
        difficulty: "normal" as const,
        nsfwMode: _stats.nsfwMode ?? false,
        enablePromptPreview: _stats.enablePromptPreview ?? false,
      };
      restoreSession(
        sessionId,
        { id: "", name: "", description: "", thumbnail: currentImageUrl },
        currentImageUrl,
        fullStats,
        [], // historyは別途同期
        attributes,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // 心境テキストをチャットメッセージとして追加（ストリーミング対応）
  // ストリーミング中は既存のfeelingメッセージを更新し、完了時に新規追加
  const prevFeelingRef = React.useRef<string | null>(null);
  const currentFeelingIdRef = React.useRef<string | null>(null);
  useEffect(() => {
    if (feelingText && sessionId) {
      // 変身中（ストリーミング中）の場合
      if (isTransforming) {
        if (currentFeelingIdRef.current) {
          // 既存のfeelingメッセージを更新
          updateMessage(currentFeelingIdRef.current, `💭 ${feelingText}`);
        } else {
          // 新しいfeelingメッセージを作成（ストリーミング開始時）
          const newId = `feeling-${Date.now()}`;
          currentFeelingIdRef.current = newId;
          const feelingMsg: ChatMessage = {
            id: newId,
            sessionId: sessionId,
            role: "system",
            content: `💭 ${feelingText}`,
            createdAt: new Date().toISOString(),
            isFeelingText: true,
            isStreaming: true,
          };
          addMessage(feelingMsg);
        }
        prevFeelingRef.current = feelingText;
      } else if (!isTransforming && prevFeelingRef.current !== feelingText) {
        // 変身完了時、最終的なfeelingを確定
        if (currentFeelingIdRef.current) {
          updateMessage(currentFeelingIdRef.current, `💭 ${feelingText}`);
          // ストリーミング状態を解除（カーソル点滅を停止）
          setMessageStreaming(currentFeelingIdRef.current, false);
        } else if (feelingText !== prevFeelingRef.current) {
          // 変身なしでの心境更新（初回表示など）
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
    updateMessage,
    setMessageStreaming,
    isTransforming,
  ]);

  // 右パネルトグル（SettingsContext経由でlocalStorageに永続化）
  const handleToggleRightPanel = useCallback(() => {
    togglePanel();
  }, [togglePanel]);

  // マスク編集保存
  const handleMaskSave = useCallback(
    (maskData: string | null, maskId: string | null) => {
      console.log(
        "[GamePlayScreen] handleMaskSave:",
        maskData ? `${maskData.length} chars` : "null",
        maskId,
      );
      setInpaintMask(maskData, maskId);
      setShowInpaintModal(false);
    },
    [setInpaintMask],
  );

  // チャット送信ハンドラ
  const handleSendMessage = useCallback(
    async (message: string, instructionType: string) => {
      if (!sessionId || isTransforming) return;

      // ユーザーメッセージをチャットに追加
      const now = new Date().toISOString();
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        sessionId: sessionId,
        role: "user",
        content: message,
        createdAt: now,
        instructionType: instructionType as
          | "dress_up"
          | "reality_alter"
          | "conversation",
      };
      addMessage(userMsg);

      // 指示タイプに応じた処理
      if (instructionType === "conversation") {
        // 会話のみ（ストリーミング対応）
        const charMsgId = `char-${Date.now()}`;
        const charNow = new Date().toISOString();

        // キャラクターメッセージをストリーミング状態で追加
        const charMsg: ChatMessage = {
          id: charMsgId,
          sessionId: sessionId,
          role: "system",
          content: "",
          createdAt: charNow,
          isStreaming: true,
        };
        addMessage(charMsg);

        try {
          const params = new URLSearchParams({
            session_id: sessionId,
            message: message,
            language: settingsState.language,
          });
          const response = await fetch(
            `${API_BASE}/game/chat/stream?${params.toString()}`,
          );

          if (response.ok && response.body) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = "";

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const text = decoder.decode(value, { stream: true });
              const lines = text.split("\n");

              for (const line of lines) {
                if (line.startsWith("data: ")) {
                  try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === "text" && data.chunk) {
                      fullResponse += data.chunk;
                      updateMessage(charMsgId, fullResponse);
                    } else if (data.type === "done") {
                      // ストリーミング完了
                      setMessageStreaming(charMsgId, false);
                    } else if (data.type === "error" && data.fallback) {
                      // エラー時はフォールバック応答を表示
                      fullResponse = data.fallback;
                      updateMessage(charMsgId, fullResponse);
                      setMessageStreaming(charMsgId, false);
                    }
                  } catch {
                    // JSON解析エラーは無視
                  }
                }
              }
            }

            // ストリーミング完了後の処理
            setMessageStreaming(charMsgId, false);

            // 既存のchatHistoryにも追加
            const userConvMsg: ConversationMessage = {
              id: userMsg.id,
              role: "user",
              content: message,
              createdAt: userMsg.createdAt,
            };
            const charConvMsg: ConversationMessage = {
              id: charMsgId,
              role: "character",
              content: fullResponse,
              createdAt: charNow,
            };
            onChatHistoryChange([...chatHistory, userConvMsg, charConvMsg]);
          } else {
            // エラー時
            setMessageStreaming(charMsgId, false);
            updateMessage(charMsgId, uiText.chatFetchFailed);
          }
        } catch (err) {
          console.error("Failed to send chat:", err);
          setMessageStreaming(charMsgId, false);
          updateMessage(charMsgId, uiText.chatNetworkError);
        }
      } else {
        // 着せ替えまたは現実改変
        const transformationType =
          instructionType === "reality_alter" ? "reality" : "costume";

        // Build transform options including inpaint and character references
        let transformOptions:
          | {
              maskImage?: string;
              maskId?: string;
              inpaintStrength?: number;
              inpaintNoise?: number;
              negativePrompt?: string;
              promptOverride?: string;
              characterReferences?: Array<{
                imageData: string;
                type: string;
                strength: number;
                fidelity: number;
              }>;
            }
          | undefined;

        // NovelAI mode: always send i2i strength and optionally character references
        if (imageProvider === "novelai") {
          const enabledRefs = settingsState.preciseReferences.filter(
            (r) => r.enabled,
          );
          transformOptions = {
            // Mask only when inpaint is enabled
            ...(settingsState.inpaintEnabled &&
              maskDataUrl && {
                maskImage: maskDataUrl || undefined,
                maskId: selectedMaskId || undefined,
              }),
            // i2i strength and noise are always sent
            inpaintStrength: inpaintSettings.i2iStrength,
            inpaintNoise: inpaintSettings.inpaintNoise,
            negativePrompt: inpaintSettings.negativePrompt || undefined,
            promptOverride: inpaintSettings.promptOverride || undefined,
            // Precise reference images (enabled only)
            ...(enabledRefs.length > 0 && {
              characterReferences: enabledRefs.map((r) => ({
                imageData: r.imageData,
                type: r.type,
                strength: r.strength,
                fidelity: r.fidelity,
              })),
            }),
          };
        }

        // Anlas warning: if precise references are enabled, show confirmation
        const enabledRefCount = transformOptions?.characterReferences
          ? (
              transformOptions.characterReferences as Array<{
                imageData: string;
              }>
            ).length
          : 0;
        if (enabledRefCount > 0) {
          setAnlasConfirmPending({
            message,
            changeSettings,
            transformationType,
            transformOptions: transformOptions as
              | Record<string, unknown>
              | undefined,
            anlasCost: enabledRefCount * 5,
          });
          return; // Wait for user confirmation
        }

        onTransform(
          message,
          undefined,
          changeSettings,
          transformationType,
          transformOptions,
        );
      }
    },
    [
      sessionId,
      isTransforming,
      addMessage,
      updateMessage,
      setMessageStreaming,
      onTransform,
      changeSettings,
      chatHistory,
      onChatHistoryChange,
      imageProvider,
      settingsState.inpaintEnabled,
      uiText,
      maskDataUrl,
      selectedMaskId,
      inpaintSettings,
      settingsState.preciseReferences,
      settingsState.language,
    ],
  );

  // 画像クリック時のハンドラ（画像プレビューモーダル表示）
  const handleImageClick = useCallback(() => {
    // T030: 画像クリックで拡大プレビューを表示
    if (currentImageUrl) {
      setShowImagePreviewModal(true);
    }
  }, [currentImageUrl]);

  // Anlas confirmation dialog handlers
  const handleAnlasConfirm = useCallback(() => {
    if (!anlasConfirmPending) return;
    const {
      message,
      changeSettings: cs,
      transformationType,
      transformOptions,
    } = anlasConfirmPending;
    setAnlasConfirmPending(null);
    onTransform(message, undefined, cs, transformationType, transformOptions);
  }, [anlasConfirmPending, onTransform]);

  const handleAnlasCancel = useCallback(() => {
    setAnlasConfirmPending(null);
  }, []);

  // インペイントトグル時のハンドラ
  const handleInpaintToggle = useCallback(
    (enabled: boolean) => {
      if (!enabled) {
        clearInpaintMask();
        setShowInpaintModal(false);
      }
      if (enabled && imageProvider === "novelai") {
        setShowInpaintModal(true);
      }
    },
    [clearInpaintMask, imageProvider],
  );

  // セッションがない場合はウェルカム画面を表示
  // GameContext.state.isActive が true の場合のみセッションがアクティブと判定
  // clearSession() 後は isActive が false になるので、WelcomeScreen が表示される
  const isSessionActive = gameState.isActive;

  // 右パネルコンテンツ
  const rightPanelContent = (
    <RightPanel
      onClose={togglePanel}
      onOpenInpaintModal={() => setShowInpaintModal(true)}
    />
  );

  return (
    <MainLayout
      rightPanel={rightPanelContent}
      showRightPanel={showRightPanel}
      onToggleRightPanel={handleToggleRightPanel}
    >
      <div className="game-play-screen">
        {/* API料金表示バー: openrouterプロバイダー使用時のみ表示 */}
        {showCost && (
          <div className="game-play-screen__cost-bar">
            <span className="game-play-screen__cost-label">
              {uiText.apiCost}: ${totalCost.toFixed(4)} USD
            </span>
            <button
              type="button"
              className="game-play-screen__cost-reset"
              onClick={onResetCost}
              title={uiText.resetCost}
            >
              ↺
            </button>
          </div>
        )}
        {!isSessionActive ? (
          <WelcomeScreen onSessionStart={onSessionStart} />
        ) : (
          <div className="game-play-screen__content">
            {/* 左カラム: キャラクター状態パネル（縦レイアウト） */}
            <div className="game-play-screen__left-panel">
              <CharacterStatePanel
                onImageClick={handleImageClick}
                onInpaintToggle={handleInpaintToggle}
                onOpenInpaintModal={() => setShowInpaintModal(true)}
                transformationCount={_transformationCount}
                isTransforming={isTransforming}
              />
            </div>

            {/* 右カラム: チャットエリア */}
            <div className="game-play-screen__chat-area">
              {/* チャットメッセージ一覧 */}
              <div className="game-play-screen__messages" ref={messageListRef}>
                <ChatMessageList
                  messages={chatState.messages}
                  highlightedMessageId={chatState.highlightedMessageId}
                  scrollToMessageId={chatState.scrollToMessageId}
                  isTyping={isTransforming}
                />
              </div>

              {/* チャット入力 */}
              <div className="game-play-screen__input">
                {settingsState.inpaintEnabled && maskDataUrl && (
                  <div
                    style={{
                      fontSize: "0.85rem",
                      color: "#8f8",
                      marginBottom: "0.5rem",
                      paddingLeft: "0.5rem",
                    }}
                  >
                    {uiText.maskConfigured}
                  </div>
                )}
                <ChatInput
                  onSendMessage={handleSendMessage}
                  disabled={isTransforming || chatState.isStreaming}
                  imageProvider={imageProvider}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* インペイントモーダル */}
      {showInpaintModal && currentImageUrl && (
        <InpaintModal
          isOpen={showInpaintModal}
          currentImageUrl={currentImageUrl}
          initialMaskDataUrl={maskDataUrl}
          initialMaskId={selectedMaskId}
          initialSettings={inpaintSettings}
          onApply={(settings, mask, maskId) => {
            // SettingsContextのinpaintSettingsを更新（RightPanelと同期）
            setInpaintSettings(settings);
            handleMaskSave(mask, maskId);
          }}
          onClose={() => setShowInpaintModal(false)}
        />
      )}

      {/* T031: 画像プレビューモーダル */}
      <ImagePreviewModal
        isOpen={showImagePreviewModal}
        imageUrl={gameState.currentImage || currentImageUrl}
        onClose={() => setShowImagePreviewModal(false)}
        alt={uiText.imageAlt}
        onPrev={navigatePrevHistory}
        onNext={navigateNextHistory}
        hasPrev={gameState.currentHistoryIndex > 0}
        hasNext={gameState.currentHistoryIndex < gameState.history.length - 1}
      />
      {/* Anlas cost confirmation dialog for precise references */}
      {anlasConfirmPending && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: "var(--bg-secondary, #2a2a2a)",
              borderRadius: 8,
              padding: "1.5rem",
              maxWidth: 400,
              width: "90%",
              boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
            }}
          >
            <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>
              {uiText.anlasTitle}
            </h3>
            <p
              style={{
                margin: "0 0 1rem",
                fontSize: "0.9rem",
                lineHeight: 1.5,
              }}
            >
              精密参照画像の使用により追加で{" "}
              <strong>{anlasConfirmPending.anlasCost} Anlas</strong>{" "}
              を消費します。続行しますか？
            </p>
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                onClick={handleAnlasCancel}
                style={{
                  padding: "0.5rem 1rem",
                  borderRadius: 4,
                  border: "1px solid var(--border-color, #555)",
                  background: "transparent",
                  color: "var(--text-primary, #eee)",
                  cursor: "pointer",
                }}
              >
                {uiText.anlasCancel}
              </button>
              <button
                type="button"
                onClick={handleAnlasConfirm}
                style={{
                  padding: "0.5rem 1rem",
                  borderRadius: 4,
                  border: "none",
                  background: "var(--accent-color, #6366f1)",
                  color: "#fff",
                  cursor: "pointer",
                }}
              >
                {uiText.anlasProceed}
              </button>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  );
}
/* eslint-enable @typescript-eslint/no-unused-vars */
