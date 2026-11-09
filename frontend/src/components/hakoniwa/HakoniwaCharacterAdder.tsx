import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaGender } from "../../apis/hakoniwa";
import type { CharacterPreset } from "../../types";
import CharacterPickerModal from "../characters/CharacterPickerModal";
import ConfirmDialog from "../ui/ConfirmDialog";

export interface HakoniwaPickedCharacter {
  character_preset_id: string;
  name: string;
  portrait_url: string | null;
  gender: HakoniwaGender;
}

interface HakoniwaCharacterAdderProps {
  /** すでに選んでいる(住民になっている)キャラクターの id */
  excludeIds: string[];
  onAdd: (character: HakoniwaPickedCharacter) => void;
  disabled?: boolean;
  className?: string;
}

const GENDER_BY_PROFILE: Record<string, HakoniwaGender> = {
  man: "male",
  woman: "female",
};

/**
 * 登録キャラクターを1人選ぶボタン。立ち絵の無いキャラクターは迎えられないことを伝え、
 * 性別が未設定ならここで選んでもらう。
 */
export default function HakoniwaCharacterAdder({
  excludeIds,
  onAdd,
  disabled = false,
  className,
}: HakoniwaCharacterAdderProps) {
  const { t } = useTranslation();
  const [picking, setPicking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [needsGender, setNeedsGender] = useState<CharacterPreset | null>(null);
  const [gender, setGender] = useState<HakoniwaGender>("female");

  const handleSelect = (preset: CharacterPreset) => {
    setPicking(false);
    if (excludeIds.includes(preset.id)) {
      setMessage(t("hakoniwa.character.alreadyAdded", { name: preset.name }));
      return;
    }
    if (!preset.portrait_url) {
      setMessage(t("hakoniwa.character.noPortrait", { name: preset.name }));
      return;
    }
    setMessage(null);
    const known = GENDER_BY_PROFILE[preset.profile?.gender ?? ""];
    if (!known) {
      setGender("female");
      setNeedsGender(preset);
      return;
    }
    onAdd({
      character_preset_id: preset.id,
      name: preset.name,
      portrait_url: preset.portrait_url,
      gender: known,
    });
  };

  return (
    <div className={className}>
      <button
        type="button"
        className="hakoniwa-button"
        onClick={() => setPicking(true)}
        disabled={disabled}
      >
        {t("hakoniwa.hub.addCharacter")}
      </button>
      {message && (
        <p className="hakoniwa-note hakoniwa-note--warning" role="alert">
          {message}
        </p>
      )}
      {picking && (
        <CharacterPickerModal
          title={t("hakoniwa.character.pickerTitle")}
          onSelect={handleSelect}
          onClose={() => setPicking(false)}
        />
      )}
      <ConfirmDialog
        open={needsGender !== null}
        title={t("hakoniwa.character.genderTitle", {
          name: needsGender?.name ?? "",
        })}
        confirmLabel={t("hakoniwa.character.genderConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setNeedsGender(null)}
        onConfirm={() => {
          if (needsGender) {
            onAdd({
              character_preset_id: needsGender.id,
              name: needsGender.name,
              portrait_url: needsGender.portrait_url,
              gender,
            });
          }
          setNeedsGender(null);
        }}
      >
        <p>{t("hakoniwa.character.genderBody")}</p>
        <GenderSegments value={gender} onChange={setGender} />
      </ConfirmDialog>
    </div>
  );
}

export function GenderSegments({
  value,
  onChange,
  labelledBy,
}: {
  value: HakoniwaGender;
  onChange: (gender: HakoniwaGender) => void;
  labelledBy?: string;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="hakoniwa-segments"
      role="group"
      aria-labelledby={labelledBy}
    >
      {(["female", "male"] as const).map((option) => (
        <button
          key={option}
          type="button"
          className={value === option ? "is-active" : undefined}
          aria-pressed={value === option}
          onClick={() => onChange(option)}
        >
          {t(`hakoniwa.gender.${option}`)}
        </button>
      ))}
    </div>
  );
}
