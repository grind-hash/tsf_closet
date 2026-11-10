import { useId } from "react";
import { useTranslation } from "react-i18next";

interface HakoniwaTagsFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** 保存済みのタグがプレイヤーの手直しか(説明から作ったタグなら false) */
  manual: boolean;
  /** 保存のときに説明から作り直すか */
  regenerate: boolean;
  onRegenerateChange: (regenerate: boolean) => void;
  placeholder?: string;
  /** 欄の下の説明を出すか(同じ説明が並ぶときは1つ目の欄だけに出す) */
  showNote?: boolean;
}

/**
 * 画像の生成に使うタグの欄(住民のいつもの姿・ドレス姿、自作の掟の見た目)。
 * 手で直したタグは説明を変えても上書きされず、「説明から作り直す」を押したときだけ
 * 保存で作り直す。作り直す間は欄を触れないようにする。
 */
export default function HakoniwaTagsField({
  label,
  value,
  onChange,
  manual,
  regenerate,
  onRegenerateChange,
  placeholder,
  showNote = true,
}: HakoniwaTagsFieldProps) {
  const { t } = useTranslation();
  const fieldId = useId();
  const noteId = useId();

  return (
    <div className="hakoniwa-field hakoniwa-tags-field">
      <div className="hakoniwa-tags-field__head">
        <label htmlFor={fieldId}>{label}</label>
        <span className="hakoniwa-badge">
          {t(manual ? "hakoniwa.tagsField.manual" : "hakoniwa.tagsField.auto")}
        </span>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost hakoniwa-tags-field__action"
          aria-pressed={regenerate}
          onClick={() => onRegenerateChange(!regenerate)}
        >
          {t(
            regenerate
              ? "hakoniwa.tagsField.cancelRegenerate"
              : "hakoniwa.tagsField.regenerate",
          )}
        </button>
      </div>
      <textarea
        id={fieldId}
        className="hakoniwa-tags-field__input"
        rows={3}
        value={value}
        placeholder={placeholder}
        disabled={regenerate}
        spellCheck={false}
        aria-describedby={regenerate || showNote ? noteId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {(regenerate || showNote) && (
        <p id={noteId} className="hakoniwa-note">
          {t(
            regenerate
              ? "hakoniwa.tagsField.regenerateNote"
              : "hakoniwa.tagsField.note",
          )}
        </p>
      )}
    </div>
  );
}

/**
 * タグの欄の入力から、保存に送る値を作る。手で変えていなければ null(手直し無し)。
 * 作り直すときもタグは送らない(説明から作る)。
 */
export function editedTags(
  value: string,
  saved: string,
  regenerate: boolean,
): string | null {
  if (regenerate) return null;
  return value.trim() === saved.trim() ? null : value.trim();
}
