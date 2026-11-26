import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../../contexts/SettingsContext";
import { usePreciseReferenceDropZone } from "../../../hooks/usePreciseReferenceDropZone";
import { PRECISE_REFERENCE_SECTION_ID } from "../../../hooks/usePreciseReferenceFiles";
import type { PreciseReferenceType } from "../../../types";
import { fetchMediaAsFile } from "../../../utils/mediaImage";
import {
  clampReferenceStrength,
  isReferenceTypeSupported,
  PRECISE_REFERENCE_STRENGTH_MAX,
  referenceTypeUsesOutfit,
} from "../../../utils/preciseReferences";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../../adventure/AdventureSessionPickerModal";

const noteStyle = {
  display: "block",
  fontSize: "0.7rem",
  marginTop: "0.15rem",
} as const;

/**
 * 精密参照画像(character reference)の追加と各画像の設定。
 * 項目はモデルで出し分けず、効かない組み合わせは無効表示と注記で伝える
 */
export default function PreciseReferencesPanel() {
  const { t } = useTranslation();
  const {
    state: settingsState,
    updatePreciseReference,
    removePreciseReference,
    novelaiPreciseReferenceFormat: format,
  } = useSettings();
  const dropZone = usePreciseReferenceDropZone();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const unsupported = format === null;
  const isV5 = format === "v5";
  const strengthMax = PRECISE_REFERENCE_STRENGTH_MAX[format ?? "v4_5"];
  const inpaintActive =
    settingsState.inpaintEnabled &&
    Boolean(settingsState.inpaintMask.maskDataUrl);

  // 一覧(セッション・お気に入り・Prompt Expander・キャラクター)から選んだ画像を取り込み、
  // アップロードと同じ検証を通して追加する
  const handlePick = async (selection: AdventureSourceSelection) => {
    setPicking(true);
    dropZone.setError(null);
    try {
      const name =
        selection.characterName?.trim() ||
        selection.pointLabel?.trim() ||
        t("rightPanel.preciseRefPickedFallback");
      const file = await fetchMediaAsFile(selection.thumbnailUrl, name);
      await dropZone.addFiles([file]);
    } catch (err) {
      console.error("Failed to load the picked reference image", err);
      dropZone.setError(t("rightPanel.preciseRefPickFailed"));
    } finally {
      setPicking(false);
      setPickerOpen(false);
    }
  };

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
      <small
        className="right-panel__hint"
        style={{ marginBottom: "0.5rem", display: "block" }}
      >
        {unsupported
          ? t("rightPanel.preciseReferenceUnsupportedModel")
          : t("rightPanel.preciseReferenceAnlas")}
      </small>
      {isV5 && inpaintActive && (
        <small
          className="right-panel__hint"
          data-testid="precise-ref-inpaint-v5-note"
          style={{ marginBottom: "0.5rem", display: "block" }}
        >
          {t("rightPanel.preciseReferenceInpaintV5")}
        </small>
      )}
      <div
        className={unsupported ? "right-panel__disabled-block" : undefined}
        aria-disabled={unsupported || undefined}
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
        <button
          type="button"
          className="right-panel__btn-secondary right-panel__precise-ref-pick"
          onClick={() => setPickerOpen(true)}
          data-testid="precise-ref-pick"
        >
          {t("rightPanel.preciseRefPickFromList")}
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
                  <option value="costume" disabled={!isV5}>
                    {t("rightPanel.referenceTypeCostume")}
                  </option>
                </select>
                {format !== null &&
                  !isReferenceTypeSupported(ref.type, format) && (
                    <small className="right-panel__hint" style={noteStyle}>
                      {t("rightPanel.costumeV5Only")}
                    </small>
                  )}
              </div>

              {/* 衣装も参照する（V5 のキャラ系の参照だけ有効） */}
              <div
                className="right-panel__form-group"
                style={{ marginBottom: "0.3rem" }}
              >
                <label
                  className="right-panel__toggle"
                  style={{
                    opacity:
                      isV5 && referenceTypeUsesOutfit(ref.type) ? 1 : 0.5,
                  }}
                >
                  <span
                    className="right-panel__toggle-label"
                    style={{ fontSize: "0.75rem" }}
                  >
                    {t("rightPanel.includeOutfit")}
                  </span>
                  <input
                    type="checkbox"
                    className="right-panel__toggle-input"
                    data-testid="precise-ref-include-outfit"
                    checked={ref.includeOutfit}
                    disabled={!isV5 || !referenceTypeUsesOutfit(ref.type)}
                    onChange={(e) =>
                      updatePreciseReference(ref.id, {
                        includeOutfit: e.target.checked,
                      })
                    }
                  />
                  <span className="right-panel__toggle-switch" />
                </label>
                <small className="right-panel__hint" style={noteStyle}>
                  {!referenceTypeUsesOutfit(ref.type)
                    ? t("rightPanel.includeOutfitCharacterOnly")
                    : isV5
                      ? t("rightPanel.includeOutfitHint")
                      : t("rightPanel.includeOutfitV5Only")}
                </small>
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
                  data-testid="precise-ref-strength"
                  min={0}
                  max={strengthMax}
                  step={0.05}
                  value={Math.min(ref.strength, strengthMax)}
                  onChange={(e) =>
                    updatePreciseReference(ref.id, {
                      strength: parseFloat(e.target.value),
                    })
                  }
                />
                {format !== null && ref.strength > strengthMax && (
                  <small className="right-panel__hint" style={noteStyle}>
                    {t("rightPanel.strengthClamped", {
                      value: clampReferenceStrength(
                        ref.strength,
                        format,
                      ).toFixed(2),
                    })}
                  </small>
                )}
              </div>

              {/* Fidelity slider（V5 では廃止） */}
              <div
                className="right-panel__form-group"
                style={{ marginBottom: 0, opacity: isV5 ? 0.5 : 1 }}
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
                  disabled={isV5}
                  onChange={(e) =>
                    updatePreciseReference(ref.id, {
                      fidelity: parseFloat(e.target.value),
                    })
                  }
                />
                {isV5 && (
                  <small className="right-panel__hint" style={noteStyle}>
                    {t("rightPanel.fidelityV5Unused")}
                  </small>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {/* 無効表示の半透明を引き継がないよう、モーダルは無効ブロックの外に置く */}
      {pickerOpen && (
        <AdventureSessionPickerModal
          title={t("rightPanel.preciseRefPickerTitle")}
          selected={null}
          onSelect={(selection) => void handlePick(selection)}
          onClose={() => setPickerOpen(false)}
          allowPromptExpander={settingsState.experimentalPromptExpanderEnabled}
          characters="tab"
          busyLabel={picking ? t("rightPanel.preciseRefPicking") : null}
        />
      )}
    </div>
  );
}
