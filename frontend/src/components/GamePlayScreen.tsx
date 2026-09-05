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

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Trans, useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { fetchFavorites, toggleFavorite } from "../apis/favorites";
import { exportSessionMarkdown, exportSessionNovelHtml } from "../apis/gallery";
import {
  deleteConversationMessage,
  deleteHistoryEntry,
  deleteLatestHistory,
} from "../apis/game";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "../constants/novelaiImageModels";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import { useNotification } from "../contexts/NotificationContext";
import { useSettings } from "../contexts/SettingsContext";
import {
  PRECISE_REFERENCE_SECTION_ID,
  usePreciseReferenceFiles,
} from "../hooks/usePreciseReferenceFiles";
import { useWindowFileDrop } from "../hooks/useWindowFileDrop";
import type {
  ChatMessage,
  ConversationMessage,
  InstructionType,
  SessionStats,
} from "../types";
import { API_BASE } from "../utils/api";
import type { ExportSessionInfo } from "../utils/exportChat";
import {
  downloadBlob,
  downloadFile,
  exportAsCsv,
  exportAsJson,
  exportAsMarkdown,
  exportAsNovel,
  exportAsPlainText,
  formatBytes,
} from "../utils/exportChat";
import { generateUUID } from "../utils/generateUUID";
import { isHistoryLookbackEnabled } from "../utils/historyLookback";
import { readSseEvents } from "../utils/sse";
import { readStorageFlag, writeStorageFlag } from "../utils/storage";
import AudioControlBar from "./chat/AudioControlBar";
import ChatInput, { SUGGEST_USE_MEMORY_STORAGE_KEY } from "./chat/ChatInput";
import ChatMessageList from "./chat/ChatMessageList";
import WelcomeScreen from "./chat/WelcomeScreen";
import ImagePreviewModal from "./ImagePreviewModal";
import InpaintModal from "./InpaintModal";
import MainLayout from "./layout/MainLayout";
import RightPanel from "./layout/RightPanel";
import { NovelaiUsageBar } from "./NovelaiUsageBar";
import CharacterPanel from "./panel/CharacterPanel";
import CharacterStatePanel from "./panel/CharacterStatePanel";
import AnlasConfirmDialog from "./ui/AnlasConfirmDialog";
import ConfirmDialog from "./ui/ConfirmDialog";
import FileDropOverlay from "./ui/FileDropOverlay";
import ImageOverlay from "./ui/ImageOverlay";
import "./GamePlayScreen.css";
import "./chat/ChatContainer.css";

const ANLAS_WARN_SUPPRESSED_KEY = "anlas_warn_suppressed";

interface GamePlayScreenProps {
  onTransform: (
    instruction: string,
    costumeImage?: string,
    transformationType?: string,
    options?: {
      maskImage?: string;
      maskId?: string;
      inpaintStrength?: number;
      inpaintNoise?: number;
      negativePrompt?: string;
      promptOverride?: string;
      imageOnlyTextToImage?: boolean;
    },
    instructionType?: string,
    pendingToken?: string,
    useMemory?: boolean,
  ) => void;
  onResetCost: () => void;
  onSessionStart?: () => void;
}

// 未使用の props と変数は将来のリファクタリングで使用予定
export default function GamePlayScreen({
  onTransform,
  onResetCost,
  onSessionStart,
}: GamePlayScreenProps) {
  const { t } = useTranslation();
  const { showNotification } = useNotification();
  const location = useLocation();
  const isNewGameRoute = location.pathname === "/play/new";

  const {
    state: gameState,
    setCurrentImage,
    setConversationHistory,
    setLastSurroundingsImage,
    navigatePrevHistory,
    navigateNextHistory,
    navigateToHistoryById,
    removeHistoryEntry,
    updateStats,
    loadSessionCharacters,
    restoreActiveSession,
  } = useGame();
  const {
    state: chatState,
    setMessages,
    addMessage,
    updateMessage,
    setMessageStreaming,
    appendToMessage: _appendToMessage,
    setStreaming: _setStreaming,
    upsertPendingIdentity,
    attachFeelingMessage,
    getLatestPendingIdentity,
    getMessageHistoryId,
    clearInput,
    setInputText,
    setInstructionType,
    scrollToMessage,
    messageListRef,
  } = useChat();
  const {
    state: settingsState,
    setInpaintSettings,
    setInpaintMask,
    clearInpaintMask,
    togglePanel,
    setPanelOpen,
    isNovelaiV5Active,
  } = useSettings();
  const sessionId = gameState.sessionId;
  const currentImageUrl = gameState.currentImage;
  const history = gameState.history;
  const feelingText = gameState.feelingText;
  const isTransforming = gameState.isTransforming;
  const chatHistory = gameState.conversationHistory;
  const totalCost = settingsState.totalCost;
  const showCost = settingsState.showCost;
  const imageProvider = settingsState.imageProvider;
  const lastGeneratedSeed = gameState.lastGeneratedSeed;
  const anlasBalance = settingsState.anlasBalance;
  const [isMobileAnlasExpanded, setIsMobileAnlasExpanded] = useState(false);

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
  const [favoritedHistoryIds, setFavoritedHistoryIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [favoriteBusy, setFavoriteBusy] = useState(false);

  // US2: 周囲状況画像拡大モーダル
  const [surroundingsOverlayUrl, setSurroundingsOverlayUrl] = useState<
    string | null
  >(null);

  // Export menu
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  // 画像同梱エクスポート（Markdown / Novel HTML zip）のダウンロード進捗
  const [exportProgress, setExportProgress] = useState<{
    format: "markdown_images" | "novel_html_zip";
    loaded: number;
    total: number | null;
  } | null>(null);

  // メッセージ削除確認モーダル
  const [deleteMessageConfirm, setDeleteMessageConfirm] = useState<{
    messageId: string;
    historyId?: string;
    conversationId?: string;
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
    transformationType: string;
    transformOptions: Record<string, unknown> | undefined;
    anlasCost: number;
    instructionType?: string;
    useMemory: boolean;
  } | null>(null);

  // V5 利用上限の使い切り警告ダイアログ（Anlas 消費で生成が続く状態）
  const [usageWarnPending, setUsageWarnPending] = useState<{
    message: string;
    transformationType: string;
    transformOptions: Record<string, unknown> | undefined;
    instructionType?: string;
    useMemory: boolean;
  } | null>(null);

  // Close export menu on outside click
  useEffect(() => {
    if (!exportMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (
        exportMenuRef.current &&
        !exportMenuRef.current.contains(e.target as Node)
      ) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen]);

  const buildExportSessionInfo = useCallback((): ExportSessionInfo => {
    return {
      sessionId: gameState.sessionId ?? "unknown",
      characterName: gameState.character?.name,
    };
  }, [gameState.sessionId, gameState.character]);

  const handleExport = useCallback(
    async (
      format:
        | "markdown"
        | "csv"
        | "json"
        | "clipboard"
        | "novel"
        | "markdown_images"
        | "novel_html_zip",
    ) => {
      const info = buildExportSessionInfo();
      if (format === "clipboard") {
        const content = exportAsPlainText(chatState.messages, info);
        void navigator.clipboard.writeText(content);
        setExportMenuOpen(false);
        return;
      }
      const ts = new Date().toISOString().slice(0, 10);
      const base = `chat_${ts}_${info.sessionId.slice(0, 8)}`;
      switch (format) {
        case "markdown": {
          const content = exportAsMarkdown(chatState.messages, info);
          downloadFile(content, `${base}.md`, "text/markdown;charset=utf-8");
          break;
        }
        case "csv": {
          const content = exportAsCsv(chatState.messages, info);
          downloadFile(content, `${base}.csv`, "text/csv;charset=utf-8");
          break;
        }
        case "json": {
          const content = exportAsJson(chatState.messages, info);
          downloadFile(
            content,
            `${base}.json`,
            "application/json;charset=utf-8",
          );
          break;
        }
        case "novel": {
          const content = exportAsNovel(chatState.messages);
          downloadFile(
            content,
            `${base}_novel.txt`,
            "text/plain;charset=utf-8",
          );
          break;
        }
        case "markdown_images": {
          if (!gameState.sessionId) break;
          setExportMenuOpen(false);
          setExportProgress({
            format: "markdown_images",
            loaded: 0,
            total: null,
          });
          try {
            const { blob, filename } = await exportSessionMarkdown(
              gameState.sessionId,
              (loaded, total) =>
                setExportProgress({
                  format: "markdown_images",
                  loaded,
                  total,
                }),
            );
            downloadBlob(blob, filename);
          } catch (err) {
            console.error("Markdown export failed", err);
          } finally {
            setExportProgress(null);
          }
          break;
        }
        case "novel_html_zip": {
          if (!gameState.sessionId) break;
          setExportMenuOpen(false);
          setExportProgress({
            format: "novel_html_zip",
            loaded: 0,
            total: null,
          });
          try {
            const { blob, filename } = await exportSessionNovelHtml(
              gameState.sessionId,
              (loaded, total) =>
                setExportProgress({
                  format: "novel_html_zip",
                  loaded,
                  total,
                }),
            );
            downloadBlob(blob, filename);
          } catch (err) {
            console.error("Novel HTML export failed", err);
          } finally {
            setExportProgress(null);
          }
          break;
        }
      }
      setExportMenuOpen(false);
    },
    [chatState.messages, buildExportSessionInfo, gameState.sessionId],
  );

  // お気に入り履歴IDをセッション開始時に読み込む (spec 009)
  useEffect(() => {
    if (!sessionId || isNewGameRoute) {
      setFavoritedHistoryIds(new Set());
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const ids = new Set<string>();
        let page = 1;
        while (page <= 20) {
          const data = await fetchFavorites(page, 100);
          for (const item of data.items) {
            ids.add(item.history_id);
          }
          if (!data.has_more) break;
          page += 1;
        }
        if (!cancelled) {
          setFavoritedHistoryIds(ids);
        }
      } catch {
        // お気に入り取得失敗はプレビューの初期状態にのみ影響するため握りつぶす
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, isNewGameRoute]);

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

      // ギャラリーからの遷移時は対象メッセージへのスクロールを予約（自動スクロールを抑制）
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
  const hasNavigatedToHistoryRef = React.useRef(false);
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

  // GameContextに履歴を同期（既存のhistory propsをGameContext形式に変換）
  // 注: GameContext.setHistoryはHistoryItem[]を期待するが、props.historyは部分的な型
  // ここでは直接同期せず、GameContext側で独自に管理させる
  // useEffect(() => {
  //   if (history.length > 0) {
  //     // 型変換が複雑なため、GameContextへの直接同期はスキップ
  //   }
  // }, [history, setHistory]);

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

  // 右パネルトグル（SettingsContext経由でlocalStorageに永続化）
  const handleToggleRightPanel = useCallback(() => {
    togglePanel();
  }, [togglePanel]);

  // 画面全体への画像ドロップ → 精密参照画像に追加（NovelAI 選択時のみ受け付ける）
  const { addFiles: addPreciseReferenceFiles } = usePreciseReferenceFiles();
  const isPreciseRefDropEnabled = imageProvider === "novelai";
  const canAddPreciseReference = isPreciseRefDropEnabled && !isNovelaiV5Active;
  const [pendingPreciseRefScroll, setPendingPreciseRefScroll] = useState(false);

  const handleScreenPreciseRefDrop = useCallback(
    async (files: File[]) => {
      if (!canAddPreciseReference) {
        showNotification(
          "warning",
          t("gameplay.preciseRefDropResultTitle"),
          t("rightPanel.preciseReferenceV5Unavailable"),
        );
        return;
      }
      const { addedCount, error } = await addPreciseReferenceFiles(files);
      if (error) {
        showNotification(
          addedCount > 0 ? "warning" : "error",
          t("gameplay.preciseRefDropResultTitle"),
          error,
        );
      }
      if (addedCount > 0) {
        // 右パネルを開き、描画後に精密参照セクションへスクロールする（下の effect）
        setPanelOpen(true);
        setPendingPreciseRefScroll(true);
      }
    },
    [
      addPreciseReferenceFiles,
      canAddPreciseReference,
      setPanelOpen,
      showNotification,
      t,
    ],
  );

  const isFileDragging = useWindowFileDrop({
    enabled: isPreciseRefDropEnabled,
    onFiles: handleScreenPreciseRefDrop,
  });

  // ドロップ後: 右パネルが開いた描画を待ってから精密参照セクションへスクロール
  useEffect(() => {
    if (!pendingPreciseRefScroll || !showRightPanel) return;
    setPendingPreciseRefScroll(false);
    document
      .getElementById(PRECISE_REFERENCE_SECTION_ID)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [pendingPreciseRefScroll, showRightPanel]);

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
    async (message: string, instructionType: string, useMemory: boolean) => {
      if (!sessionId || isTransforming) return;

      // ユーザーメッセージをチャットに追加
      const now = new Date().toISOString();
      const tempToken = generateUUID();
      const userMsg: ChatMessage = {
        id: `user-${tempToken}`,
        sessionId: sessionId,
        role: "user",
        content: message,
        createdAt: now,
        pendingToken: tempToken,
        instructionType: instructionType as InstructionType,
      };
      addMessage(userMsg);
      upsertPendingIdentity({
        tempToken,
        userMessageId: userMsg.id,
        feelingMessageId: null,
        resolvedHistoryId: null,
        status: "pending",
      });

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
              imageOnlyTextToImage?: boolean;
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
          // V5系モデルは精密参照非対応のため送らない
          const enabledRefs = isNovelaiV5Active
            ? []
            : settingsState.preciseReferences.filter((r) => r.enabled);
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

        // 画像のみモードで「前画像を使わない」が ON なら text-to-image フラグを載せる
        // （確認ダイアログ経由の再送にも transformOptions ごと引き継がれる）
        if (
          backendInstructionType === "image_only" &&
          chatState.imageOnlyTextToImage
        ) {
          transformOptions = {
            ...(transformOptions ?? {}),
            imageOnlyTextToImage: true,
          };
        }

        // V5 利用上限を使い切った状態での生成は Anlas を消費するため警告する
        const usageExhausted =
          anlasBalance?.usage != null &&
          (anlasBalance.usage.percent <= 0 || anlasBalance.usage.isNegative);
        if (
          isNovelaiV5Active &&
          usageExhausted &&
          !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
        ) {
          setUsageWarnPending({
            message,
            transformationType,
            transformOptions: transformOptions as
              | Record<string, unknown>
              | undefined,
            instructionType: backendInstructionType,
            useMemory,
          });
          return; // Wait for user confirmation
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
          if (readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)) {
            onTransform(
              message,
              undefined,
              transformationType,
              transformOptions,
              backendInstructionType,
              undefined,
              useMemory,
            );
            return;
          }
          setAnlasConfirmPending({
            message,
            transformationType,
            transformOptions: transformOptions as
              | Record<string, unknown>
              | undefined,
            anlasCost: enabledRefCount * 5,
            instructionType: backendInstructionType,
            useMemory,
          });
          return; // Wait for user confirmation
        }

        onTransform(
          message,
          undefined,
          transformationType,
          transformOptions,
          backendInstructionType,
          tempToken,
          useMemory,
        );
      }
    },
    [
      sessionId,
      isTransforming,
      addMessage,
      upsertPendingIdentity,
      updateMessage,
      setMessageStreaming,
      onTransform,
      chatHistory,
      setConversationHistory,
      imageProvider,
      settingsState.inpaintEnabled,
      uiText,
      maskDataUrl,
      selectedMaskId,
      inpaintSettings,
      settingsState.preciseReferences,
      isNovelaiV5Active,
      anlasBalance,
      settingsState.language,
      settingsState.enableMultiplePeople,
      settingsState.playMemoryEnabled,
      settingsState.historyLookbackTargets,
      showNotification,
      t,
      restoreActiveSession,
      chatState.imageOnlyTextToImage,
    ],
  );

  // 画像クリック時のハンドラ（画像プレビューモーダル表示）
  const handleImageClick = useCallback(() => {
    // T030: 画像クリックで拡大プレビューを表示
    if (currentImageUrl) {
      setShowImagePreviewModal(true);
    }
  }, [currentImageUrl]);

  const currentPreviewHistory =
    gameState.history[gameState.currentHistoryIndex] ?? null;
  const currentHistoryId = currentPreviewHistory?.id ?? null;
  const isCurrentHistoryFavorited = Boolean(
    currentHistoryId && favoritedHistoryIds.has(currentHistoryId),
  );

  const handleToggleFavorite = useCallback(async () => {
    const historyId = gameState.history[gameState.currentHistoryIndex]?.id;
    if (!historyId || favoriteBusy) return;
    const currently = favoritedHistoryIds.has(historyId);
    setFavoriteBusy(true);
    try {
      const next = await toggleFavorite(historyId, currently);
      setFavoritedHistoryIds((prev) => {
        const copy = new Set(prev);
        if (next) {
          copy.add(historyId);
        } else {
          copy.delete(historyId);
        }
        return copy;
      });
    } catch (err) {
      console.error("Failed to toggle favorite:", err);
    } finally {
      setFavoriteBusy(false);
    }
  }, [
    favoriteBusy,
    favoritedHistoryIds,
    gameState.currentHistoryIndex,
    gameState.history,
  ]);

  // 画像ナビゲーション時のチャットスクロール
  const scrollToCurrentHistoryMessage = useCallback(
    (historyIndex: number) => {
      if (!settingsState.linkChatToImage) return;
      const item = gameState.history[historyIndex];
      if (!item) return;
      const el = document.getElementById(`history-msg-${item.id}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    },
    [settingsState.linkChatToImage, gameState.history],
  );

  const handlePrevWithScroll = useCallback(() => {
    const newIndex = gameState.currentHistoryIndex - 1;
    navigatePrevHistory();
    scrollToCurrentHistoryMessage(newIndex);
  }, [
    gameState.currentHistoryIndex,
    navigatePrevHistory,
    scrollToCurrentHistoryMessage,
  ]);

  const handleNextWithScroll = useCallback(() => {
    const newIndex = gameState.currentHistoryIndex + 1;
    navigateNextHistory();
    scrollToCurrentHistoryMessage(newIndex);
  }, [
    gameState.currentHistoryIndex,
    navigateNextHistory,
    scrollToCurrentHistoryMessage,
  ]);

  // プロンプトプレビューからのオーバーライド送信
  const handleSendWithPromptOverride = useCallback(
    (override: string) => {
      if (!sessionId || isTransforming) return;
      const message = chatState.inputText.trim();
      const instructionType = chatState.instructionType;
      if (!message || instructionType === "conversation") return;

      // ユーザーメッセージをチャットに追加
      const now = new Date().toISOString();
      const tempToken = generateUUID();
      const userMsg: ChatMessage = {
        id: `user-${tempToken}`,
        sessionId,
        role: "user",
        content: message,
        createdAt: now,
        pendingToken: tempToken,
        instructionType: instructionType as InstructionType,
      };
      addMessage(userMsg);
      upsertPendingIdentity({
        tempToken,
        userMessageId: userMsg.id,
        feelingMessageId: null,
        resolvedHistoryId: null,
        status: "pending",
      });

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
        imageOnlyTextToImage?: boolean;
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
      // 画像のみモードで「前画像を使わない」が ON なら text-to-image フラグを載せる
      if (
        backendInstructionType === "image_only" &&
        chatState.imageOnlyTextToImage
      ) {
        transformOptions.imageOnlyTextToImage = true;
      }

      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        backendInstructionType,
        tempToken,
        readStorageFlag("local", SUGGEST_USE_MEMORY_STORAGE_KEY),
      );

      // 入力をクリア
      clearInput();
    },
    [
      sessionId,
      isTransforming,
      chatState.inputText,
      chatState.instructionType,
      chatState.imageOnlyTextToImage,
      addMessage,
      upsertPendingIdentity,
      onTransform,
      imageProvider,
      inpaintSettings,
      settingsState.inpaintEnabled,
      maskDataUrl,
      selectedMaskId,
      clearInput,
    ],
  );

  // Anlas confirmation dialog handlers
  const handleAnlasConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!anlasConfirmPending) return;
      const {
        message,
        transformationType,
        transformOptions,
        instructionType: pendingInstructionType,
        useMemory,
      } = anlasConfirmPending;
      if (doNotShowAgain) {
        writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
      }
      setAnlasConfirmPending(null);
      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        pendingInstructionType,
        undefined,
        useMemory,
      );
    },
    [anlasConfirmPending, onTransform],
  );

  const handleAnlasCancel = useCallback(() => {
    setAnlasConfirmPending(null);
  }, []);

  // V5 利用上限使い切り警告ダイアログのハンドラー
  const handleUsageWarnConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!usageWarnPending) return;
      const {
        message,
        transformationType,
        transformOptions,
        instructionType: pendingInstructionType,
        useMemory,
      } = usageWarnPending;
      if (doNotShowAgain) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      setUsageWarnPending(null);
      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        pendingInstructionType,
        undefined,
        useMemory,
      );
    },
    [usageWarnPending, onTransform],
  );

  const handleUsageWarnCancel = useCallback(() => {
    setUsageWarnPending(null);
  }, []);

  // メッセージ削除の確認ダイアログを表示
  const handleRequestDeleteMessage = useCallback(
    (messageId: string) => {
      const historyId = getMessageHistoryId(messageId);

      // 会話メッセージのconversationIdを取得
      const userMessage = chatState.messages.find((m) => m.id === messageId);
      const conversationId = userMessage?.conversationId;

      // historyIdもconversationIdもなければ削除不可
      if (!historyId && !conversationId) {
        return;
      }

      if (historyId) {
        // 画像付きメッセージ: 応答メッセージのプレビューを作成
        const feelingMsg = chatState.messages.find(
          (m) => m.relatedHistoryId === historyId && m.isFeelingText,
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
      } else {
        // 会話のみメッセージ: 対応するキャラクター応答を検索
        const msgIndex = chatState.messages.findIndex(
          (m) => m.id === messageId,
        );
        const charMsg =
          msgIndex >= 0 ? chatState.messages[msgIndex + 1] : undefined;
        const preview =
          charMsg && charMsg.role !== "user"
            ? charMsg.content.slice(0, 30) +
              (charMsg.content.length > 30 ? "..." : "")
            : "";

        setDeleteMessageConfirm({
          messageId,
          conversationId,
          responsePreview: preview,
        });
      }
    },
    [chatState.messages, getMessageHistoryId],
  );

  // メッセージ削除を実行
  const handleConfirmDeleteMessage = useCallback(async () => {
    if (!deleteMessageConfirm) return;

    const { messageId, historyId, conversationId } = deleteMessageConfirm;

    try {
      setIsDeletingMessage(true);

      if (historyId) {
        // 画像付きメッセージ: 履歴エントリを完全削除（History + 画像 + 会話テキスト）
        const result = await deleteHistoryEntry(historyId, sessionId || "");

        // チャットメッセージから対象のユーザーメッセージ + 応答メッセージを除去
        const idsToRemove = new Set(
          chatState.messages
            .filter(
              (message) =>
                message.relatedHistoryId === historyId ||
                message.id === `user-${historyId}` ||
                message.id === `feeling-${historyId}`,
            )
            .map((message) => message.id),
        );
        setMessages(chatState.messages.filter((m) => !idsToRemove.has(m.id)));

        // GameContext の history からもエントリを除去（画像表示を更新）
        removeHistoryEntry(historyId, result.restored_history_id || "");

        // parameter_reverts がある場合、フロントエンドの stats に反映する
        if (result.parameter_reverts && result.parameter_reverts.length > 0) {
          const statsUpdate: Partial<SessionStats> = {};
          for (const revert of result.parameter_reverts) {
            (statsUpdate as Record<string, number>)[revert.stat_name] =
              revert.new_value;
          }
          updateStats(statsUpdate);
        }
      } else if (conversationId) {
        // 会話のみメッセージ: ユーザーの会話レコードを削除
        await deleteConversationMessage(conversationId, sessionId || "");

        // 対応するキャラクター応答メッセージも特定して削除
        const userMessage = chatState.messages.find((m) => m.id === messageId);
        const msgIndex = chatState.messages.findIndex(
          (m) => m.id === messageId,
        );
        const charMsg =
          msgIndex >= 0 ? chatState.messages[msgIndex + 1] : undefined;

        // キャラクター応答の会話レコードも削除
        if (charMsg && charMsg.role !== "user" && charMsg.conversationId) {
          try {
            await deleteConversationMessage(
              charMsg.conversationId,
              sessionId || "",
            );
          } catch {
            // キャラクター応答の削除失敗は無視
          }
        }

        // UIからメッセージペアを除去
        const idsToRemove = new Set([messageId]);
        if (charMsg && charMsg.role !== "user") {
          idsToRemove.add(charMsg.id);
        }
        setMessages(chatState.messages.filter((m) => !idsToRemove.has(m.id)));

        // conversationHistoryからも除去
        const convIdsToRemove = new Set<string>();
        if (userMessage?.conversationId) {
          convIdsToRemove.add(userMessage.conversationId);
        }
        if (charMsg?.conversationId) {
          convIdsToRemove.add(charMsg.conversationId);
        }
        if (convIdsToRemove.size > 0) {
          setConversationHistory(
            chatHistory.filter((ch) => !convIdsToRemove.has(ch.id)),
          );
        }
      }

      // 履歴削除に伴いバックエンドが SessionCharacter の外見を最新履歴に
      // 復帰するため、フロント側のキャラクターパネル表示も再同期する。
      void loadSessionCharacters();

      setDeleteMessageConfirm(null);
    } catch (err) {
      console.error("Failed to delete message:", err);
      setDeleteMessageConfirm(null);
    } finally {
      setIsDeletingMessage(false);
    }
  }, [
    deleteMessageConfirm,
    chatState.messages,
    setMessages,
    sessionId,
    removeHistoryEntry,
    updateStats,
    chatHistory,
    setConversationHistory,
    loadSessionCharacters,
  ]);

  // 最新メッセージ編集リクエスト（確認ダイアログを表示）
  const handleRequestEditMessage = useCallback(
    (messageId: string, content: string) => {
      // Temporary guard: right after sending, the ID is still a timestamp (not UUID).
      const historyId = getMessageHistoryId(messageId);
      if (!historyId) {
        return;
      }

      setEditMessageConfirm({ messageId, content });
    },
    [getMessageHistoryId],
  );

  // 最新メッセージ編集を確定して実行
  const handleConfirmEditMessage = useCallback(async () => {
    if (!editMessageConfirm || !sessionId) return;

    const { messageId, content } = editMessageConfirm;
    const historyId = getMessageHistoryId(messageId);
    if (!historyId) {
      return;
    }

    try {
      setIsEditingMessage(true);

      // Backend: delete latest history
      const result = await deleteLatestHistory(sessionId);

      // Chat messages: remove user message + corresponding feeling message
      // The user message ID is "user-{historyId}", but the feeling message
      // created during streaming uses "feeling-{Date.now()}" (not historyId).
      // So we find the feeling message by locating the one that immediately
      // follows the user message in the list.
      const idsToRemove = new Set(
        chatState.messages
          .filter((message) => message.relatedHistoryId === historyId)
          .map((message) => message.id),
      );
      setMessages(chatState.messages.filter((m) => !idsToRemove.has(m.id)));

      // Restore instruction text to input
      setInputText(content);

      // Restore instruction type
      if (result.restored_instruction_type) {
        setInstructionType(result.restored_instruction_type as InstructionType);
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

      // 履歴削除に伴いバックエンドが SessionCharacter の外見を最新履歴に
      // 復帰するため、フロント側のキャラクターパネル表示も再同期する。
      void loadSessionCharacters();

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
    getMessageHistoryId,
    setInputText,
    setInstructionType,
    setCurrentImage,
    onSessionStart,
    loadSessionCharacters,
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
          <div
            className={`game-play-screen__anlas-bar${
              isMobileAnlasExpanded ? " is-expanded" : ""
            }`}
          >
            <button
              type="button"
              className="game-play-screen__anlas-toggle"
              aria-expanded={isMobileAnlasExpanded}
              aria-controls="mobile-anlas-balance"
              onClick={() => setIsMobileAnlasExpanded((expanded) => !expanded)}
            >
              <span>Anlas</span>
              <span
                className="game-play-screen__anlas-toggle-icon"
                aria-hidden="true"
              >
                ▾
              </span>
            </button>
            <div
              id="mobile-anlas-balance"
              className="game-play-screen__anlas-content"
            >
              {isNovelaiV5Active && anlasBalance.usage && (
                <NovelaiUsageBar usage={anlasBalance.usage} compact />
              )}
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
                transformationCount={gameState.transformationCount}
                isTransforming={isTransforming}
                canFavorite={Boolean(currentHistoryId)}
                isFavorited={isCurrentHistoryFavorited}
                favoriteBusy={favoriteBusy}
                onToggleFavorite={handleToggleFavorite}
              />
              {settingsState.enableMultiplePeople && <CharacterPanel />}
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

            {/* Right column: chat area */}
            <div className="game-play-screen__chat-area">
              {/* Export header */}
              {chatState.messages.length > 0 && (
                <div className="chat-export-header" ref={exportMenuRef}>
                  {exportProgress && (
                    <div
                      className="chat-export-header__progress"
                      role="status"
                      aria-live="polite"
                    >
                      <span className="chat-export-header__progress-label">
                        {exportProgress.format === "markdown_images"
                          ? t("chat.export.markdownWithImages")
                          : t("chat.export.novelHtmlZip")}{" "}
                        {t("chat.export.exporting")}
                      </span>
                      <div className="chat-export-header__progress-bar">
                        <div
                          className="chat-export-header__progress-bar-fill"
                          data-indeterminate={!exportProgress.total}
                          style={
                            exportProgress.total
                              ? {
                                  width: `${Math.min(
                                    100,
                                    (exportProgress.loaded /
                                      exportProgress.total) *
                                      100,
                                  )}%`,
                                }
                              : undefined
                          }
                        />
                      </div>
                      <span className="chat-export-header__progress-text">
                        {exportProgress.total
                          ? `${Math.round(
                              (exportProgress.loaded / exportProgress.total) *
                                100,
                            )}%`
                          : formatBytes(exportProgress.loaded)}
                      </span>
                    </div>
                  )}
                  <button
                    className="chat-export-header__btn"
                    onClick={() => setExportMenuOpen((prev) => !prev)}
                    title={t("chat.export.button")}
                    data-open={exportMenuOpen}
                    disabled={!!exportProgress}
                  >
                    ↗ {t("chat.export.button")}
                  </button>
                  {exportMenuOpen && (
                    <div className="chat-export-header__menu">
                      <button onClick={() => handleExport("clipboard")}>
                        {t("chat.export.clipboard")}
                      </button>
                      <hr />
                      <button onClick={() => handleExport("markdown")}>
                        {t("chat.export.markdown")}
                      </button>
                      <button onClick={() => handleExport("csv")}>
                        {t("chat.export.csv")}
                      </button>
                      <button onClick={() => handleExport("json")}>
                        {t("chat.export.json")}
                      </button>
                      <hr />
                      <button onClick={() => handleExport("novel")}>
                        {t("chat.export.novel")}
                      </button>
                      <button onClick={() => handleExport("markdown_images")}>
                        {t("chat.export.markdownWithImages")}
                      </button>
                      <button onClick={() => handleExport("novel_html_zip")}>
                        {t("chat.export.novelHtmlZip")}
                      </button>
                    </div>
                  )}
                </div>
              )}
              {/* Message area */}
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

              <AudioControlBar />

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
        onPrev={handlePrevWithScroll}
        onNext={handleNextWithScroll}
        hasPrev={gameState.currentHistoryIndex > 0}
        hasNext={gameState.currentHistoryIndex < gameState.history.length - 1}
        historyId={currentHistoryId}
        isFavorited={isCurrentHistoryFavorited}
        favoriteBusy={favoriteBusy}
        onToggleFavorite={handleToggleFavorite}
        captionPlacement={currentPreviewHistory ? "side" : "below"}
        caption={
          currentPreviewHistory ? (
            <div className="image-preview-modal__detail">
              <section className="image-preview-modal__detail-section">
                <h2 className="image-preview-modal__detail-label">
                  {t("imagePreview.instruction")}
                </h2>
                <p className="image-preview-modal__detail-text">
                  {currentPreviewHistory.instruction}
                </p>
              </section>
              <section className="image-preview-modal__detail-section">
                <h2 className="image-preview-modal__detail-label">
                  {t("imagePreview.generatedText")}
                </h2>
                <p className="image-preview-modal__detail-text">
                  {currentPreviewHistory.feelingText.trim() ||
                    t("imagePreview.noGeneratedText")}
                </p>
              </section>
            </div>
          ) : undefined
        }
      />
      {/* 精密参照の Anlas 追加消費の確認 */}
      <AnlasConfirmDialog
        open={anlasConfirmPending !== null}
        body={
          <Trans
            i18nKey="gameplay.anlasPreciseReferenceBody"
            values={{ cost: anlasConfirmPending?.anlasCost ?? 0 }}
            components={{ strong: <strong /> }}
          />
        }
        onConfirm={handleAnlasConfirm}
        onCancel={handleAnlasCancel}
      />

      {/* V5 利用上限使い切り警告ダイアログ */}
      <AnlasConfirmDialog
        open={usageWarnPending !== null}
        body={t("gameplay.v5UsageExhaustedBody")}
        onConfirm={handleUsageWarnConfirm}
        onCancel={handleUsageWarnCancel}
      />

      {/* メッセージ削除確認ダイアログ */}
      <ConfirmDialog
        open={deleteMessageConfirm !== null}
        title={t("gameplay.deleteMessageTitle")}
        confirmLabel={t("gameplay.deleteMessageAction")}
        cancelLabel={t("gameplay.deleteMessageCancel")}
        busy={isDeletingMessage}
        dismissible
        onConfirm={handleConfirmDeleteMessage}
        onCancel={() => setDeleteMessageConfirm(null)}
      >
        <p>{t("gameplay.deleteMessageConfirm")}</p>
        {deleteMessageConfirm?.responsePreview && (
          <p className="game-play-screen__delete-modal-preview">
            {t("gameplay.deleteMessageResponsePreview", {
              preview: deleteMessageConfirm.responsePreview,
            })}
          </p>
        )}
      </ConfirmDialog>

      {/* US2: 周囲状況画像拡大表示 */}
      {surroundingsOverlayUrl && (
        <ImageOverlay
          imageUrl={surroundingsOverlayUrl}
          alt="周囲状況画像"
          onClose={() => setSurroundingsOverlayUrl(null)}
        />
      )}

      {/* 最新メッセージ編集確認ダイアログ */}
      <ConfirmDialog
        open={editMessageConfirm !== null}
        title={t("gameplay.editMessageTitle")}
        confirmLabel={t("gameplay.editMessageAction")}
        cancelLabel={t("gameplay.editMessageCancel")}
        busy={isEditingMessage}
        dismissible
        onConfirm={handleConfirmEditMessage}
        onCancel={() => setEditMessageConfirm(null)}
      >
        <p>{t("gameplay.editMessageConfirm")}</p>
        {editMessageConfirm && (
          <p className="game-play-screen__delete-modal-preview">
            {editMessageConfirm.content.slice(0, 60)}
            {editMessageConfirm.content.length > 60 ? "..." : ""}
          </p>
        )}
      </ConfirmDialog>

      {/* 画面全体への画像ドロップ用オーバーレイ（表示のみ。drop 自体は window で受ける） */}
      {isFileDragging && (
        <FileDropOverlay
          testId="precise-ref-drop-overlay"
          unavailable={!canAddPreciseReference}
          title={
            canAddPreciseReference
              ? t("gameplay.preciseRefDropTitle")
              : t("rightPanel.preciseReferenceV5Unavailable")
          }
          hint={
            canAddPreciseReference
              ? t("gameplay.preciseRefDropHint")
              : undefined
          }
        />
      )}
    </MainLayout>
  );
}
