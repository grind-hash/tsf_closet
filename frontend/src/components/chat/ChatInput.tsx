/**
 * ChatInput - チャット入力コンポーネント
 * 007-chat-interactive-ux
 *
 * 構成:
 * - InstructionTypeSelect: 指示タイプ選択
 * - TextInput: テキスト入力
 * - FileAttachButton: ファイル添付
 * - SendButton: 送信
 */

import {
  useRef,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { useNotification } from "../../contexts/NotificationContext";
import { suggestInstruction } from "../../apis/game";
import type { InstructionType } from "../../types";
import "./ChatInput.css";

interface ChatInputProps {
  onSendMessage?: (message: string, instructionType: string) => void;
  disabled?: boolean;
  imageProvider?: string;
}

export default function ChatInput({
  onSendMessage,
  disabled = false,
  imageProvider,
}: ChatInputProps) {
  const { t, i18n } = useTranslation();
  const { state, setInputText, setInstructionType, attachImage, clearInput } =
    useChat();
  const { state: gameState } = useGame();
  const { showNotification } = useNotification();

  // 過去メッセージからの指示テキスト生成
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [filterByType, setFilterByType] = useState(false);
  const canFilterByType = state.instructionType !== "conversation";

  const handleSuggestInstruction = async () => {
    if (!gameState.sessionId || isSuggesting || disabled) return;
    setIsSuggesting(true);
    try {
      const typeFilter =
        filterByType && canFilterByType ? state.instructionType : "all";
      const language = i18n.language?.startsWith("en") ? "en" : "ja";
      const keyword = state.inputText.trim();
      const suggestion = await suggestInstruction(
        gameState.sessionId,
        typeFilter,
        language,
        keyword,
      );
      setInputText(suggestion);
    } catch {
      showNotification(
        "error",
        t("chat.input.suggestError"),
        t("chat.input.suggestErrorDetail"),
      );
    } finally {
      setIsSuggesting(false);
    }
  };

  // Detect narrow viewport for short labels
  const [isNarrow, setIsNarrow] = useState(
    typeof window !== "undefined" && window.innerWidth <= 900,
  );
  useEffect(() => {
    const handleResize = () => setIsNarrow(window.innerWidth <= 900);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // pointer:fine = mouse/trackpad; pointer:coarse = touch screen
  // タッチデバイスでは Enter キーを送信ではなく改行として扱う
  const hasPointerFine =
    typeof window !== "undefined" &&
    window.matchMedia("(pointer: fine)").matches;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // disabled状態になったらフォーカスを外す（カーソル点滅を停止）
  useEffect(() => {
    if (disabled && textareaRef.current) {
      textareaRef.current.blur();
    }
  }, [disabled]);

  // 生成ボタン等でプログラム的にtextareaの値が変わった場合も高さを自動調整する
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [state.inputText]);

  // 送信ハンドラ
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!state.inputText.trim() || disabled) return;

    onSendMessage?.(state.inputText.trim(), state.instructionType);
    clearInput();

    // テキストエリアにフォーカスを戻す
    textareaRef.current?.focus();
  };

  // Enter送信（Shift+Enterで改行）
  // タッチデバイス（pointer:coarse）では Enter を素通りさせて改行とする
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      !e.nativeEvent.isComposing &&
      hasPointerFine
    ) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // ファイル選択ハンドラ
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      attachImage(file);
    }
    // 同じファイルを再選択できるようにリセット
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // 添付画像削除
  const handleRemoveAttachment = () => {
    attachImage(null);
  };

  // テキストエリアの値変更（高さ調整はuseEffectで一元化）
  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
  };

  const getInstructionTypeLabel = (type: InstructionType) => {
    switch (type) {
      case "dress_up":
        return isNarrow
          ? t("chat.instructionType.dressUpShort")
          : t("chat.instructionType.dressUp");
      case "reality_alter":
        return isNarrow
          ? t("chat.instructionType.realityAlterShort")
          : t("chat.instructionType.realityAlter");
      case "conversation":
        return isNarrow
          ? t("chat.instructionType.conversationShort")
          : t("chat.instructionType.conversation");
      case "action":
        return isNarrow
          ? t("chat.instructionType.actionShort")
          : t("chat.instructionType.action");
      default:
        return type;
    }
  };

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      {/* 添付画像プレビュー */}
      {state.attachedImagePreview && (
        <div className="chat-input__attachment-preview">
          <img
            src={state.attachedImagePreview}
            alt={t("chat.input.attachmentPreviewAlt")}
            className="chat-input__attachment-image"
          />
          <button
            type="button"
            className="chat-input__attachment-remove"
            onClick={handleRemoveAttachment}
            aria-label={t("chat.input.removeAttachment")}
          >
            ✕
          </button>
        </div>
      )}

      <div className="chat-input__row">
        {/* 指示タイプ選択 */}
        <select
          className="chat-input__type-select"
          value={state.instructionType}
          onChange={(e) =>
            setInstructionType(e.target.value as InstructionType)
          }
          disabled={disabled}
          aria-label={t("chat.input.instructionTypeAria")}
        >
          {(
            [
              "dress_up",
              "reality_alter",
              "conversation",
              "action",
            ] as InstructionType[]
          ).map((type) => (
            <option key={type} value={type}>
              {getInstructionTypeLabel(type)}
            </option>
          ))}
        </select>

        {/* テキスト入力 */}
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          value={state.inputText}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={
            hasPointerFine
              ? t("chat.input.messagePlaceholder")
              : t("chat.input.messagePlaceholderTouch", "指示を入力...")
          }
          disabled={disabled}
          rows={1}
          aria-label={t("chat.input.messageInputAria")}
        />

        {/* 過去メッセージから指示テキストを生成 */}
        <label
          className="chat-input__suggest-filter"
          title={t("chat.input.suggestFilterLabel")}
        >
          <input
            type="checkbox"
            checked={filterByType && canFilterByType}
            disabled={!canFilterByType || disabled}
            onChange={(e) => setFilterByType(e.target.checked)}
          />
          <span>{t("chat.input.suggestFilterLabel")}</span>
        </label>
        <button
          type="button"
          className="chat-input__suggest-btn"
          onClick={handleSuggestInstruction}
          disabled={disabled || isSuggesting || !gameState.sessionId}
          aria-label={t("chat.input.suggestInstruction")}
          title={t("chat.input.suggestInstruction")}
        >
          {isSuggesting ? (
            <span className="chat-input__suggest-spinner" />
          ) : (
            "✨"
          )}
        </button>

        {/* File attach - hidden in NovelAI mode */}
        {imageProvider !== "novelai" && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="chat-input__file-input"
              disabled={disabled}
            />
            <button
              type="button"
              className="chat-input__attach-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              aria-label={t("chat.input.attachImage")}
            >
              📎
            </button>
          </>
        )}

        {/* 送信ボタン */}
        <button
          type="submit"
          className="chat-input__send-btn"
          disabled={disabled || !state.inputText.trim()}
          aria-label={t("chat.input.send")}
        >
          {t("chat.input.send")}
        </button>
      </div>
    </form>
  );
}
