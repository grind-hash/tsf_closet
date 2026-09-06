import { useTranslation } from "react-i18next";

interface AdventureFreeInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** 送信中(streaming)。入力自体は許可し、送信だけ止める */
  busy: boolean;
}

/**
 * 常設の自由入力欄。streaming 中も入力自体は許可し(無効化するとフォーカスが
 * 外れて次の数字キーが選択肢送信になる)、送信は呼び出し側のガードと
 * ボタンの disabled で止める。攻略対象との雑談はキャラチャットへ移動して行う。
 */
export default function AdventureFreeInput({
  value,
  onChange,
  onSubmit,
  busy,
}: AdventureFreeInputProps) {
  const { t } = useTranslation();
  const placeholder = t("adventure.freeInput");
  return (
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
        maxLength={1000}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        title={t("adventure.freeInputHint")}
        enterKeyHint="send"
      />
      <button
        type="submit"
        className="adventure-freeinput__submit"
        disabled={!value.trim() || busy}
      >
        {t("adventure.send")}
      </button>
    </form>
  );
}
