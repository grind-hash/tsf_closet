import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  HakoniwaGender,
  HakoniwaMemoLookGroup,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";

/** 本来の性別の並び(バックエンドの groups と同じ) */
export const MEMO_LOOK_GENDERS = ["female", "male"] as const;
type BodyOption = "keep" | HakoniwaGender;

/** 体の選択肢。本来と同じ性別にしても変わらないので、変えないか、もう一方の性別か */
function bodyOptions(gender: HakoniwaGender): BodyOption[] {
  return ["keep", gender === "female" ? "male" : "female"];
}
/** タグの長さの上限(バックエンドの HAKONIWA_MANUAL_TAGS_INPUT_MAX と同じ) */
const TAGS_MAX_LENGTH = 2000;

interface GroupDraft {
  tags: string;
  body: BodyOption;
}

function toDraft(group: HakoniwaMemoLookGroup | null | undefined): GroupDraft {
  return { tags: group?.tags ?? "", body: group?.body_gender ?? "keep" };
}

/** タグが空で体も変えない性別は、姿が変わらない(null) */
function toGroup(draft: GroupDraft): HakoniwaMemoLookGroup | null {
  const tags = draft.tags.trim();
  const body = draft.body === "keep" ? null : draft.body;
  return tags || body ? { tags, body_gender: body } : null;
}

/**
 * 世界のメモの姿を、住民の本来の性別ごとに手で直すダイアログ。
 * LLM の判断が外れたときに、見た目のタグと体の性別を決め直す。保存すると、姿が変わる
 * 住民のうち、まだ(または直す前の姿)の住民の姿を描く
 */
export default function HakoniwaMemoLookDialog({
  onClose,
}: {
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { world, busy, saveMemoLook } = useHakoniwa();
  const idBase = useId();
  const groups = world?.memo_look?.groups;
  const [drafts, setDrafts] = useState<Record<HakoniwaGender, GroupDraft>>(
    () => ({
      female: toDraft(groups?.female),
      male: toDraft(groups?.male),
    }),
  );

  const update = (gender: HakoniwaGender, change: Partial<GroupDraft>) => {
    setDrafts((current) => ({
      ...current,
      [gender]: { ...current[gender], ...change },
    }));
  };

  return (
    <ConfirmDialog
      open
      className="hakoniwa-form-dialog"
      title={t("hakoniwa.settings.memoLookEditTitle")}
      confirmLabel={t("hakoniwa.settings.memoLookEditSave")}
      cancelLabel={t("hakoniwa.residentForm.cancel")}
      busy={busy === "settings"}
      onCancel={onClose}
      onConfirm={() => {
        void saveMemoLook({
          female: toGroup(drafts.female),
          male: toGroup(drafts.male),
        }).then((saved) => {
          if (saved) onClose();
        });
      }}
    >
      <div className="hakoniwa-form">
        <HakoniwaErrorBanner placement="dialog" clearOnMount />
        <p className="hakoniwa-note">
          {t("hakoniwa.settings.memoLookEditNote")}
        </p>
        {MEMO_LOOK_GENDERS.map((gender) => {
          const draft = drafts[gender];
          const tagsId = `${idBase}-${gender}-tags`;
          const bodyId = `${idBase}-${gender}-body`;
          return (
            <fieldset key={gender} className="hakoniwa-memo-look-group">
              <legend>{t(`hakoniwa.settings.memoLookGroup.${gender}`)}</legend>
              <label className="hakoniwa-field" htmlFor={tagsId}>
                <span>{t("hakoniwa.settings.memoLookEditTags")}</span>
                <textarea
                  id={tagsId}
                  rows={2}
                  value={draft.tags}
                  maxLength={TAGS_MAX_LENGTH}
                  placeholder={t(
                    "hakoniwa.settings.memoLookEditTagsPlaceholder",
                  )}
                  onChange={(event) =>
                    update(gender, { tags: event.target.value })
                  }
                />
              </label>
              <div className="hakoniwa-field">
                <span id={bodyId}>{t("hakoniwa.rules.body")}</span>
                <div
                  className="hakoniwa-segments"
                  role="group"
                  aria-labelledby={bodyId}
                >
                  {bodyOptions(gender).map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={
                        draft.body === option ? "is-active" : undefined
                      }
                      aria-pressed={draft.body === option}
                      onClick={() => update(gender, { body: option })}
                    >
                      {t(`hakoniwa.rules.bodyOption.${option}`)}
                    </button>
                  ))}
                </div>
              </div>
            </fieldset>
          );
        })}
      </div>
    </ConfirmDialog>
  );
}
