/**
 * ProfileFields - 性格プロフィールの入力欄（性格・リアクションスタイル・一人称・性別・
 * 趣味・TSFへの態度）。自分自身モードのキャラ設定と、複数人表示の登場人物で共用する。
 *
 * 値は親が持つ。onChange は入力のたびに、onCommit は確定時（テキスト欄の blur・
 * セレクトの変更）に、変わった項目だけを渡す。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import "./SelfProfileEditor.css";

export const REACTION_STYLES = [
  "default",
  "bold",
  "gentle",
  "cheerful",
  "shy",
  "calm",
  "passionate",
] as const;

export const GENDERS = ["man", "woman"] as const;

export interface ProfileFieldsValue {
  personality: string;
  reaction_style: string;
  pronoun: string;
  gender: string;
  interests: string[];
  tsf_attitude: string;
}

interface ProfileFieldsProps {
  value: ProfileFieldsValue;
  onChange: (patch: Partial<ProfileFieldsValue>) => void;
  onCommit?: (patch: Partial<ProfileFieldsValue>) => void;
  /** true のとき性別に「未設定」を選べる（登場人物用） */
  allowUnsetGender?: boolean;
}

function parseInterests(text: string): string[] {
  return text
    .split(/[,、]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function ProfileFields({
  value,
  onChange,
  onCommit,
  allowUnsetGender = false,
}: ProfileFieldsProps) {
  const { t } = useTranslation();
  const idPrefix = useId();

  // 趣味は入力中の区切り文字を消さないよう文字列のまま持ち、確定時に配列へ変換する。
  // 親の値が外から変わった（自動生成など）ときだけ取り込む。
  const joinedInterests = value.interests.join(", ");
  const [interestsText, setInterestsText] = useState(joinedInterests);
  const lastJoinedRef = useRef(joinedInterests);
  useEffect(() => {
    if (joinedInterests !== lastJoinedRef.current) {
      lastJoinedRef.current = joinedInterests;
      setInterestsText(joinedInterests);
    }
  }, [joinedInterests]);

  const commitInterests = () => {
    const parsed = parseInterests(interestsText);
    lastJoinedRef.current = parsed.join(", ");
    onChange({ interests: parsed });
    onCommit?.({ interests: parsed });
  };

  const fieldId = (name: string) => `${idPrefix}-${name}`;
  const genderValue = allowUnsetGender ? value.gender : value.gender || "man";

  return (
    <>
      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("personality")}
        >
          {t("settings.selfProfile.personality")}
        </label>
        <textarea
          id={fieldId("personality")}
          className="self-profile-editor__textarea self-profile-editor__textarea--small"
          value={value.personality}
          onChange={(e) => onChange({ personality: e.target.value })}
          onBlur={(e) => onCommit?.({ personality: e.target.value })}
          rows={2}
        />
      </div>

      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("reaction")}
        >
          {t("settings.selfProfile.reactionStyle")}
        </label>
        <select
          id={fieldId("reaction")}
          className="self-profile-editor__select"
          value={value.reaction_style}
          onChange={(e) => {
            onChange({ reaction_style: e.target.value });
            onCommit?.({ reaction_style: e.target.value });
          }}
        >
          {REACTION_STYLES.map((style) => (
            <option key={style} value={style}>
              {t(`settings.selfProfile.reactionStyles.${style}`)}
            </option>
          ))}
        </select>
      </div>

      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("pronoun")}
        >
          {t("settings.selfProfile.pronoun")}
        </label>
        <input
          id={fieldId("pronoun")}
          type="text"
          className="self-profile-editor__input"
          value={value.pronoun}
          onChange={(e) => onChange({ pronoun: e.target.value })}
          onBlur={(e) => onCommit?.({ pronoun: e.target.value })}
        />
      </div>

      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("gender")}
        >
          {t("settings.selfProfile.gender")}
        </label>
        <select
          id={fieldId("gender")}
          className="self-profile-editor__select"
          value={genderValue}
          onChange={(e) => {
            onChange({ gender: e.target.value });
            onCommit?.({ gender: e.target.value });
          }}
        >
          {allowUnsetGender && (
            <option value="">{t("character.profile.genderUnset")}</option>
          )}
          {GENDERS.map((g) => (
            <option key={g} value={g}>
              {t(`settings.selfProfile.genders.${g}`)}
            </option>
          ))}
        </select>
      </div>

      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("interests")}
        >
          {t("settings.selfProfile.interests")}
        </label>
        <input
          id={fieldId("interests")}
          type="text"
          className="self-profile-editor__input"
          value={interestsText}
          onChange={(e) => setInterestsText(e.target.value)}
          onBlur={commitInterests}
          placeholder={t("settings.selfProfile.interestsPlaceholder")}
        />
      </div>

      <div className="self-profile-editor__field">
        <label
          className="self-profile-editor__label"
          htmlFor={fieldId("tsf-attitude")}
        >
          {t("settings.selfProfile.tsfAttitude")}
        </label>
        <input
          id={fieldId("tsf-attitude")}
          type="text"
          className="self-profile-editor__input"
          value={value.tsf_attitude}
          onChange={(e) => onChange({ tsf_attitude: e.target.value })}
          onBlur={(e) => onCommit?.({ tsf_attitude: e.target.value })}
        />
      </div>
    </>
  );
}
