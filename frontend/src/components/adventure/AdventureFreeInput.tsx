import { useTranslation } from "react-i18next";
import type { SpeechInputErrorCode } from "../../hooks/useSpeechInput";

export interface AdventureFreeInputSpeech {
  supported: boolean;
  listening: boolean;
  autoSend: boolean;
  error: SpeechInputErrorCode | null;
  onToggleListening: () => void;
  onToggleAutoSend: () => void;
}

interface AdventureFreeInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** トークモードでは文字数上限・プレースホルダとマイクの出し分けが変わる */
  talkMode: boolean;
  partnerName: string;
  /** 送信中(streaming / talking)。入力自体は許可し、送信だけ止める */
  busy: boolean;
  speech: AdventureFreeInputSpeech;
}

/**
 * 常設の自由入力欄。streaming 中も入力自体は許可し(無効化するとフォーカスが
 * 外れて次の数字キーが選択肢送信になる)、送信は呼び出し側のガードと
 * ボタンの disabled で止める。
 */
export default function AdventureFreeInput({
  value,
  onChange,
  onSubmit,
  talkMode,
  partnerName,
  busy,
  speech,
}: AdventureFreeInputProps) {
  const { t } = useTranslation();
  const placeholder = talkMode
    ? t("adventure.talk.placeholder", { name: partnerName })
    : t("adventure.freeInput");
  return (
    <>
      <form
        className="adventure-freeinput"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <input
          type="text"
          className="adventure-freeinput__field"
          value={value}
          maxLength={talkMode ? 500 : 1000}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          title={t(
            talkMode ? "adventure.talk.hint" : "adventure.freeInputHint",
          )}
          enterKeyHint="send"
        />
        {talkMode && speech.supported && (
          <>
            <button
              type="button"
              className={`adventure-freeinput__mic${
                speech.listening ? " is-listening" : ""
              }`}
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
              className={`adventure-freeinput__autosend${
                speech.autoSend ? " is-on" : ""
              }`}
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
          className="adventure-freeinput__submit"
          disabled={!value.trim() || busy}
        >
          {t("adventure.send")}
        </button>
      </form>
      {talkMode && speech.error && (
        <p className="adventure-freeinput__mic-error" role="status">
          {t(`adventure.mic.error.${speech.error}`)}
        </p>
      )}
    </>
  );
}
