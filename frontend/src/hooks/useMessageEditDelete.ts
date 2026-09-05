import { useCallback, useState } from "react";
import {
  deleteConversationMessage,
  deleteHistoryEntry,
  deleteLatestHistory,
} from "../apis/game";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import type { InstructionType, SessionStats } from "../types";
import { API_BASE } from "../utils/api";

export interface DeleteMessageConfirm {
  messageId: string;
  historyId?: string;
  conversationId?: string;
  responsePreview: string;
}

export interface EditMessageConfirm {
  messageId: string;
  content: string;
}

interface UseMessageEditDeleteOptions {
  /** 「修正して再生成」の再同期前に呼ぶ(復元済みフラグのリセット等) */
  onBeforeResync: () => void;
  /** セッション状態(画像 URL・履歴・stats)の再同期 */
  onSessionStart?: () => void | Promise<void>;
}

/**
 * チャットメッセージの削除(画像付き・会話のみ)と、最新メッセージの
 * 「修正して再生成」(最新履歴を削除して指示を入力欄へ戻す)。
 * 確認ダイアログの表示状態も持つ。
 */
export function useMessageEditDelete({
  onBeforeResync,
  onSessionStart,
}: UseMessageEditDeleteOptions) {
  const {
    state: gameState,
    setCurrentImage,
    setConversationHistory,
    removeHistoryEntry,
    updateStats,
    loadSessionCharacters,
  } = useGame();
  const {
    state: chatState,
    setMessages,
    getMessageHistoryId,
    setInputText,
    setInstructionType,
  } = useChat();
  const sessionId = gameState.sessionId;
  const chatHistory = gameState.conversationHistory;

  const [deleteConfirm, setDeleteConfirm] =
    useState<DeleteMessageConfirm | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editConfirm, setEditConfirm] = useState<EditMessageConfirm | null>(
    null,
  );
  const [editing, setEditing] = useState(false);

  // メッセージ削除の確認ダイアログを表示
  const requestDelete = useCallback(
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

        setDeleteConfirm({ messageId, historyId, responsePreview: preview });
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

        setDeleteConfirm({
          messageId,
          conversationId,
          responsePreview: preview,
        });
      }
    },
    [chatState.messages, getMessageHistoryId],
  );

  // メッセージ削除を実行
  const confirmDelete = useCallback(async () => {
    if (!deleteConfirm) return;

    const { messageId, historyId, conversationId } = deleteConfirm;

    try {
      setDeleting(true);

      if (historyId) {
        // 画像付きメッセージ: 履歴エントリを完全削除(History + 画像 + 会話テキスト)
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

        // GameContext の history からもエントリを除去(画像表示を更新)
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

      setDeleteConfirm(null);
    } catch (err) {
      console.error("Failed to delete message:", err);
      setDeleteConfirm(null);
    } finally {
      setDeleting(false);
    }
  }, [
    deleteConfirm,
    chatState.messages,
    setMessages,
    sessionId,
    removeHistoryEntry,
    updateStats,
    chatHistory,
    setConversationHistory,
    loadSessionCharacters,
  ]);

  const cancelDelete = useCallback(() => setDeleteConfirm(null), []);

  // 最新メッセージ編集リクエスト(確認ダイアログを表示)
  const requestEdit = useCallback(
    (messageId: string, content: string) => {
      // Temporary guard: right after sending, the ID is still a timestamp (not UUID).
      const historyId = getMessageHistoryId(messageId);
      if (!historyId) {
        return;
      }
      setEditConfirm({ messageId, content });
    },
    [getMessageHistoryId],
  );

  // 最新メッセージ編集を確定して実行
  const confirmEdit = useCallback(async () => {
    if (!editConfirm || !sessionId) return;

    const { messageId, content } = editConfirm;
    const historyId = getMessageHistoryId(messageId);
    if (!historyId) {
      return;
    }

    try {
      setEditing(true);

      // Backend: delete latest history
      const result = await deleteLatestHistory(sessionId);

      // Chat messages: remove user message + corresponding feeling message
      // (both carry relatedHistoryId of the deleted history)
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
      // Reset the message restoration flag so the messages will be rebuilt
      // from fresh history + chatHistory after restoreSession.
      onBeforeResync();
      if (onSessionStart) {
        await onSessionStart();
      }

      // 履歴削除に伴いバックエンドが SessionCharacter の外見を最新履歴に
      // 復帰するため、フロント側のキャラクターパネル表示も再同期する。
      void loadSessionCharacters();

      setEditConfirm(null);
    } catch (err) {
      console.error("Failed to edit message:", err);
      setEditConfirm(null);
    } finally {
      setEditing(false);
    }
  }, [
    editConfirm,
    sessionId,
    chatState.messages,
    setMessages,
    getMessageHistoryId,
    setInputText,
    setInstructionType,
    setCurrentImage,
    onBeforeResync,
    onSessionStart,
    loadSessionCharacters,
  ]);

  const cancelEdit = useCallback(() => setEditConfirm(null), []);

  return {
    deleteConfirm,
    deleting,
    requestDelete,
    confirmDelete,
    cancelDelete,
    editConfirm,
    editing,
    requestEdit,
    confirmEdit,
    cancelEdit,
  };
}

export type UseMessageEditDeleteResult = ReturnType<
  typeof useMessageEditDelete
>;
