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
import ImageOverlay from "./ui/ImageOverlay";
import { useGame } from "../contexts/GameContext";
import { useChat } from "../contexts/ChatContext";
import { useSettings } from "../contexts/SettingsContext";
import { API_BASE } from "../utils/api";
import { fetchAnlasBalance } from "../apis/anlas";
import { deleteGalleryItem } from "../apis/gallery";
import { deleteLatestHistory } from "../apis/game";
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
    instructionType?: string,
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
  // US5: 自分自身モードフラグ
  selfMode?: boolean;
  // 007: セッション開始時のコールバック（App.tsx側でuseSession.restoreSession()を呼ぶため）
  onSessionStart?: () => void;
  // US4: Last generated seed value
  lastGeneratedSeed?: number | null;
  // US5: Anlas balance (NovelAI only)
  anlasBalance?: {
    fixedAnlas: number;
    purchasedAnlas: number;
    totalAnlas: number;
  } | null;
  onAnlasBalanceChange?: (
    balance: {
      fixedAnlas: number;
      purchasedAnlas: number;
      totalAnlas: number;
    } | null,
  ) => void;
  // US2: Last surroundings image from SSE
  lastSurroundingsImage?: {
    imageBase64: string;
    historyId: string;
    seed?: number;
  } | null;
  onClearSurroundingsImage?: () => void;
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
  selfMode: selfModeProp = false,
  onSessionStart,
  lastGeneratedSeed,
  anlasBalance,
  onAnlasBalanceChange,
  lastSurroundingsImage,
  onClearSurroundingsImage,
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
    setSelfMode,
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
    clearInput,
    setInputText,
    setInstructionType,
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

  // US2: 周囲状況画像拡大モーダル
  const [surroundingsOverlayUrl, setSurroundingsOverlayUrl] = useState<
    string | null
  >(null);

  // メッセージ削除確認モーダル
  const [deleteMessageConfirm, setDeleteMessageConfirm] = useState<{
    messageId: string;
    historyId: string;
    responsePreview: string;
  } | null>(null);
  const [isDeletingMessage, setIsDeletingMessage] = useState(false);

  // 最新メッセージ編集・再生成確認モーダル
  const [editMessageConfirm, setEditMessageConfirm] = useState<{
    messageId: string;
    content: string;
  } | null>(null);
  const [isEditingMessage, setIsEditingMessage] = useState(false);

  // Anlas cost confirmation dialog for precise references
  const [anlasConfirmPending, setAnlasConfirmPending] = useState<{
    message: string;
    changeSettings: ChangeSettings;
    transformationType: string;
    transformOptions: Record<string, unknown> | undefined;
    anlasCost: number;
    instructionType?: string;
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
          instructionType: (h.instructionType || "dress_up") as
            | "dress_up"
            | "reality_alter"
            | "conversation"
            | "action",
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
            surroundingsImageUrl: h.surroundingsImageUrl,
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
            msg.role === "user"
              ? ((msg.instruction_type || "conversation") as
                  | "dress_up"
                  | "reality_alter"
                  | "conversation"
                  | "action")
              : undefined,
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

  // US5: selfMode を GameContext に同期
  useEffect(() => {
    setSelfMode(selfModeProp);
  }, [selfModeProp, setSelfMode]);

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
      // GameContextのrestoreSessionを呼び出してsessionIdと全状態を設定
      // history も含めて一括で渡す（Effect A の SET_HISTORY との二重セットは冪等なので安全）
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
        history,
        attributes,
        selfModeProp,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // US5: Initial Anlas balance fetch (NovelAI only)
  useEffect(() => {
    if (imageProvider === "novelai" && onAnlasBalanceChange) {
      fetchAnlasBalance().then((balance) => {
        if (balance) {
          onAnlasBalanceChange(balance);
        }
      });
    }
  }, [imageProvider, onAnlasBalanceChange]);

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

  // US2: Update message with surroundings image when received
  // Attach to the character's feeling text message (not the user's action message)
  useEffect(() => {
    if (lastSurroundingsImage && sessionId) {
      const { imageBase64 } = lastSurroundingsImage;
      // Find the most recent feeling-text system message (character response)
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
      }
      // Clear the surroundings image state
      onClearSurroundingsImage?.();
    }
  }, [
    lastSurroundingsImage,
    sessionId,
    chatState.messages,
    updateMessage,
    onClearSurroundingsImage,
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
          | "conversation"
          | "action",
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
        // action / dress_up / reality_alter -> play/stream
        const transformationType =
          instructionType === "reality_alter" ? "reality" : "costume";

        // Determine instruction_type for backend
        const backendInstructionType =
          instructionType === "action" ? "action" : instructionType;

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
            instructionType: backendInstructionType,
          });
          return; // Wait for user confirmation
        }

        onTransform(
          message,
          undefined,
          changeSettings,
          transformationType,
          transformOptions,
          backendInstructionType,
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

  // プロンプトプレビューからのオーバーライド送信
  const handleSendWithPromptOverride = useCallback(
    (override: string) => {
      if (!sessionId || isTransforming) return;
      const message = chatState.inputText.trim();
      const instructionType = chatState.instructionType;
      if (!message || instructionType === "conversation") return;

      // ユーザーメッセージをチャットに追加
      const now = new Date().toISOString();
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        sessionId,
        role: "user",
        content: message,
        createdAt: now,
        instructionType: instructionType as
          | "dress_up"
          | "reality_alter"
          | "action",
      };
      addMessage(userMsg);

      const transformationType =
        instructionType === "reality_alter" ? "reality" : "costume";
      const backendInstructionType =
        instructionType === "action" ? "action" : instructionType;

      // prompt_override を含むオプションでtransformを実行
      const transformOptions: {
        promptOverride: string;
        maskImage?: string;
        maskId?: string;
        inpaintStrength?: number;
        inpaintNoise?: number;
        negativePrompt?: string;
      } = {
        promptOverride: override,
      };

      if (imageProvider === "novelai") {
        transformOptions.inpaintStrength = inpaintSettings.i2iStrength;
        transformOptions.inpaintNoise = inpaintSettings.inpaintNoise;
        if (inpaintSettings.negativePrompt) {
          transformOptions.negativePrompt = inpaintSettings.negativePrompt;
        }
        if (settingsState.inpaintEnabled && maskDataUrl) {
          transformOptions.maskImage = maskDataUrl;
          transformOptions.maskId = selectedMaskId || undefined;
        }
      }

      onTransform(
        message,
        undefined,
        changeSettings,
        transformationType,
        transformOptions,
        backendInstructionType,
      );

      // 入力をクリア
      clearInput();
    },
    [
      sessionId,
      isTransforming,
      chatState.inputText,
      chatState.instructionType,
      addMessage,
      onTransform,
      changeSettings,
      imageProvider,
      inpaintSettings,
      settingsState.inpaintEnabled,
      maskDataUrl,
      selectedMaskId,
      clearInput,
    ],
  );

  // Anlas confirmation dialog handlers
  const handleAnlasConfirm = useCallback(() => {
    if (!anlasConfirmPending) return;
    const {
      message,
      changeSettings: cs,
      transformationType,
      transformOptions,
      instructionType: pendingInstructionType,
    } = anlasConfirmPending;
    setAnlasConfirmPending(null);
    onTransform(
      message,
      undefined,
      cs,
      transformationType,
      transformOptions,
      pendingInstructionType,
    );
  }, [anlasConfirmPending, onTransform]);

  const handleAnlasCancel = useCallback(() => {
    setAnlasConfirmPending(null);
  }, []);

  // メッセージ削除の確認ダイアログを表示
  const handleRequestDeleteMessage = useCallback(
    (messageId: string) => {
      // user-{historyId} から historyId を抽出
      const historyId = messageId.replace(/^user-/, "");
      // 対応する応答メッセージ (feeling-{historyId}) を取得してプレビューを作成
      const feelingMsg = chatState.messages.find(
        (m) => m.id === `feeling-${historyId}`,
      );
      const preview = feelingMsg
        ? feelingMsg.content.slice(0, 30) +
          (feelingMsg.content.length > 30 ? "..." : "")
        : "";

      setDeleteMessageConfirm({
        messageId,
        historyId,
        responsePreview: preview,
      });
    },
    [chatState.messages],
  );

  // メッセージ削除を実行
  const handleConfirmDeleteMessage = useCallback(async () => {
    if (!deleteMessageConfirm) return;

    const { historyId } = deleteMessageConfirm;

    try {
      setIsDeletingMessage(true);
      // バックエンドの履歴アイテムを削除
      await deleteGalleryItem(historyId);

      // チャットメッセージから対象のユーザーメッセージ + 応答メッセージを除去
      // The feeling message created during streaming uses "feeling-{Date.now()}"
      // (not historyId), so we find it by position after the user message.
      const userMsgIdx = chatState.messages.findIndex(
        (m) => m.id === `user-${historyId}`,
      );
      const idsToRemove = new Set<string>();
      if (userMsgIdx !== -1) {
        idsToRemove.add(chatState.messages[userMsgIdx].id);
        for (let i = userMsgIdx + 1; i < chatState.messages.length; i++) {
          const m = chatState.messages[i];
          if (m.role === "system" && m.isFeelingText) {
            idsToRemove.add(m.id);
            break;
          }
          if (m.role === "user") break;
        }
      }
      setMessages(chatState.messages.filter((m) => !idsToRemove.has(m.id)));

      setDeleteMessageConfirm(null);
    } catch (err) {
      console.error("Failed to delete message:", err);
      setDeleteMessageConfirm(null);
    } finally {
      setIsDeletingMessage(false);
    }
  }, [deleteMessageConfirm, chatState.messages, setMessages]);

  // 最新メッセージ編集リクエスト（確認ダイアログを表示）
  const handleRequestEditMessage = useCallback(
    (messageId: string, content: string) => {
      setEditMessageConfirm({ messageId, content });
    },
    [],
  );

  // 最新メッセージ編集を確定して実行
  const handleConfirmEditMessage = useCallback(async () => {
    if (!editMessageConfirm || !sessionId) return;

    const { messageId, content } = editMessageConfirm;
    const historyId = messageId.replace(/^user-/, "");

    try {
      setIsEditingMessage(true);

      // Backend: delete latest history
      const result = await deleteLatestHistory(sessionId);

      // Chat messages: remove user message + corresponding feeling message
      // The user message ID is "user-{historyId}", but the feeling message
      // created during streaming uses "feeling-{Date.now()}" (not historyId).
      // So we find the feeling message by locating the one that immediately
      // follows the user message in the list.
      const userMsgIdx = chatState.messages.findIndex(
        (m) => m.id === `user-${historyId}`,
      );
      const idsToRemove = new Set<string>();
      if (userMsgIdx !== -1) {
        idsToRemove.add(chatState.messages[userMsgIdx].id);
        // Find the corresponding feeling/system message after the user message
        for (let i = userMsgIdx + 1; i < chatState.messages.length; i++) {
          const m = chatState.messages[i];
          if (m.role === "system" && m.isFeelingText) {
            idsToRemove.add(m.id);
            break;
          }
          if (m.role === "user") break; // next user message reached
        }
      }
      setMessages(chatState.messages.filter((m) => !idsToRemove.has(m.id)));

      // Restore instruction text to input
      setInputText(content);

      // Restore instruction type
      if (result.restored_instruction_type) {
        setInstructionType(
          result.restored_instruction_type as
            | "dress_up"
            | "reality_alter"
            | "conversation"
            | "action",
        );
      }

      // Restore image: use history API URL with restored history ID
      if (result.restored_history_id) {
        setCurrentImage(
          `${API_BASE}/history/images/${result.restored_history_id}`,
        );
      }

      // Re-sync full session state (image URL, history, stats, etc.)
      // Reset the message restoration flag so the useEffect will rebuild
      // messages from fresh history + chatHistory after restoreSession.
      hasRestoredMessagesRef.current = false;
      if (onSessionStart) {
        await onSessionStart();
      }

      setEditMessageConfirm(null);
    } catch (err) {
      console.error("Failed to edit message:", err);
      setEditMessageConfirm(null);
    } finally {
      setIsEditingMessage(false);
    }
  }, [
    editMessageConfirm,
    sessionId,
    chatState.messages,
    setMessages,
    setInputText,
    setInstructionType,
    setCurrentImage,
    onSessionStart,
  ]);

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
      onSendWithPromptOverride={handleSendWithPromptOverride}
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
        {/* US5: Anlas balance display (NovelAI only) */}
        {imageProvider === "novelai" && anlasBalance && (
          <div className="game-play-screen__anlas-bar">
            <span className="game-play-screen__anlas-label">
              Anlas: {anlasBalance.totalAnlas.toLocaleString()}
            </span>
            <span
              className="game-play-screen__anlas-detail"
              title={t(
                "gameplay.anlasBreakdown",
                "Fixed: {{fixed}}, Purchased: {{purchased}}",
                {
                  fixed: anlasBalance.fixedAnlas.toLocaleString(),
                  purchased: anlasBalance.purchasedAnlas.toLocaleString(),
                },
              )}
            >
              ({anlasBalance.fixedAnlas.toLocaleString()} +{" "}
              {anlasBalance.purchasedAnlas.toLocaleString()})
            </span>
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
              {/* US4: Seed display */}
              {lastGeneratedSeed !== null &&
                lastGeneratedSeed !== undefined && (
                  <div
                    className="game-play-screen__seed-display"
                    title={t("gameplay.seedTooltip", "Click to copy seed")}
                    onClick={() => {
                      void navigator.clipboard.writeText(
                        String(lastGeneratedSeed),
                      );
                    }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        void navigator.clipboard.writeText(
                          String(lastGeneratedSeed),
                        );
                      }
                    }}
                  >
                    <span className="game-play-screen__seed-label">Seed:</span>
                    <span className="game-play-screen__seed-value">
                      {lastGeneratedSeed}
                    </span>
                  </div>
                )}
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
                  onSurroundingsImageClick={(url) =>
                    setSurroundingsOverlayUrl(url)
                  }
                  onDeleteMessage={handleRequestDeleteMessage}
                  onEditMessage={handleRequestEditMessage}
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

      {/* メッセージ削除確認ダイアログ */}
      {deleteMessageConfirm && (
        <div
          className="game-play-screen__delete-modal-overlay"
          onClick={() => !isDeletingMessage && setDeleteMessageConfirm(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && !isDeletingMessage)
              setDeleteMessageConfirm(null);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-msg-modal-title"
        >
          <div
            className="game-play-screen__delete-modal"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={() => {}}
            role="document"
          >
            <h3 id="delete-msg-modal-title">
              {t("gameplay.deleteMessageTitle")}
            </h3>
            <p>{t("gameplay.deleteMessageConfirm")}</p>
            {deleteMessageConfirm.responsePreview && (
              <p className="game-play-screen__delete-modal-preview">
                {t("gameplay.deleteMessageResponsePreview", {
                  preview: deleteMessageConfirm.responsePreview,
                })}
              </p>
            )}
            <div className="game-play-screen__delete-modal-actions">
              <button
                type="button"
                onClick={handleConfirmDeleteMessage}
                disabled={isDeletingMessage}
                className="game-play-screen__delete-modal-confirm"
              >
                {t("gameplay.deleteMessageAction")}
              </button>
              <button
                type="button"
                onClick={() => setDeleteMessageConfirm(null)}
                disabled={isDeletingMessage}
                className="game-play-screen__delete-modal-cancel"
              >
                {t("gameplay.deleteMessageCancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* US2: 周囲状況画像拡大表示 */}
      {surroundingsOverlayUrl && (
        <ImageOverlay
          imageUrl={surroundingsOverlayUrl}
          alt="周囲状況画像"
          onClose={() => setSurroundingsOverlayUrl(null)}
        />
      )}

      {/* 最新メッセージ編集確認ダイアログ */}
      {editMessageConfirm && (
        <div
          className="game-play-screen__delete-modal-overlay"
          onClick={() => !isEditingMessage && setEditMessageConfirm(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && !isEditingMessage)
              setEditMessageConfirm(null);
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-msg-modal-title"
        >
          <div
            className="game-play-screen__delete-modal"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={() => {}}
            role="document"
          >
            <h3 id="edit-msg-modal-title">{t("gameplay.editMessageTitle")}</h3>
            <p>{t("gameplay.editMessageConfirm")}</p>
            <p
              className="game-play-screen__delete-modal-preview"
              style={{ fontStyle: "italic" }}
            >
              {editMessageConfirm.content.slice(0, 60)}
              {editMessageConfirm.content.length > 60 ? "..." : ""}
            </p>
            <div className="game-play-screen__delete-modal-actions">
              <button
                type="button"
                onClick={handleConfirmEditMessage}
                disabled={isEditingMessage}
                className="game-play-screen__delete-modal-confirm"
              >
                {t("gameplay.editMessageAction")}
              </button>
              <button
                type="button"
                onClick={() => setEditMessageConfirm(null)}
                disabled={isEditingMessage}
                className="game-play-screen__delete-modal-cancel"
              >
                {t("gameplay.editMessageCancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </MainLayout>
  );
}
/* eslint-enable @typescript-eslint/no-unused-vars */
