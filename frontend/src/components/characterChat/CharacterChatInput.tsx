import { useTranslation } from "react-i18next";
import type { SpeechInputErrorCode } from "../../hooks/useSpeechInput";
import { useSubmitTextarea } from "../../hooks/useSubmitTextarea";

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
 * 複数行入力にする(Enter で送信、Shift+Enter で改行)。
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
  const canSubmit = value.trim() !== "" && !busy;
  const field = useSubmitTextarea({ value, canSubmit, onSubmit });

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
          ref={field.ref}
          className="character-chat__input-field"
          value={value}
          rows={1}
          maxLength={1000}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={field.onKeyDown}
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
