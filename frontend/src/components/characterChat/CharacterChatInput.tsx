import { type KeyboardEvent, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { SpeechInputErrorCode } from "../../hooks/useSpeechInput";

export interface CharacterChatInputSpeech {
  supported: boolean;
  listening: boolean;
  autoSend: boolean;
  error: SpeechInputErrorCode | null;
  onToggleListening: () => void;
  onToggleAutoSend: () => void;
}

interface CharacterChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  name: string;
  /** 送信中。入力自体は許可し、送信だけ止める(無効化するとフォーカスが外れる) */
  busy: boolean;
  speech: CharacterChatInputSpeech;
}

/**
 * メッセージ窓の下端の入力欄。通常プレイの入力欄と同じく、内容に合わせて縦に伸びる
 * 複数行入力にする(上限は CSS の max-height、超えた分は欄の中でスクロール)。
 */
export default function CharacterChatInput({
  value,
  onChange,
  onSubmit,
  name,
  busy,
  speech,
}: CharacterChatInputProps) {
  const { t } = useTranslation();
  const placeholder = t("characterChat.input.placeholder", { name });
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const canSubmit = value.trim() !== "" && !busy;

  // 音声入力や送信後のクリアで値が変わったときも高さを合わせる
  useLayoutEffect(() => {
    const field = fieldRef.current;
    if (!field) return;
    // value の変更をトリガーに高さを再計算する
    void value;
    field.style.height = "auto";
    // 窓を隠している間(display: none)は測れないため、1 行の高さのままにする
    if (field.scrollHeight === 0) return;
    // box-sizing: border-box なので、内容の高さに上下の枠線を足す
    field.style.height = `${field.scrollHeight + field.offsetHeight - field.clientHeight}px`;
  }, [value]);

  // Enter で送信、Shift+Enter で改行。変換中の Enter は確定に使う。
  // タッチ端末(pointer: coarse)では通常プレイの入力欄と同じく Enter を改行にする
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing ||
      !window.matchMedia("(pointer: fine)").matches
    ) {
      return;
    }
    event.preventDefault();
    if (canSubmit) onSubmit();
  };

  return (
    <div className="character-chat__input-wrap">
      <form
        className="character-chat__input"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <textarea
          ref={fieldRef}
          className="character-chat__input-field"
          value={value}
          rows={1}
          maxLength={1000}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label={placeholder}
          title={t("characterChat.input.hint")}
        />
        {speech.supported && (
          <>
            <button
              type="button"
              className={`character-chat__mic${speech.listening ? " is-listening" : ""}`}
              disabled={busy}
              aria-pressed={speech.listening}
              aria-label={t(
                speech.listening
                  ? "adventure.mic.listening"
                  : "adventure.mic.start",
              )}
              title={t(
                speech.listening
                  ? "adventure.mic.listening"
                  : "adventure.mic.startHint",
              )}
              onClick={speech.onToggleListening}
            >
              🎤
            </button>
            <button
              type="button"
              className={`character-chat__autosend${speech.autoSend ? " is-on" : ""}`}
              aria-pressed={speech.autoSend}
              title={t("adventure.mic.autoSendHint")}
              onClick={speech.onToggleAutoSend}
            >
              {t("adventure.mic.autoSend")}
            </button>
          </>
        )}
        <button
          type="submit"
          className="character-chat__send"
          disabled={!canSubmit}
        >
          {t("characterChat.input.send")}
        </button>
      </form>
      {speech.error && (
        <p className="character-chat__mic-error" role="status">
          {t(`adventure.mic.error.${speech.error}`)}
        </p>
      )}
    </div>
  );
}
