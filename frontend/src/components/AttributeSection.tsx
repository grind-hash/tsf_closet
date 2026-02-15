import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AttributePreset } from "../types";
import "./AttributeSection.css";

export interface Attribute {
  id: string;
  text: string;
}

interface AttributeSectionProps {
  attributes: Attribute[];
  onAttributesChange: (attributes: Attribute[]) => void;
}

const STORAGE_KEY = "tsf-closet-attribute-presets";

export function AttributeSection({
  attributes,
  onAttributesChange,
}: AttributeSectionProps) {
  const { t } = useTranslation();
  // 入力関連
  const [showInput, setShowInput] = useState(false);
  const [inputText, setInputText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // プリセット関連 (初期値でlocalStorageから読み込み)
  const [presets, setPresets] = useState<AttributePreset[]>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return JSON.parse(stored) as AttributePreset[];
      } catch (e) {
        console.warn("Failed to parse attribute presets", e);
      }
    }
    return [];
  });
  const [selectedPresetId, setSelectedPresetId] = useState<string>("");
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [presetName, setPresetName] = useState("");

  // ホバー状態
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // 削除確認
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // プリセット保存
  const savePresetsToStorage = (newPresets: AttributePreset[]) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newPresets));
    setPresets(newPresets);
  };

  // 属性追加/更新
  const handleAddAttribute = () => {
    const text = inputText.trim();
    if (!text) return;

    if (editingId) {
      // 更新
      const updated = attributes.map((a) =>
        a.id === editingId ? { ...a, text } : a,
      );
      onAttributesChange(updated);
    } else {
      // 追加
      const newAttr: Attribute = {
        id: crypto.randomUUID(),
        text,
      };
      onAttributesChange([...attributes, newAttr]);
    }

    setInputText("");
    setEditingId(null);
    setShowInput(false);
  };

  // 属性編集開始
  const handleEdit = (attr: Attribute) => {
    setEditingId(attr.id);
    setInputText(attr.text);
    setShowInput(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  // 属性削除
  const handleDelete = (id: string) => {
    setDeleteConfirmId(id);
  };

  const confirmDelete = () => {
    if (deleteConfirmId) {
      onAttributesChange(attributes.filter((a) => a.id !== deleteConfirmId));
      setDeleteConfirmId(null);
    }
  };

  // キャンセル
  const handleCancel = () => {
    setInputText("");
    setEditingId(null);
    setShowInput(false);
  };

  // Enter キー対応
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleAddAttribute();
    } else if (e.key === "Escape") {
      handleCancel();
    }
  };

  // プリセット選択
  const handlePresetSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    setSelectedPresetId(id);
    if (id) {
      const preset = presets.find((p) => p.id === id);
      if (preset) {
        onAttributesChange(
          preset.attributes.map((text) => ({
            id: crypto.randomUUID(),
            text,
          })),
        );
      }
    }
  };

  // プリセット保存
  const handleSavePreset = () => {
    const name = presetName.trim();
    if (!name || attributes.length === 0) return;

    const newPreset: AttributePreset = {
      id: crypto.randomUUID(),
      name,
      attributes: attributes.map((a) => a.text),
      createdAt: new Date().toISOString(),
    };

    const updated = [...presets, newPreset];
    savePresetsToStorage(updated);
    setPresetName("");
    setShowSaveDialog(false);
    setSelectedPresetId(newPreset.id);
  };

  // プリセット削除
  const handleDeletePreset = () => {
    if (!selectedPresetId) return;
    const updated = presets.filter((p) => p.id !== selectedPresetId);
    savePresetsToStorage(updated);
    setSelectedPresetId("");
  };

  return (
    <div className="attribute-section">
      {/* ヘッダー：タイトル + プリセット操作 */}
      <div className="attribute-section-header">
        <span className="attribute-section-title">
          {t("attributeSection.title")}
        </span>
        <div className="attribute-preset-controls">
          <select
            className="attribute-preset-select"
            value={selectedPresetId}
            onChange={handlePresetSelect}
          >
            <option value="">{t("attributeSection.presetPlaceholder")}</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="attribute-preset-btn attribute-preset-save-btn"
            onClick={() => setShowSaveDialog(true)}
            disabled={attributes.length === 0}
            title={t("attributeSection.saveCurrentPresetTitle")}
          >
            {t("attributeSection.save")}
          </button>
          {selectedPresetId && (
            <button
              type="button"
              className="attribute-preset-btn attribute-preset-delete-btn"
              onClick={handleDeletePreset}
              title={t("attributeSection.deleteSelectedPresetTitle")}
            >
              {t("attributeSection.delete")}
            </button>
          )}
        </div>
      </div>

      {/* 属性バッジ一覧 */}
      <div className="attribute-badges-container">
        {attributes.length === 0 ? (
          <span className="attribute-empty-message">
            {t("attributeSection.empty")}
          </span>
        ) : (
          attributes.map((attr) => (
            <span
              key={attr.id}
              className={`attribute-badge ${hoveredId === attr.id ? "hovered" : ""}`}
              onMouseEnter={() => setHoveredId(attr.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => handleEdit(attr)}
            >
              <span className="badge-text">{attr.text}</span>
              <span className="badge-actions">
                <button
                  type="button"
                  className="badge-action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleEdit(attr);
                  }}
                  title={t("attributeSection.editTitle")}
                >
                  ✏️
                </button>
                <button
                  type="button"
                  className="badge-action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(attr.id);
                  }}
                  title={t("attributeSection.deleteTitle")}
                >
                  🗑️
                </button>
              </span>
            </span>
          ))
        )}
        {!showInput && (
          <button
            type="button"
            className="attribute-add-btn"
            onClick={() => {
              setShowInput(true);
              setEditingId(null);
              setInputText("");
              setTimeout(() => inputRef.current?.focus(), 0);
            }}
          >
            {t("attributeSection.add")}
          </button>
        )}
      </div>

      {/* 入力エリア */}
      {showInput && (
        <div className="attribute-input-area">
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t("attributeSection.inputPlaceholder")}
            maxLength={100}
          />
          <button
            type="button"
            className="btn-primary"
            onClick={handleAddAttribute}
          >
            {editingId
              ? t("attributeSection.update")
              : t("attributeSection.add")}
          </button>
          <button type="button" className="btn-outline" onClick={handleCancel}>
            {t("attributeSection.close")}
          </button>
        </div>
      )}

      {/* 削除確認モーダル */}
      {deleteConfirmId && (
        <div
          className="attribute-dialog-overlay"
          onClick={() => setDeleteConfirmId(null)}
        >
          <div
            className="attribute-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="attribute-dialog-title">
              {t("attributeSection.deleteHeading")}
            </div>
            <p>
              {t("attributeSection.deleteConfirm", {
                name:
                  attributes.find((a) => a.id === deleteConfirmId)?.text ?? "",
              })}
            </p>
            <div className="attribute-dialog-buttons">
              <button
                type="button"
                className="attribute-dialog-btn attribute-dialog-btn-cancel"
                onClick={() => setDeleteConfirmId(null)}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="attribute-dialog-btn attribute-preset-delete-btn"
                onClick={confirmDelete}
              >
                {t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* プリセット保存ダイアログ */}
      {showSaveDialog && (
        <div
          className="attribute-dialog-overlay"
          onClick={() => setShowSaveDialog(false)}
        >
          <div
            className="attribute-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="attribute-dialog-title">
              {t("attributeSection.saveAsPreset")}
            </div>
            <input
              type="text"
              className="attribute-dialog-input"
              placeholder={t("attributeSection.presetNamePlaceholder")}
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              maxLength={50}
              autoFocus
            />
            <div className="attribute-dialog-buttons">
              <button
                type="button"
                className="attribute-dialog-btn attribute-dialog-btn-cancel"
                onClick={() => {
                  setShowSaveDialog(false);
                  setPresetName("");
                }}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="attribute-dialog-btn attribute-dialog-btn-save"
                onClick={handleSavePreset}
                disabled={!presetName.trim()}
              >
                {t("common.save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
