import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaGender, HakoniwaResident } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import { GenderSegments } from "./HakoniwaCharacterAdder";

const NAME_MAX = 30;
const PERSONALITY_MAX = 300;
const APPEARANCE_MAX = 300;

interface HakoniwaResidentModalProps {
  /** 編集する住民。null なら新しく迎える */
  resident: HakoniwaResident | null;
  onClose: () => void;
}

/**
 * 住民の追加・編集。外見の説明はプレイヤーの文章のまま保存し、画像のタグは
 * バックエンドが別に作る(タグは読み取り専用で見せる)。
 */
export default function HakoniwaResidentModal({
  resident,
  onClose,
}: HakoniwaResidentModalProps) {
  const { t } = useTranslation();
  const { saveResident, busy } = useHakoniwa();
  const nameId = useId();
  const personalityId = useId();
  const genderId = useId();
  const appearanceId = useId();
  const dressId = useId();
  const [name, setName] = useState(resident?.name ?? "");
  const [personality, setPersonality] = useState(resident?.personality ?? "");
  const [gender, setGender] = useState<HakoniwaGender>(
    resident?.gender ?? "female",
  );
  const [appearance, setAppearance] = useState(resident?.appearance_text ?? "");
  const [dress, setDress] = useState(resident?.dress_text ?? "");
  const saving = busy === "resident";

  const handleSave = async () => {
    const saved = await saveResident(
      {
        name: name.trim(),
        personality: personality.trim(),
        gender,
        appearance_text: appearance.trim(),
        dress_text: dress.trim(),
      },
      resident?.id,
    );
    if (saved) onClose();
  };

  return (
    <ConfirmDialog
      open
      className="hakoniwa-form-dialog"
      title={
        resident
          ? t("hakoniwa.residentForm.titleEdit")
          : t("hakoniwa.residentForm.titleAdd")
      }
      confirmLabel={
        saving
          ? t("hakoniwa.residentForm.saving")
          : t("hakoniwa.residentForm.save")
      }
      cancelLabel={t("hakoniwa.residentForm.cancel")}
      confirmDisabled={!name.trim() || !personality.trim()}
      busy={saving}
      onCancel={onClose}
      onConfirm={() => void handleSave()}
    >
      <div className="hakoniwa-form">
        <label className="hakoniwa-field" htmlFor={nameId}>
          <span>{t("hakoniwa.residentForm.name")}</span>
          <input
            id={nameId}
            type="text"
            value={name}
            maxLength={NAME_MAX}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="hakoniwa-field" htmlFor={personalityId}>
          <span>{t("hakoniwa.residentForm.personality")}</span>
          <textarea
            id={personalityId}
            rows={3}
            value={personality}
            maxLength={PERSONALITY_MAX}
            placeholder={t("hakoniwa.residentForm.personalityPlaceholder")}
            onChange={(event) => setPersonality(event.target.value)}
          />
        </label>
        <div className="hakoniwa-field">
          <span id={genderId}>{t("hakoniwa.residentForm.gender")}</span>
          <GenderSegments
            value={gender}
            onChange={setGender}
            labelledBy={genderId}
          />
        </div>
        <label className="hakoniwa-field" htmlFor={appearanceId}>
          <span>{t("hakoniwa.residentForm.appearance")}</span>
          <textarea
            id={appearanceId}
            rows={2}
            value={appearance}
            maxLength={APPEARANCE_MAX}
            placeholder={t("hakoniwa.residentForm.appearancePlaceholder")}
            onChange={(event) => setAppearance(event.target.value)}
          />
        </label>
        <p className="hakoniwa-note">
          {t("hakoniwa.residentForm.appearanceNote")}
        </p>
        {resident?.base_tags && (
          <p className="hakoniwa-tags">
            <span>{t("hakoniwa.residentForm.tags")}</span>
            <code>{resident.base_tags}</code>
          </p>
        )}
        <label className="hakoniwa-field" htmlFor={dressId}>
          <span>{t("hakoniwa.residentForm.dress")}</span>
          <textarea
            id={dressId}
            rows={2}
            value={dress}
            maxLength={APPEARANCE_MAX}
            placeholder={t("hakoniwa.residentForm.dressPlaceholder")}
            onChange={(event) => setDress(event.target.value)}
          />
        </label>
        {resident?.dress_tags && (
          <p className="hakoniwa-tags">
            <span>{t("hakoniwa.residentForm.dressTags")}</span>
            <code>{resident.dress_tags}</code>
          </p>
        )}
      </div>
    </ConfirmDialog>
  );
}
