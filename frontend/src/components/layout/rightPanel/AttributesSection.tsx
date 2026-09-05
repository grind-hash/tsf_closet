import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../../contexts/GameContext";
import { useSettings } from "../../../contexts/SettingsContext";
import { useAttributeInput } from "../../../hooks/useAttributeInput";
import {
  loadPresetAttributes,
  useAttributePresets,
} from "../../../hooks/useAttributePresets";
import type { AttributePreset } from "../../../types";
import AttributePresetSaveDialog from "../../attributes/AttributePresetSaveDialog";

/** 属性付与(現在の属性・プリセット・追加/編集フォーム・現実改変通知トグル) */
export default function AttributesSection() {
  const { t } = useTranslation();
  const { state: gameState, addAttribute, removeAttribute } = useGame();
  const { state: settingsState, setShowRealityAttributeNotification } =
    useSettings();

  // 属性入力状態(追加・編集・削除の挙動は右パネル / 人物パネルで共通)
  const {
    showInput: showAttributeInput,
    setShowInput: setShowAttributeInput,
    text: attributeText,
    setText: setAttributeText,
    isAdding: isAddingAttribute,
    editingId: editingAttributeId,
    setEditingId: setEditingAttributeId,
    inputRef: attributeInputRef,
    submit: handleAddAttribute,
    remove: handleRemoveAttribute,
    beginEdit: handleEditAttribute,
    onKeyDown: handleAttributeKeyDown,
  } = useAttributeInput({ addAttribute, removeAttribute });

  // 属性プリセット(localStorage 共有。人物パネルと同じ一覧を見る)
  const {
    presets: attributePresets,
    savePreset,
    deletePreset: handleDeleteAttributePreset,
  } = useAttributePresets();
  const [showPresetSaveModal, setShowPresetSaveModal] = useState(false);

  // 属性プリセット保存(名前か属性が空なら閉じない)
  const handleSaveAttributePreset = (name: string) => {
    const saved = savePreset(
      name,
      gameState.attributes.map((a) => a.text),
    );
    if (saved) setShowPresetSaveModal(false);
  };

  // 属性プリセット読み込み
  const handleLoadAttributePreset = (preset: AttributePreset) =>
    loadPresetAttributes(preset, addAttribute);

  return (
    <section className="right-panel__section">
      <h4 className="right-panel__section-title">
        {t("rightPanel.sectionAttributes")}
      </h4>

      {/* 属性プリセットチップ */}
      {attributePresets.length > 0 && (
        <div className="right-panel__attribute-presets">
          <span className="right-panel__preset-label">
            {t("rightPanel.presets")}
          </span>
          {attributePresets.map((preset) => (
            <span
              key={preset.id}
              className="right-panel__preset-chip"
              onClick={() => handleLoadAttributePreset(preset)}
              title={t("rightPanel.clickToAddTitle", {
                items: preset.attributes.join(", "),
              })}
            >
              <span>{preset.name}</span>
              <button
                type="button"
                className="right-panel__preset-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteAttributePreset(preset.id);
                }}
                title={t("common.delete")}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 現在の属性一覧 */}
      <div className="right-panel__attributes">
        {gameState.attributes.map((attr) => (
          <span key={attr.id} className="right-panel__attribute-badge">
            <span className="right-panel__attribute-text">{attr.text}</span>
            <button
              type="button"
              className="right-panel__attribute-delete"
              onClick={() => handleEditAttribute(attr.id, attr.text)}
              aria-label={t("characterPanel.editAttrAria", {
                text: attr.text,
              })}
              title={t("common.edit")}
            >
              ✏️
            </button>
            <button
              type="button"
              className="right-panel__attribute-delete"
              onClick={() => handleRemoveAttribute(attr.id)}
              aria-label={t("characterPanel.deleteAttrAria", {
                text: attr.text,
              })}
              title={t("common.delete")}
            >
              ✕
            </button>
          </span>
        ))}

        {/* 追加ボタン / 入力フォーム */}
        {showAttributeInput ? (
          <div className="right-panel__attribute-input">
            <input
              ref={attributeInputRef}
              type="text"
              value={attributeText}
              onChange={(e) => setAttributeText(e.target.value)}
              onKeyDown={handleAttributeKeyDown}
              placeholder={t("rightPanel.attributePlaceholder")}
              maxLength={100}
              disabled={isAddingAttribute}
            />
            <button
              type="button"
              className="right-panel__btn-primary"
              onClick={handleAddAttribute}
              disabled={isAddingAttribute || !attributeText.trim()}
            >
              {isAddingAttribute
                ? t("rightPanel.loadingDots")
                : editingAttributeId
                  ? t("common.update")
                  : t("common.add")}
            </button>
            <button
              type="button"
              className="right-panel__btn-secondary"
              onClick={() => {
                setShowAttributeInput(false);
                setAttributeText("");
                setEditingAttributeId(null);
              }}
            >
              {t("common.cancel")}
            </button>
          </div>
        ) : (
          <div className="right-panel__attribute-actions">
            <button
              type="button"
              className="right-panel__btn-secondary"
              onClick={() => {
                setShowAttributeInput(true);
                setTimeout(() => attributeInputRef.current?.focus(), 0);
              }}
            >
              {t("rightPanel.addAttribute")}
            </button>
            {gameState.attributes.length > 0 && (
              <button
                type="button"
                className="right-panel__btn-secondary"
                onClick={() => setShowPresetSaveModal(true)}
                title={t("rightPanel.saveAttributePreset")}
              >
                {t("rightPanel.saveAttributePreset")}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Reality attribute notification toggle */}
      <label className="right-panel__mini-toggle">
        <input
          type="checkbox"
          checked={settingsState.showRealityAttributeNotification}
          onChange={(e) =>
            setShowRealityAttributeNotification(e.target.checked)
          }
        />
        <span className="right-panel__mini-toggle-label">
          {t("rightPanel.realityAttrNotify")}
        </span>
      </label>

      {/* 属性プリセット保存モーダル */}
      <AttributePresetSaveDialog
        open={showPresetSaveModal}
        title={t("rightPanel.attributePresetModalTitle")}
        placeholder={t("rightPanel.presetNamePlaceholder")}
        onSave={handleSaveAttributePreset}
        onCancel={() => setShowPresetSaveModal(false)}
      />
    </section>
  );
}
