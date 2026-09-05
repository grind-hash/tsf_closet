import { useCallback, useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { fetchFavorites, toggleFavorite } from "../apis/favorites";

import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import { useNotification } from "../contexts/NotificationContext";
import { useSettings } from "../contexts/SettingsContext";
import { useConversationStream } from "../hooks/useConversationStream";
import { useFeelingMessages } from "../hooks/useFeelingMessages";
import { useMessageEditDelete } from "../hooks/useMessageEditDelete";
import {
  PRECISE_REFERENCE_SECTION_ID,
  usePreciseReferenceFiles,
} from "../hooks/usePreciseReferenceFiles";
import { useRestoredChatMessages } from "../hooks/useRestoredChatMessages";
import { useSessionExport } from "../hooks/useSessionExport";
import {
  resolveTransformKinds,
  type TransformHandler,
  type TransformOptions,
  useTransformRequest,
} from "../hooks/useTransformRequest";
import { useWindowFileDrop } from "../hooks/useWindowFileDrop";
import type { ChatMessage, InstructionType } from "../types";
import { generateUUID } from "../utils/generateUUID";
import { readStorageFlag } from "../utils/storage";
import AnlasBar from "./AnlasBar";
import AudioControlBar from "./chat/AudioControlBar";
import ChatExportHeader from "./chat/ChatExportHeader";
import ChatInput, { SUGGEST_USE_MEMORY_STORAGE_KEY } from "./chat/ChatInput";
import ChatMessageList from "./chat/ChatMessageList";
import MessageEditDeleteDialogs from "./chat/MessageEditDeleteDialogs";
import WelcomeScreen from "./chat/WelcomeScreen";
import ImagePreviewModal from "./ImagePreviewModal";
import InpaintModal from "./InpaintModal";
import MainLayout from "./layout/MainLayout";
import RightPanel from "./layout/RightPanel";
import CharacterPanel from "./panel/CharacterPanel";
import CharacterStatePanel from "./panel/CharacterStatePanel";
import AnlasConfirmDialog from "./ui/AnlasConfirmDialog";
import FileDropOverlay from "./ui/FileDropOverlay";
import ImageOverlay from "./ui/ImageOverlay";
import "./GamePlayScreen.css";
import "./chat/ChatContainer.css";

// 通常ゲームのプレイ画面。画像・履歴・チャットを束ね、送信の振り分け
// (会話 → useConversationStream / 変身 → useTransformRequest)と各モーダルの開閉を持つ。
// チャット欄の復元・心境メッセージ・削除/修正・エクスポートはそれぞれの hook に分けている。

interface GamePlayScreenProps {
  onTransform: TransformHandler;
  onResetCost: () => void;
  onSessionStart?: () => void;
}

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
    navigatePrevHistory,
    navigateNextHistory,
  } = useGame();
  const {
    state: chatState,
    addMessage,
    upsertPendingIdentity,
    clearInput,
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
  const isTransforming = gameState.isTransforming;
  const totalCost = settingsState.totalCost;
  const showCost = settingsState.showCost;
  const imageProvider = settingsState.imageProvider;
  const lastGeneratedSeed = gameState.lastGeneratedSeed;
  const anlasBalance = settingsState.anlasBalance;

  // 右パネル開閉状態はSettingsContext経由でlocalStorageに保存
  const showRightPanel = settingsState.rightPanelOpen;
  const uiText = useMemo(
    () => ({
      apiCost: t("gameplay.apiCost"),
      resetCost: t("gameplay.resetCost"),
      maskConfigured: t("gameplay.maskConfigured"),
      imageAlt: t("gameplay.imageAlt"),
    }),
    [t],
  );

  // NovelAI インペイント関連
  const [showInpaintModal, setShowInpaintModal] = useState(false);
  const { maskDataUrl, selectedMaskId } = settingsState.inpaintMask;
  // inpaintSettingsはSettingsContextから取得(RightPanelと同期するため)
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

  const chatExport = useSessionExport({
    messages: chatState.messages,
    sessionId,
    characterName: gameState.character?.name,
  });

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

  // チャット履歴を統合して復元(history + chatHistory を時系列順に統合)
  const { resetRestoration } = useRestoredChatMessages(isNewGameRoute);
  // 心境テキストと周囲状況画像をチャットメッセージへ反映
  useFeelingMessages();
  // メッセージ削除と「修正して再生成」
  const editDelete = useMessageEditDelete({
    onBeforeResync: resetRestoration,
    onSessionStart,
  });
  const { streamConversation } = useConversationStream();
  const transformRequest = useTransformRequest(onTransform);

  // 右パネルトグル(SettingsContext経由でlocalStorageに永続化)
  const handleToggleRightPanel = useCallback(() => {
    togglePanel();
  }, [togglePanel]);

  // 画面全体への画像ドロップ → 精密参照画像に追加(NovelAI 選択時のみ受け付ける)
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
        // 右パネルを開き、描画後に精密参照セクションへスクロールする(下の effect)
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

  /** ユーザーの指示メッセージをチャットへ積み、pending identity を登録する */
  const pushUserMessage = useCallback(
    (message: string, instructionType: string, currentSessionId: string) => {
      const now = new Date().toISOString();
      const tempToken = generateUUID();
      const userMsg: ChatMessage = {
        id: `user-${tempToken}`,
        sessionId: currentSessionId,
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
      return { userMsg, tempToken };
    },
    [addMessage, upsertPendingIdentity],
  );

  // チャット送信ハンドラ
  const handleSendMessage = useCallback(
    async (message: string, instructionType: string, useMemory: boolean) => {
      if (!sessionId || isTransforming) return;
      const { userMsg, tempToken } = pushUserMessage(
        message,
        instructionType,
        sessionId,
      );
      if (instructionType === "conversation") {
        // 会話のみ(ストリーミング対応)
        await streamConversation(message, userMsg);
        return;
      }
      // action / dress_up / reality_alter / image_only -> play/stream
      transformRequest.submitTransform(
        message,
        instructionType,
        useMemory,
        tempToken,
      );
    },
    [
      sessionId,
      isTransforming,
      pushUserMessage,
      streamConversation,
      transformRequest.submitTransform,
    ],
  );

  // 画像クリック時のハンドラ(画像プレビューモーダル表示)
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

      const { tempToken } = pushUserMessage(
        message,
        instructionType,
        sessionId,
      );
      const { transformationType, backendInstructionType } =
        resolveTransformKinds(instructionType);

      // prompt_override を含むオプションでtransformを実行
      const transformOptions: TransformOptions = {
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
      pushUserMessage,
      onTransform,
      imageProvider,
      inpaintSettings,
      settingsState.inpaintEnabled,
      maskDataUrl,
      selectedMaskId,
      clearInput,
    ],
  );

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
          <AnlasBar balance={anlasBalance} showUsage={isNovelaiV5Active} />
        )}
        {!isSessionActive ? (
          <WelcomeScreen onSessionStart={onSessionStart} />
        ) : (
          <div className="game-play-screen__content">
            {/* 左カラム: キャラクター状態パネル(縦レイアウト) */}
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
              {chatState.messages.length > 0 && (
                <ChatExportHeader
                  menuOpen={chatExport.menuOpen}
                  onToggleMenu={chatExport.toggleMenu}
                  menuRef={chatExport.menuRef}
                  progress={chatExport.progress}
                  onExport={chatExport.exportAs}
                />
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
                  onDeleteMessage={editDelete.requestDelete}
                  onEditMessage={editDelete.requestEdit}
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
            // SettingsContextのinpaintSettingsを更新(RightPanelと同期)
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
        open={transformRequest.anlasConfirmPending !== null}
        body={
          <Trans
            i18nKey="gameplay.anlasPreciseReferenceBody"
            values={{
              cost: transformRequest.anlasConfirmPending?.anlasCost ?? 0,
            }}
            components={{ strong: <strong /> }}
          />
        }
        onConfirm={transformRequest.handleAnlasConfirm}
        onCancel={transformRequest.handleAnlasCancel}
      />

      {/* V5 利用上限使い切り警告ダイアログ */}
      <AnlasConfirmDialog
        open={transformRequest.usageWarnPending !== null}
        body={t("gameplay.v5UsageExhaustedBody")}
        onConfirm={transformRequest.handleUsageWarnConfirm}
        onCancel={transformRequest.handleUsageWarnCancel}
      />

      {/* メッセージ削除・修正の確認ダイアログ */}
      <MessageEditDeleteDialogs controller={editDelete} />

      {/* US2: 周囲状況画像拡大表示 */}
      {surroundingsOverlayUrl && (
        <ImageOverlay
          imageUrl={surroundingsOverlayUrl}
          alt="周囲状況画像"
          onClose={() => setSurroundingsOverlayUrl(null)}
        />
      )}

      {/* 画面全体への画像ドロップ用オーバーレイ(表示のみ。drop 自体は window で受ける) */}
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
