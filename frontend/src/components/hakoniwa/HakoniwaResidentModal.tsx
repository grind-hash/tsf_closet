import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  HAKONIWA_ADDRESS_STYLES,
  type HakoniwaAddressStyle,
  type HakoniwaGender,
  type HakoniwaResident,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import { GenderSegments } from "./HakoniwaCharacterAdder";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import HakoniwaLookFields from "./HakoniwaLookFields";

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
 * 「説明からタグを作る」で作るか手で書く(欄のタグをそのまま保存する)。
 */
export default function HakoniwaResidentModal({
  resident,
  onClose,
}: HakoniwaResidentModalProps) {
  const { t } = useTranslation();
  const { saveResident, makeResidentTags, busy } = useHakoniwa();
  const nameId = useId();
  const personalityId = useId();
  const genderId = useId();
  const addressId = useId();
  const [name, setName] = useState(resident?.name ?? "");
  const [personality, setPersonality] = useState(resident?.personality ?? "");
  const [gender, setGender] = useState<HakoniwaGender>(
    resident?.gender ?? "female",
  );
  const [appearance, setAppearance] = useState(resident?.appearance_text ?? "");
  const [dress, setDress] = useState(resident?.dress_text ?? "");
  const [addressStyle, setAddressStyle] = useState<HakoniwaAddressStyle>(
    resident?.address_style ?? "given_san",
  );
  const [baseTags, setBaseTags] = useState(resident?.base_tags ?? "");
  const [dressTags, setDressTags] = useState(resident?.dress_tags ?? "");
  const [makingBase, setMakingBase] = useState(false);
  const [makingDress, setMakingDress] = useState(false);
  const saving = busy === "resident";

  const handleSave = async () => {
    const saved = await saveResident(
      {
        name: name.trim(),
        personality: personality.trim(),
        gender,
        appearance_text: appearance.trim(),
        dress_text: dress.trim(),
        address_style: addressStyle,
        base_tags: baseTags.trim(),
        dress_tags: dressTags.trim(),
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
      confirmDisabled={
        !name.trim() ||
        !personality.trim() ||
        !baseTags.trim() ||
        makingBase ||
        makingDress
      }
      busy={saving}
      onCancel={onClose}
      onConfirm={() => void handleSave()}
    >
      <div className="hakoniwa-form">
        <HakoniwaErrorBanner placement="dialog" clearOnMount />
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
        <label className="hakoniwa-field" htmlFor={addressId}>
          <span>{t("hakoniwa.residentForm.addressStyle")}</span>
          <select
            id={addressId}
            value={addressStyle}
            onChange={(event) =>
              setAddressStyle(event.target.value as HakoniwaAddressStyle)
            }
          >
            {HAKONIWA_ADDRESS_STYLES.map((style) => (
              <option key={style} value={style}>
                {t(`hakoniwa.residentForm.addressStyles.${style}`)}
              </option>
            ))}
          </select>
        </label>
        <p className="hakoniwa-note">
          {t("hakoniwa.residentForm.addressNote")}
        </p>
        <HakoniwaLookFields
          descriptionLabel={t("hakoniwa.residentForm.appearance")}
          description={appearance}
          onDescriptionChange={setAppearance}
          descriptionPlaceholder={t(
            "hakoniwa.residentForm.appearancePlaceholder",
          )}
          descriptionMax={APPEARANCE_MAX}
          note={t("hakoniwa.residentForm.appearanceNote")}
          tagsLabel={t("hakoniwa.residentForm.tags")}
          tags={baseTags}
          onTagsChange={setBaseTags}
          tagsPlaceholder={t("hakoniwa.residentForm.tagsPlaceholder")}
          required
          canMake={Boolean(appearance.trim())}
          onMake={() =>
            makeResidentTags({
              appearance_text: appearance.trim(),
              gender,
              dress: false,
            })
          }
          onMakingChange={setMakingBase}
        />
        <HakoniwaLookFields
          descriptionLabel={t("hakoniwa.residentForm.dress")}
          description={dress}
          onDescriptionChange={setDress}
          descriptionPlaceholder={t("hakoniwa.residentForm.dressPlaceholder")}
          descriptionMax={APPEARANCE_MAX}
          tagsLabel={t("hakoniwa.residentForm.dressTags")}
          tags={dressTags}
          onTagsChange={setDressTags}
          tagsPlaceholder={t("hakoniwa.residentForm.dressTagsPlaceholder")}
          showTagsNote={false}
          canMake={Boolean(dress.trim())}
          onMake={() =>
            makeResidentTags({
              appearance_text: dress.trim(),
              gender,
              dress: true,
            })
          }
          onMakingChange={setMakingDress}
        />
      </div>
    </ConfirmDialog>
  );
}
