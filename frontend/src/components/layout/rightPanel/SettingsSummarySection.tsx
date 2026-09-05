import { useTranslation } from "react-i18next";
import { useGame } from "../../../contexts/GameContext";
import { useSettings } from "../../../contexts/SettingsContext";

/** 現在の設定サマリー(難易度・言語・インペイント・NSFW・属性) */
export default function SettingsSummarySection() {
  const { t } = useTranslation();
  const { state: settingsState } = useSettings();
  const { state: gameState } = useGame();
  const isNovelAI = settingsState.imageProvider === "novelai";
  const difficultyOptions: Array<{
    id: "easy" | "normal" | "hard";
    label: string;
  }> = [
    { id: "easy", label: t("settings.easy") },
    { id: "normal", label: t("settings.normal") },
    { id: "hard", label: t("settings.hard") },
  ];
  return (
    <section className="right-panel__section right-panel__section--summary">
      <h4 className="right-panel__section-title">
        {t("rightPanel.sectionSummary")}
      </h4>
      <ul className="right-panel__summary">
        <li>
          {t("rightPanel.difficultyLabel")}:{" "}
          {difficultyOptions.find((d) => d.id === settingsState.difficulty)
            ?.label || t("settings.normal")}
        </li>
        <li>
          {t("rightPanel.languageLabel")}:{" "}
          {settingsState.language === "en"
            ? t("settings.en")
            : t("settings.ja")}
        </li>
        {isNovelAI && (
          <>
            <li>
              {t("rightPanel.inpaintLabel")}:{" "}
              {settingsState.inpaintEnabled
                ? t("common.enabled")
                : t("common.disabled")}
            </li>
            <li>
              {t("rightPanel.nsfwLabel")}:{" "}
              {settingsState.nsfwMode
                ? t("common.enabled")
                : t("common.disabled")}
            </li>
          </>
        )}
        {gameState.attributes.length > 0 && (
          <li>
            {t("rightPanel.attributesLabel")}:{" "}
            {gameState.attributes.map((a) => a.text).join(", ")}
          </li>
        )}
      </ul>
    </section>
  );
}
