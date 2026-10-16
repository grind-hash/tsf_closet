import { useTranslation } from "react-i18next";
import { useInsertAtCaret } from "../../hooks/useInsertAtCaret";
import { useSubmitTextarea } from "../../hooks/useSubmitTextarea";
import { FavoritePromptInsertButton } from "../favoritePrompts/FavoritePromptButtons";

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
 * ボタンの disabled / Enter の判定で止める。攻略対象との雑談はキャラチャットへ移動して行う。
 * 通常プレイの入力欄と同じく、内容に合わせて縦に伸びる複数行入力にする
 * (Enter で送信、Shift+Enter で改行)。
 */
export default function AdventureFreeInput({
  value,
  onChange,
  onSubmit,
  busy,
}: AdventureFreeInputProps) {
  const { t } = useTranslation();
  const placeholder = t("adventure.freeInput");
  const canSubmit = value.trim() !== "" && !busy;
  const field = useSubmitTextarea({ value, canSubmit, onSubmit });
  const insertFavoritePrompt = useInsertAtCaret(
    field.ref,
    value,
    onChange,
    " ",
  );
  return (
    <form
      className="adventure-freeinput"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <textarea
        ref={field.ref}
        className="adventure-freeinput__field"
        value={value}
        rows={1}
        maxLength={1000}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={field.onKeyDown}
        placeholder={placeholder}
        aria-label={placeholder}
        title={t("adventure.freeInputHint")}
      />
      <FavoritePromptInsertButton
        onInsert={insertFavoritePrompt}
        className="adventure-freeinput__favorite"
        iconSize={16}
      />
      <button
        type="submit"
        className="adventure-freeinput__submit"
        disabled={!canSubmit}
      >
        {t("adventure.send")}
      </button>
    </form>
  );
}
