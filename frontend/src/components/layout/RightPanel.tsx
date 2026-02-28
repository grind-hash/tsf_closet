/**
 * RightPanel - 右サイドパネル (開閉式)
 * 007-chat-interactive-ux
 *
 * 構成:
 * - 属性設定UI
 * - 保持する要素設定
 * - インペイント設定（NovelAIのみ）
 * - その他のオプション設定
 *
 * T127-T130: Context経由で状態を取得
 */

import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import { useGame } from "../../contexts/GameContext";
import type {
  PreserveElement,
  ChangeScope,
  PreciseReferenceType,
} from "../../types";
import "./RightPanel.css";

interface RightPanelProps {
  onClose?: () => void;
  onOpenInpaintModal?: () => void; // T024: マスク設定ボタン用
}

// 属性プリセットの型
interface AttributePreset {
  id: string;
  name: string;
  attributes: string[];
  createdAt?: string;
}

// 保持要素プリセットの型
interface PreservePreset {
  id: string;
  name: string;
  preserveElements: PreserveElement[];
  changeScope: ChangeScope;
  customPreserveText: string;
}

const ATTRIBUTE_PRESET_STORAGE_KEY = "attribute_presets";
const PRESERVE_PRESET_STORAGE_KEY = "preserve_presets";
const ALLOWED_MIME_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
const PRESERVE_ELEMENTS: PreserveElement[] = [
  "background",
  "hairstyle",
  "pose",
  "expression",
  "accessories",
];
const CHANGE_SCOPES: ChangeScope[] = [
  "full",
  "upper",
  "lower",
  "accessories",
  "shoes",
];

export default function RightPanel({
  onClose,
  onOpenInpaintModal,
}: RightPanelProps) {
  const { t } = useTranslation();
  const {
    state: settingsState,
    setLanguage,
    setChangeSettings,
    setInpaintSettings,
    addPreciseReference,
    updatePreciseReference,
    removePreciseReference,
    setSeed,
    setEnableSurroundingsImage,
    setSurroundingsIncludePeople,
    setShowRealityAttributeNotification,
  } = useSettings();
  const { state: gameState, addAttribute, removeAttribute } = useGame();

  // 属性入力状態
  const [showAttributeInput, setShowAttributeInput] = useState(false);
  const [attributeText, setAttributeText] = useState("");
  const [isAddingAttribute, setIsAddingAttribute] = useState(false);
  const [editingAttributeId, setEditingAttributeId] = useState<string | null>(
    null,
  );
  const attributeInputRef = useRef<HTMLInputElement>(null);
  const preciseRefInputRef = useRef<HTMLInputElement>(null);

  // 属性プリセット
  const [attributePresets, setAttributePresets] = useState<AttributePreset[]>(
    () => {
      try {
        const saved = localStorage.getItem(ATTRIBUTE_PRESET_STORAGE_KEY);
        return saved ? JSON.parse(saved) : [];
      } catch {
        return [];
      }
    },
  );
  const [showPresetSaveModal, setShowPresetSaveModal] = useState(false);
  const [presetName, setPresetName] = useState("");

  // 保持要素プリセット
  const [preservePresets, setPreservePresets] = useState<PreservePreset[]>(
    () => {
      try {
        const saved = localStorage.getItem(PRESERVE_PRESET_STORAGE_KEY);
        return saved ? JSON.parse(saved) : [];
      } catch {
        return [];
      }
    },
  );
  const [showPreserveSaveModal, setShowPreserveSaveModal] = useState(false);
  const [preservePresetName, setPreservePresetName] = useState("");

  const difficultyOptions: Array<{
    id: "easy" | "normal" | "hard";
    label: string;
  }> = [
    { id: "easy", label: t("settings.easy") },
    { id: "normal", label: t("settings.normal") },
    { id: "hard", label: t("settings.hard") },
  ];

  const languageOptions: Array<{ id: "ja" | "en"; label: string }> = [
    { id: "ja", label: t("settings.ja") },
    { id: "en", label: t("settings.en") },
  ];

  const getPreserveElementLabel = (element: PreserveElement) => {
    switch (element) {
      case "background":
        return t("rightPanel.preserveElements.background");
      case "hairstyle":
        return t("rightPanel.preserveElements.hairstyle");
      case "pose":
        return t("rightPanel.preserveElements.pose");
      case "expression":
        return t("rightPanel.preserveElements.expression");
      case "accessories":
        return t("rightPanel.preserveElements.accessories");
      default:
        return element;
    }
  };

  const getChangeScopeLabel = (scope: ChangeScope) => {
    switch (scope) {
      case "full":
        return t("rightPanel.changeScopes.full");
      case "upper":
        return t("rightPanel.changeScopes.upper");
      case "lower":
        return t("rightPanel.changeScopes.lower");
      case "accessories":
        return t("rightPanel.changeScopes.accessories");
      case "shoes":
        return t("rightPanel.changeScopes.shoes");
      default:
        return scope;
    }
  };

  // 属性追加ハンドラー
  const handleAddAttribute = async () => {
    if (!attributeText.trim() || isAddingAttribute) return;

    setIsAddingAttribute(true);
    try {
      if (editingAttributeId) {
        await removeAttribute(editingAttributeId);
      }
      await addAttribute(attributeText.trim());
      setAttributeText("");
      setEditingAttributeId(null);
      setShowAttributeInput(false);
    } catch (error) {
      console.error("Failed to add attribute:", error);
    } finally {
      setIsAddingAttribute(false);
    }
  };

  // 属性削除ハンドラー
  const handleRemoveAttribute = async (id: string) => {
    try {
      await removeAttribute(id);
      if (editingAttributeId === id) {
        setEditingAttributeId(null);
        setAttributeText("");
      }
    } catch (error) {
      console.error("Failed to remove attribute:", error);
    }
  };

  const handleEditAttribute = (id: string, text: string) => {
    setEditingAttributeId(id);
    setAttributeText(text);
    setShowAttributeInput(true);
    setTimeout(() => attributeInputRef.current?.focus(), 0);
  };

  // Enterキーで属性追加
  const handleAttributeKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddAttribute();
    } else if (e.key === "Escape") {
      setShowAttributeInput(false);
      setAttributeText("");
      setEditingAttributeId(null);
    }
  };

  // 保持要素トグル
  const handleTogglePreserveElement = (element: PreserveElement) => {
    const current = settingsState.changeSettings.preserveElements;
    const newElements = current.includes(element)
      ? current.filter((e) => e !== element)
      : [...current, element];
    setChangeSettings({ preserveElements: newElements });
  };

  // 変更対象変更
  const handleChangeScopeChange = (scope: ChangeScope) => {
    setChangeSettings({ changeScope: scope });
  };

  // 自由記述変更
  const handleCustomPreserveTextChange = (text: string) => {
    setChangeSettings({ customPreserveText: text });
  };

  // 属性プリセット保存
  const handleSaveAttributePreset = () => {
    if (!presetName.trim() || gameState.attributes.length === 0) return;

    const newPreset: AttributePreset = {
      id: Date.now().toString(),
      name: presetName.trim(),
      attributes: gameState.attributes.map((a) => a.text),
      createdAt: new Date().toISOString(),
    };

    const updated = [...attributePresets, newPreset];
    setAttributePresets(updated);
    localStorage.setItem(ATTRIBUTE_PRESET_STORAGE_KEY, JSON.stringify(updated));
    setShowPresetSaveModal(false);
    setPresetName("");
  };

  // 属性プリセット読み込み
  const handleLoadAttributePreset = async (preset: AttributePreset) => {
    for (const text of preset.attributes) {
      try {
        await addAttribute(text);
      } catch (error) {
        console.error("Failed to add preset attribute:", error);
      }
    }
  };

  // 属性プリセット削除
  const handleDeleteAttributePreset = (id: string) => {
    const updated = attributePresets.filter((p) => p.id !== id);
    setAttributePresets(updated);
    localStorage.setItem(ATTRIBUTE_PRESET_STORAGE_KEY, JSON.stringify(updated));
  };

  // 保持要素プリセット保存
  const handleSavePreservePreset = () => {
    if (!preservePresetName.trim()) return;

    const newPreset: PreservePreset = {
      id: Date.now().toString(),
      name: preservePresetName.trim(),
      preserveElements: [...settingsState.changeSettings.preserveElements],
      changeScope: settingsState.changeSettings.changeScope,
      customPreserveText: settingsState.changeSettings.customPreserveText,
    };

    const updated = [...preservePresets, newPreset];
    setPreservePresets(updated);
    localStorage.setItem(PRESERVE_PRESET_STORAGE_KEY, JSON.stringify(updated));
    setShowPreserveSaveModal(false);
    setPreservePresetName("");
  };

  // 保持要素プリセット読み込み
  const handleLoadPreservePreset = (preset: PreservePreset) => {
    setChangeSettings({
      preserveElements: preset.preserveElements,
      changeScope: preset.changeScope,
      customPreserveText: preset.customPreserveText,
    });
  };

  // 保持要素プリセット削除
  const handleDeletePreservePreset = (id: string) => {
    const updated = preservePresets.filter((p) => p.id !== id);
    setPreservePresets(updated);
    localStorage.setItem(PRESERVE_PRESET_STORAGE_KEY, JSON.stringify(updated));
  };

  const isNovelAI = settingsState.imageProvider === "novelai";

  // Validation error for precise reference files
  const [preciseRefError, setPreciseRefError] = useState<string | null>(null);

  // Precise reference image file handler with validation
  const handlePreciseRefFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) return;
      setPreciseRefError(null);

      for (const file of Array.from(files)) {
        // MIME type check
        if (!ALLOWED_MIME_TYPES.includes(file.type)) {
          setPreciseRefError(
            t("rightPanel.preciseRefTypeError", { name: file.name }),
          );
          continue;
        }
        // File size check
        if (file.size > MAX_FILE_SIZE_BYTES) {
          setPreciseRefError(
            t("rightPanel.preciseRefSizeError", { name: file.name }),
          );
          continue;
        }
        // Max 6 references check (FR-017)
        if (settingsState.preciseReferences.length >= 6) {
          setPreciseRefError(t("rightPanel.preciseRefMaxError"));
          continue;
        }
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = reader.result as string;
          addPreciseReference({
            id: crypto.randomUUID(),
            imageData: dataUrl,
            fileName: file.name,
            type: "character&style",
            strength: 0.6,
            fidelity: 1.0,
            enabled: true,
          });
        };
        reader.readAsDataURL(file);
      }
      // Reset input so the same file can be re-selected
      e.target.value = "";
    },
    [addPreciseReference, settingsState.preciseReferences.length, t],
  );

  return (
    <div className="right-panel">
      <div className="right-panel__header">
        <h3 className="right-panel__title">{t("rightPanel.title")}</h3>
        <button
          type="button"
          className="right-panel__close-btn"
          onClick={onClose}
          aria-label={t("rightPanel.closePanel")}
        >
          ✕
        </button>
      </div>

      <div className="right-panel__content">
        {/* 属性付与セクション */}
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
        </section>

        {/* 保持する要素セクション */}
        <section className="right-panel__section">
          <h4 className="right-panel__section-title">
            {t("rightPanel.sectionPreserve")}
          </h4>

          {/* 保持要素プリセットチップ */}
          {preservePresets.length > 0 && (
            <div className="right-panel__attribute-presets">
              <span className="right-panel__preset-label">
                {t("rightPanel.presets")}
              </span>
              {preservePresets.map((preset) => (
                <span
                  key={preset.id}
                  className="right-panel__preset-chip"
                  onClick={() => handleLoadPreservePreset(preset)}
                  title={t("rightPanel.clickToApplyTitle", {
                    items: preset.preserveElements
                      .map((e) => getPreserveElementLabel(e))
                      .join(", "),
                  })}
                >
                  <span>{preset.name}</span>
                  <button
                    type="button"
                    className="right-panel__preset-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeletePreservePreset(preset.id);
                    }}
                    aria-label={t("rightPanel.deletePresetAria", {
                      name: preset.name,
                    })}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="right-panel__preserve-checkboxes">
            {PRESERVE_ELEMENTS.map((element) => (
              <label key={element} className="right-panel__checkbox">
                <input
                  type="checkbox"
                  checked={settingsState.changeSettings.preserveElements.includes(
                    element,
                  )}
                  onChange={() => handleTogglePreserveElement(element)}
                />
                <span>{getPreserveElementLabel(element)}</span>
              </label>
            ))}
          </div>

          <div className="right-panel__form-group">
            <label className="right-panel__label">
              {t("rightPanel.changeScope")}
            </label>
            <select
              className="right-panel__select"
              value={settingsState.changeSettings.changeScope}
              onChange={(e) =>
                handleChangeScopeChange(e.target.value as ChangeScope)
              }
            >
              {CHANGE_SCOPES.map((scope) => (
                <option key={scope} value={scope}>
                  {getChangeScopeLabel(scope)}
                </option>
              ))}
            </select>
          </div>

          <div className="right-panel__form-group">
            <label className="right-panel__label">
              {t("rightPanel.otherPreserve")}
            </label>
            <input
              type="text"
              className="right-panel__input"
              value={settingsState.changeSettings.customPreserveText}
              onChange={(e) => handleCustomPreserveTextChange(e.target.value)}
              placeholder={t("rightPanel.preservePlaceholder")}
            />
          </div>

          {/* 保持要素プリセット保存ボタン */}
          <div className="right-panel__attribute-actions">
            <button
              type="button"
              className="right-panel__btn-secondary"
              onClick={() => setShowPreserveSaveModal(true)}
              title={t("rightPanel.savePreservePresetTitle")}
            >
              {t("rightPanel.saveAttributePreset")}
            </button>
          </div>
        </section>

        {/* NovelAI詳細設定 - NovelAIのみ表示（インペイントトグルはCharacterStatePanelに移動済み） */}
        {isNovelAI && (
          <section className="right-panel__section">
            <h4 className="right-panel__section-title">
              {t("rightPanel.novelaiImageSettings")}
            </h4>

            {/* T014: 直接プロンプト */}
            <div className="right-panel__form-group">
              <label className="right-panel__label">
                {t("rightPanel.directPrompt")}
              </label>
              <textarea
                className="right-panel__textarea"
                value={settingsState.inpaintSettings.promptOverride}
                onChange={(e) =>
                  setInpaintSettings({ promptOverride: e.target.value })
                }
                placeholder={t("rightPanel.directPromptPlaceholder")}
                rows={3}
              />
              <small className="right-panel__hint">
                {t("rightPanel.directPromptHint")}
              </small>
            </div>

            {/* T015: ネガティブプロンプト */}
            <div className="right-panel__form-group">
              <label className="right-panel__label">
                {t("rightPanel.negativePrompt")}
              </label>
              <textarea
                className="right-panel__textarea"
                value={settingsState.inpaintSettings.negativePrompt}
                onChange={(e) =>
                  setInpaintSettings({ negativePrompt: e.target.value })
                }
                placeholder={t("rightPanel.negativePromptPlaceholder")}
                rows={2}
              />
              <small className="right-panel__hint">
                {t("rightPanel.negativePromptHint")}
              </small>
            </div>

            {/* T016: i2i強度 */}
            <div className="right-panel__form-group">
              <label className="right-panel__label">
                i2i強度: {settingsState.inpaintSettings.i2iStrength.toFixed(2)}
              </label>
              <input
                type="range"
                className="right-panel__slider"
                min={0.05}
                max={0.99}
                step={0.01}
                value={settingsState.inpaintSettings.i2iStrength}
                onChange={(e) =>
                  setInpaintSettings({
                    i2iStrength: parseFloat(e.target.value),
                  })
                }
              />
              <small className="right-panel__hint">
                {t("rightPanel.i2iStrengthHint")}
              </small>
            </div>

            {/* T017: ノイズ */}
            <div className="right-panel__form-group">
              <label className="right-panel__label">
                {t("rightPanel.inpaintNoiseLabel")}:{" "}
                {settingsState.inpaintSettings.inpaintNoise.toFixed(2)}
              </label>
              <input
                type="range"
                className="right-panel__slider"
                min={0.0}
                max={0.5}
                step={0.01}
                value={settingsState.inpaintSettings.inpaintNoise}
                onChange={(e) =>
                  setInpaintSettings({
                    inpaintNoise: parseFloat(e.target.value),
                  })
                }
              />
              <small className="right-panel__hint">
                {t("rightPanel.inpaintNoiseHint")}
              </small>
            </div>

            {/* US4: Seed input */}
            <div className="right-panel__form-group">
              <label className="right-panel__label">
                {t("rightPanel.seedLabel", "Seed")}
              </label>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="number"
                  className="right-panel__input"
                  min={0}
                  max={999999999}
                  step={1}
                  value={settingsState.seed ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") {
                      setSeed(null);
                      return;
                    }
                    const num = parseInt(raw, 10);
                    if (!isNaN(num) && num >= 0 && num <= 999999999) {
                      setSeed(num);
                    }
                  }}
                  placeholder={t("rightPanel.seedPlaceholder", "Random")}
                  style={{ flex: 1, minWidth: 0 }}
                />
                {settingsState.seed !== null && (
                  <button
                    type="button"
                    className="right-panel__btn-secondary"
                    onClick={() => setSeed(null)}
                    style={{ flexShrink: 0, padding: "0.25rem 0.5rem" }}
                    title={t("rightPanel.seedClear", "Clear seed")}
                  >
                    ✕
                  </button>
                )}
              </div>
              <small className="right-panel__hint">
                {t(
                  "rightPanel.seedHint",
                  "Empty = random. Set a value to reproduce the same image.",
                )}
              </small>
            </div>

            {/* US3: 周囲状況画像生成トグル */}
            <div className="right-panel__form-group">
              <label className="right-panel__toggle">
                <span className="right-panel__toggle-label">
                  {t(
                    "rightPanel.enableSurroundingsImage",
                    "Generate surroundings image",
                  )}
                </span>
                <input
                  type="checkbox"
                  checked={settingsState.enableSurroundingsImage}
                  onChange={(e) => setEnableSurroundingsImage(e.target.checked)}
                  className="right-panel__toggle-input"
                />
                <span className="right-panel__toggle-switch" />
              </label>
              <small className="right-panel__hint">
                {t(
                  "rightPanel.enableSurroundingsImageHint",
                  "Generate an additional image showing the surrounding environment after action instructions. Uses extra Anlas on non-Opus plans.",
                )}
              </small>
            </div>

            {/* Surroundings: include reactive bystanders */}
            {settingsState.enableSurroundingsImage && (
              <div className="right-panel__form-group">
                <label className="right-panel__toggle">
                  <span className="right-panel__toggle-label">
                    {t(
                      "rightPanel.surroundingsIncludePeople",
                      "Include bystanders in surroundings",
                    )}
                  </span>
                  <input
                    type="checkbox"
                    checked={settingsState.surroundingsIncludePeople}
                    onChange={(e) =>
                      setSurroundingsIncludePeople(e.target.checked)
                    }
                    className="right-panel__toggle-input"
                  />
                  <span className="right-panel__toggle-switch" />
                </label>
                <small className="right-panel__hint">
                  {t(
                    "rightPanel.surroundingsIncludePeopleHint",
                    "Include 2-3 reactive bystanders in the surroundings image.",
                  )}
                </small>
              </div>
            )}

            {/* NSFWモードトグル */}
            {/* <label className="right-panel__toggle">
              <span className="right-panel__toggle-label">NSFWモード</span>
              <input
                type="checkbox"
                checked={settingsState.nsfwMode}
                onChange={() => toggleNsfw()}
                className="right-panel__toggle-input"
              />
              <span className="right-panel__toggle-switch" />
            </label> */}

            {/* T024-T025: マスク設定ボタン */}
            {onOpenInpaintModal && (
              <div
                className="right-panel__form-group"
                style={{ marginTop: "1rem" }}
              >
                <button
                  type="button"
                  className="right-panel__btn-secondary"
                  onClick={onOpenInpaintModal}
                  style={{ width: "100%" }}
                >
                  {t("rightPanel.maskSettings")}
                </button>
                <small className="right-panel__hint">
                  {t("rightPanel.maskSettingsHint")}
                </small>
              </div>
            )}

            {/* Precise Reference Images Section */}
            <div
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
                {t("rightPanel.preciseReferenceAnlas")}
              </small>
              <input
                ref={preciseRefInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                style={{ display: "none" }}
                onChange={handlePreciseRefFileChange}
              />
              <button
                type="button"
                className="right-panel__btn-secondary"
                onClick={() => preciseRefInputRef.current?.click()}
                style={{ width: "100%", marginBottom: "0.5rem" }}
              >
                {t("rightPanel.addReferenceImage")}
              </button>

              {preciseRefError && (
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
                  {preciseRefError}
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
                        updatePreciseReference(ref.id, {
                          enabled: !ref.enabled,
                        })
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
          </section>
        )}
        {/* 難易度設定 */}
        {/* <section className="right-panel__section">
          <h4 className="right-panel__section-title">難易度</h4>
          <div className="right-panel__radio-group">
            {difficultyOptions.map((option) => (
              <label key={option.id} className="right-panel__radio">
                <input
                  type="radio"
                  name="difficulty"
                  value={option.id}
                  checked={settingsState.difficulty === option.id}
                  onChange={() => setDifficulty(option.id)}
                  className="right-panel__radio-input"
                />
                <span className="right-panel__radio-label">{option.label}</span>
              </label>
            ))}
          </div>
        </section> */}

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

        {/* 現在の設定サマリー */}
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
            {settingsState.changeSettings.preserveElements.length > 0 && (
              <li>
                {t("rightPanel.preserveLabel")}:{" "}
                {settingsState.changeSettings.preserveElements
                  .map((e) => getPreserveElementLabel(e))
                  .join(", ")}
              </li>
            )}
          </ul>
        </section>
      </div>

      {/* 属性プリセット保存モーダル */}
      {showPresetSaveModal && (
        <div className="right-panel__modal-overlay">
          <div className="right-panel__modal">
            <h4>{t("rightPanel.attributePresetModalTitle")}</h4>
            <input
              type="text"
              className="right-panel__input"
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder={t("rightPanel.presetNamePlaceholder")}
              autoFocus
            />
            <div className="right-panel__modal-actions">
              <button
                type="button"
                className="right-panel__btn-primary"
                onClick={handleSaveAttributePreset}
                disabled={!presetName.trim()}
              >
                {t("common.save")}
              </button>
              <button
                type="button"
                className="right-panel__btn-secondary"
                onClick={() => {
                  setShowPresetSaveModal(false);
                  setPresetName("");
                }}
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 保持要素プリセット保存モーダル */}
      {showPreserveSaveModal && (
        <div className="right-panel__modal-overlay">
          <div className="right-panel__modal">
            <h4>{t("rightPanel.preservePresetModalTitle")}</h4>
            <p className="right-panel__modal-info">
              {t("rightPanel.preserveElementsLabel")}:{" "}
              {settingsState.changeSettings.preserveElements.length > 0
                ? settingsState.changeSettings.preserveElements
                    .map((e) => getPreserveElementLabel(e))
                    .join(", ")
                : t("common.none")}
            </p>
            <input
              type="text"
              className="right-panel__input"
              value={preservePresetName}
              onChange={(e) => setPreservePresetName(e.target.value)}
              placeholder={t("rightPanel.presetNamePlaceholder")}
              autoFocus
            />
            <div className="right-panel__modal-actions">
              <button
                type="button"
                className="right-panel__btn-primary"
                onClick={handleSavePreservePreset}
                disabled={!preservePresetName.trim()}
              >
                {t("common.save")}
              </button>
              <button
                type="button"
                className="right-panel__btn-secondary"
                onClick={() => {
                  setShowPreserveSaveModal(false);
                  setPreservePresetName("");
                }}
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
