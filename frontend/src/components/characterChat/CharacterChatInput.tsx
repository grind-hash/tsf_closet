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
  return (
    <div className="character-chat__input-wrap">
      <form
        className="character-chat__input"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <input
          type="text"
          className="character-chat__input-field"
          value={value}
          maxLength={1000}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          title={t("characterChat.input.hint")}
          enterKeyHint="send"
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
          disabled={!value.trim() || busy}
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
