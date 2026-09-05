import { useTranslation } from "react-i18next";
import { useSettings } from "../../../contexts/SettingsContext";
import { usePreciseReferenceDropZone } from "../../../hooks/usePreciseReferenceDropZone";
import { PRECISE_REFERENCE_SECTION_ID } from "../../../hooks/usePreciseReferenceFiles";
import type { PreciseReferenceType } from "../../../types";

/** 精密参照画像(character reference / vibe transfer)の追加と各画像の設定 */
export default function PreciseReferencesPanel() {
  const { t } = useTranslation();
  const {
    state: settingsState,
    updatePreciseReference,
    removePreciseReference,
    isNovelaiV5Active,
  } = useSettings();
  const dropZone = usePreciseReferenceDropZone();

  return (
    <div
      id={PRECISE_REFERENCE_SECTION_ID}
      data-testid="precise-reference-section"
      className="right-panel__form-group"
      style={{ marginTop: "1rem" }}
    >
      <label className="right-panel__label">
        {t("rightPanel.preciseReferences")}
      </label>
      {isNovelaiV5Active ? (
        <small
          className="right-panel__hint"
          style={{ marginBottom: "0.5rem", display: "block" }}
        >
          {t("rightPanel.preciseReferenceV5Unavailable")}
        </small>
      ) : (
        <small
          className="right-panel__hint"
          style={{ marginBottom: "0.5rem", display: "block" }}
        >
          {t("rightPanel.preciseReferenceAnlas")}
        </small>
      )}
      <div
        className={
          isNovelaiV5Active ? "right-panel__disabled-block" : undefined
        }
        aria-disabled={isNovelaiV5Active || undefined}
      >
        <input
          ref={dropZone.inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          style={{ display: "none" }}
          onChange={dropZone.onFileChange}
        />
        <button
          type="button"
          className={`right-panel__precise-ref-drop-zone ${
            dropZone.dragging ? "is-dragging" : ""
          }`}
          onClick={dropZone.openPicker}
          onDragEnter={dropZone.onDragEnter}
          onDragOver={dropZone.onDragOver}
          onDragLeave={dropZone.onDragLeave}
          onDrop={dropZone.onDrop}
          aria-label={t("rightPanel.addReferenceImage")}
          data-testid="precise-ref-drop-zone"
        >
          {dropZone.dragging ? (
            t("rightPanel.preciseRefDropActive")
          ) : (
            <>
              <span>{t("rightPanel.addReferenceImage")}</span>
              <span className="right-panel__precise-ref-drop-hint">
                {t("rightPanel.preciseRefDropHint")}
              </span>
            </>
          )}
        </button>

        {dropZone.error && (
          <div
            style={{
              color: "var(--danger-color, #f44)",
              fontSize: "0.8rem",
              marginBottom: "0.5rem",
              padding: "0.3rem 0.5rem",
              background: "rgba(255,68,68,0.1)",
              borderRadius: 4,
            }}
          >
            {dropZone.error}
          </div>
        )}

        {settingsState.preciseReferences.map((ref) => (
          <div
            key={ref.id}
            className="right-panel__precise-ref-card"
            style={{
              border: "1px solid var(--border-color, #555)",
              borderRadius: "6px",
              padding: "0.5rem",
              marginBottom: "0.5rem",
              position: "relative",
            }}
          >
            {/* Thumbnail + controls header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                marginBottom: "0.4rem",
              }}
            >
              <img
                src={ref.imageData}
                alt={ref.fileName}
                style={{
                  width: 48,
                  height: 48,
                  objectFit: "cover",
                  borderRadius: 4,
                  opacity: ref.enabled ? 1 : 0.4,
                }}
              />
              <span
                style={{
                  flex: 1,
                  fontSize: "0.8rem",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {ref.fileName}
              </span>
              <button
                type="button"
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "1rem",
                  color: "var(--text-secondary, #aaa)",
                  pointerEvents: "auto",
                }}
                title={t("rightPanel.toggleEnabledTitle")}
                onClick={() =>
                  updatePreciseReference(ref.id, { enabled: !ref.enabled })
                }
              >
                {ref.enabled ? "👁" : "👁‍🗨"}
              </button>
              <button
                type="button"
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "1rem",
                  color: "var(--danger-color, #f44)",
                  pointerEvents: "auto",
                }}
                title={t("common.delete")}
                onClick={() => removePreciseReference(ref.id)}
              >
                🗑
              </button>
            </div>

            {/* Controls area - grayed out when disabled */}
            <div
              style={{
                opacity: ref.enabled ? 1 : 0.4,
                pointerEvents: ref.enabled ? "auto" : "none",
              }}
            >
              {/* Reference type dropdown */}
              <div
                className="right-panel__form-group"
                style={{ marginBottom: "0.3rem" }}
              >
                <label
                  className="right-panel__label"
                  style={{ fontSize: "0.75rem" }}
                >
                  {t("rightPanel.referenceType")}
                </label>
                <select
                  className="right-panel__select"
                  value={ref.type}
                  onChange={(e) =>
                    updatePreciseReference(ref.id, {
                      type: e.target.value as PreciseReferenceType,
                    })
                  }
                  style={{ width: "100%", fontSize: "0.8rem" }}
                >
                  <option value="character&style">
                    {t("rightPanel.referenceTypeCharacterStyle")}
                  </option>
                  <option value="character">
                    {t("rightPanel.referenceTypeCharacter")}
                  </option>
                  <option value="style">
                    {t("rightPanel.referenceTypeStyle")}
                  </option>
                </select>
              </div>

              {/* Strength slider */}
              <div
                className="right-panel__form-group"
                style={{ marginBottom: "0.3rem" }}
              >
                <label
                  className="right-panel__label"
                  style={{ fontSize: "0.75rem" }}
                >
                  {t("rightPanel.strength")}: {ref.strength.toFixed(2)}
                </label>
                <input
                  type="range"
                  className="right-panel__slider"
                  min={0}
                  max={1}
                  step={0.05}
                  value={ref.strength}
                  onChange={(e) =>
                    updatePreciseReference(ref.id, {
                      strength: parseFloat(e.target.value),
                    })
                  }
                />
              </div>

              {/* Fidelity slider */}
              <div
                className="right-panel__form-group"
                style={{ marginBottom: 0 }}
              >
                <label
                  className="right-panel__label"
                  style={{ fontSize: "0.75rem" }}
                >
                  {t("rightPanel.fidelity")}: {ref.fidelity.toFixed(2)}
                </label>
                <input
                  type="range"
                  className="right-panel__slider"
                  min={0}
                  max={1}
                  step={0.05}
                  value={ref.fidelity}
                  onChange={(e) =>
                    updatePreciseReference(ref.id, {
                      fidelity: parseFloat(e.target.value),
                    })
                  }
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
