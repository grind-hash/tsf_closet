import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaTagsOutcome } from "../../contexts/HakoniwaContext";

/** タグの長さの上限(バックエンドの HAKONIWA_TAGS_MAX_LENGTH・プレイの appearance_tags と同じ) */
const TAGS_MAX_LENGTH = 2000;

interface HakoniwaLookFieldsProps {
  descriptionLabel: string;
  description: string;
  onDescriptionChange: (value: string) => void;
  descriptionPlaceholder?: string;
  descriptionMax: number;
  /** 説明の欄の下に出す注意書き */
  note?: string;
  tagsLabel: string;
  tags: string;
  onTagsChange: (value: string) => void;
  /** タグが空のときの扱いを伝える文 */
  tagsPlaceholder?: string;
  /** タグを必須にするか(見出しに「必須」を出す) */
  required?: boolean;
  /** タグの欄の下の説明を出すか(同じ説明が並ぶときは1つ目だけに出す) */
  showTagsNote?: boolean;
  /** タグを作る元の文があるか(無ければボタンを押せない) */
  canMake: boolean;
  /** タグを作る。成功したらタグの欄に入れる */
  onMake: () => Promise<HakoniwaTagsOutcome>;
  /** タグを作っている間を親へ伝える(保存を止める) */
  onMakingChange?: (making: boolean) => void;
}

/**
 * 見た目の説明と、画像の生成にそのまま使うタグの欄。
 * 「説明からタグを作る」を押したときだけ説明からタグを作り、タグの欄に入れる(保存はしない)。
 */
export default function HakoniwaLookFields({
  descriptionLabel,
  description,
  onDescriptionChange,
  descriptionPlaceholder,
  descriptionMax,
  note,
  tagsLabel,
  tags,
  onTagsChange,
  tagsPlaceholder,
  required = false,
  showTagsNote = true,
  canMake,
  onMake,
  onMakingChange,
}: HakoniwaLookFieldsProps) {
  const { t } = useTranslation();
  const descriptionId = useId();
  const tagsId = useId();
  const [making, setMaking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // タグを最後に作った(開いたときは保存済みの)説明。変えたら作り直しを促す
  const [madeFrom, setMadeFrom] = useState(description);
  const descriptionChanged =
    description.trim() !== madeFrom.trim() && description.trim() !== "";

  const handleMake = async () => {
    setMaking(true);
    onMakingChange?.(true);
    setError(null);
    const outcome = await onMake();
    if (outcome.error === null) {
      onTagsChange(outcome.tags);
      setMadeFrom(description);
    } else {
      setError(outcome.error);
    }
    setMaking(false);
    onMakingChange?.(false);
  };

  return (
    <>
      <div className="hakoniwa-field">
        <div className="hakoniwa-look-fields__head">
          <label htmlFor={descriptionId}>{descriptionLabel}</label>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost hakoniwa-look-fields__action"
            disabled={making || !canMake}
            title={canMake ? undefined : t("hakoniwa.lookFields.needSource")}
            onClick={() => void handleMake()}
          >
            {making ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.lookFields.making")}
              </>
            ) : (
              t("hakoniwa.lookFields.make")
            )}
          </button>
        </div>
        <textarea
          id={descriptionId}
          rows={2}
          value={description}
          maxLength={descriptionMax}
          placeholder={descriptionPlaceholder}
          onChange={(event) => onDescriptionChange(event.target.value)}
        />
      </div>
      {note && <p className="hakoniwa-note">{note}</p>}
      <div className="hakoniwa-field">
        <div className="hakoniwa-look-fields__head">
          <label htmlFor={tagsId}>{tagsLabel}</label>
          {required && (
            <span className="hakoniwa-badge">
              {t("hakoniwa.lookFields.required")}
            </span>
          )}
        </div>
        <textarea
          id={tagsId}
          className="hakoniwa-look-fields__tags"
          rows={3}
          value={tags}
          maxLength={TAGS_MAX_LENGTH}
          placeholder={tagsPlaceholder}
          spellCheck={false}
          required={required}
          onChange={(event) => onTagsChange(event.target.value)}
        />
      </div>
      {error && (
        <p className="hakoniwa-note hakoniwa-note--error" role="alert">
          {error}
        </p>
      )}
      {descriptionChanged && !making && (
        <p className="hakoniwa-note hakoniwa-note--warning">
          {t("hakoniwa.lookFields.descriptionChanged")}
        </p>
      )}
      {showTagsNote && (
        <p className="hakoniwa-note">{t("hakoniwa.lookFields.tagsNote")}</p>
      )}
    </>
  );
}
