import { useTranslation } from "react-i18next";
import { useSettings } from "../../../contexts/SettingsContext";

/** 応答言語(ja / en)のラジオ */
export default function LanguageSection() {
  const { t } = useTranslation();
  const { state: settingsState, setLanguage } = useSettings();
  const languageOptions: Array<{ id: "ja" | "en"; label: string }> = [
    { id: "ja", label: t("settings.ja") },
    { id: "en", label: t("settings.en") },
  ];
  return (
    <section className="right-panel__section">
      <h4 className="right-panel__section-title">
        {t("rightPanel.sectionLanguage")}
      </h4>
      <div className="right-panel__radio-group">
        {languageOptions.map((option) => (
          <label key={option.id} className="right-panel__radio">
            <input
              type="radio"
              name="language"
              value={option.id}
              checked={settingsState.language === option.id}
              onChange={() => setLanguage(option.id)}
              className="right-panel__radio-input"
            />
            <span className="right-panel__radio-label">{option.label}</span>
          </label>
        ))}
      </div>
    </section>
  );
}
