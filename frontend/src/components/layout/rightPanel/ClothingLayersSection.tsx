import { useTranslation } from "react-i18next";
import { useSettings } from "../../../contexts/SettingsContext";

/** 衣装レイヤー考慮トグル(下着や隠れる部位を上着の下に隠す) */
export default function ClothingLayersSection() {
  const { t } = useTranslation();
  const { state: settingsState, setRespectClothingLayers } = useSettings();
  return (
    <section className="right-panel__section">
      <div className="right-panel__form-group">
        <label className="right-panel__toggle">
          <span className="right-panel__toggle-label">
            {t("rightPanel.respectClothingLayers", "Respect Clothing Layers")}
          </span>
          <input
            type="checkbox"
            checked={settingsState.respectClothingLayers}
            onChange={(e) => setRespectClothingLayers(e.target.checked)}
            className="right-panel__toggle-input"
          />
          <span className="right-panel__toggle-switch" />
        </label>
        <div style={{ marginTop: "0.25rem" }}>
          <span
            className="feature-chip-experimental"
            data-feature-version="v0.6.0"
          >
            Experimental
          </span>
        </div>
        <small className="right-panel__hint">
          {t(
            "rightPanel.respectClothingLayersHint",
            "Keeps underwear and covered body attributes hidden beneath normally worn outer clothing.",
          )}
        </small>
        {settingsState.respectClothingLayers && (
          <small
            className="right-panel__hint"
            style={{
              marginTop: "0.25rem",
              color: "var(--text-warning, #e0a050)",
            }}
          >
            {t("rightPanel.respectClothingLayersException")}
          </small>
        )}
      </div>
    </section>
  );
}
