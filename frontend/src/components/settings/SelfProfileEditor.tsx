/**
 * SelfProfileEditor - Self-profile editing component
 * US6 - Personality profile auto-generation and manual editing
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  generateSelfProfile,
  type SelfProfile,
  saveSelfProfile,
} from "../../apis/settings";
import { useSettings } from "../../contexts/SettingsContext";
import "./SelfProfileEditor.css";

const REACTION_STYLES = [
  "default",
  "bold",
  "gentle",
  "cheerful",
  "shy",
  "calm",
  "passionate",
] as const;

const GENDERS = ["man", "woman"] as const;

export default function SelfProfileEditor() {
  const { t } = useTranslation();
  const { selfProfile, setSelfProfile, loadSelfProfile } = useSettings();

  const [inputText, setInputText] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Local editing state (separate from context so user can edit before saving)
  const [editProfile, setEditProfile] = useState<SelfProfile | null>(
    selfProfile,
  );

  const handleGenerate = useCallback(async () => {
    if (!inputText.trim()) return;
    setIsGenerating(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const profile = await generateSelfProfile(inputText);
      setEditProfile(profile);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("settings.selfProfile.generateError"),
      );
    } finally {
      setIsGenerating(false);
    }
  }, [inputText, t]);

  const handleSave = useCallback(async () => {
    if (!editProfile) return;
    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await saveSelfProfile(editProfile);
      setSelfProfile(editProfile);
      setSuccessMessage(t("settings.selfProfile.saved"));
      // Reload from server to confirm
      await loadSelfProfile();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("settings.selfProfile.saveError"),
      );
    } finally {
      setIsSaving(false);
    }
  }, [editProfile, setSelfProfile, loadSelfProfile, t]);

  const updateField = useCallback(
    (field: keyof SelfProfile, value: string | string[]) => {
      if (!editProfile) return;
      setEditProfile({ ...editProfile, [field]: value });
    },
    [editProfile],
  );

  return (
    <div className="self-profile-editor">
      {/* Text input for auto-generation */}
      <div className="self-profile-editor__generate">
        <label className="self-profile-editor__label">
          {t("settings.selfProfile.inputLabel")}
        </label>
        <textarea
          className="self-profile-editor__textarea"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={t("settings.selfProfile.inputPlaceholder")}
          maxLength={1000}
          rows={3}
        />
        <button
          type="button"
          className="self-profile-editor__generate-btn"
          onClick={handleGenerate}
          disabled={isGenerating || !inputText.trim()}
        >
          {isGenerating
            ? t("settings.selfProfile.generating")
            : t("settings.selfProfile.generateButton")}
        </button>
      </div>

      {/* Profile editing form */}
      {editProfile && (
        <div className="self-profile-editor__form">
          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.displayName")}
            </label>
            <input
              type="text"
              className="self-profile-editor__input"
              value={editProfile.display_name}
              onChange={(e) => updateField("display_name", e.target.value)}
              placeholder={t("settings.selfProfile.displayNamePlaceholder")}
            />
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.personality")}
            </label>
            <textarea
              className="self-profile-editor__textarea self-profile-editor__textarea--small"
              value={editProfile.personality}
              onChange={(e) => updateField("personality", e.target.value)}
              rows={2}
            />
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.reactionStyle")}
            </label>
            <select
              className="self-profile-editor__select"
              value={editProfile.reaction_style}
              onChange={(e) => updateField("reaction_style", e.target.value)}
            >
              {REACTION_STYLES.map((style) => (
                <option key={style} value={style}>
                  {t(`settings.selfProfile.reactionStyles.${style}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.pronoun")}
            </label>
            <input
              type="text"
              className="self-profile-editor__input"
              value={editProfile.pronoun}
              onChange={(e) => updateField("pronoun", e.target.value)}
            />
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.gender")}
            </label>
            <select
              className="self-profile-editor__select"
              value={editProfile.gender || "man"}
              onChange={(e) => updateField("gender", e.target.value)}
            >
              {GENDERS.map((g) => (
                <option key={g} value={g}>
                  {t(`settings.selfProfile.genders.${g}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.interests")}
            </label>
            <input
              type="text"
              className="self-profile-editor__input"
              value={editProfile.interests.join(", ")}
              onChange={(e) =>
                updateField(
                  "interests",
                  e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                )
              }
              placeholder={t("settings.selfProfile.interestsPlaceholder")}
            />
          </div>

          <div className="self-profile-editor__field">
            <label className="self-profile-editor__label">
              {t("settings.selfProfile.tsfAttitude")}
            </label>
            <input
              type="text"
              className="self-profile-editor__input"
              value={editProfile.tsf_attitude}
              onChange={(e) => updateField("tsf_attitude", e.target.value)}
            />
          </div>

          <button
            type="button"
            className="self-profile-editor__save-btn"
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving
              ? t("settings.selfProfile.saving")
              : t("settings.selfProfile.saveButton")}
          </button>

          {/* Error / success messages */}
          {error && <div className="self-profile-editor__error">{error}</div>}
          {successMessage && (
            <div className="self-profile-editor__success">{successMessage}</div>
          )}
        </div>
      )}

      {/* Show current saved profile info */}
      {selfProfile && !editProfile && (
        <div className="self-profile-editor__current">
          <p className="self-profile-editor__current-info">
            {t("settings.selfProfile.currentProfile")}:{" "}
            {selfProfile.personality}
          </p>
          <button
            type="button"
            className="self-profile-editor__edit-btn"
            onClick={() => setEditProfile(selfProfile)}
          >
            {t("settings.selfProfile.editButton")}
          </button>
        </div>
      )}
    </div>
  );
}
