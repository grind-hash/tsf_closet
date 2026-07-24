/**
 * CharacterStatePanel - キャラクター状態パネル（縦レイアウト）
 * 007-chat-interactive-ux
 *
 * 刷新版: 左パネルとして縦に配置
 * 構成:
 * - キャラクター画像（大きく表示）
 * - 履歴ナビゲーション（← →）
 * - インペイントトグル (NovelAIのみ) - FR-017準拠
 * - 属性一覧（追加/削除/プリセット保存・読込機能付き）
 * - パラメータ表示 (bloom, shame, adaptation)
 */

import { useState, useRef, useEffect, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import { useChat } from "../../contexts/ChatContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { AttributePreset } from "../../types";
import "./CharacterStatePanel.css";

// 属性プリセット用のlocalStorageキー（RightPanelと共通）
const ATTRIBUTE_PRESET_STORAGE_KEY = "attribute_presets";

interface CharacterStatePanelProps {
  onImageClick?: () => void;
  onInpaintToggle?: (enabled: boolean) => void;
  onOpenInpaintModal?: () => void;
  transformationCount?: number;
  isTransforming?: boolean;
  /** NSFWトグルを表示するか（デフォルト: true） */
  showNsfwToggle?: boolean;
}

export default function CharacterStatePanel({
  onImageClick,
  onInpaintToggle,
  onOpenInpaintModal,
  transformationCount = 0,
  isTransforming = false,
  showNsfwToggle = true,
}: CharacterStatePanelProps) {
  const { t } = useTranslation();
  const {
    state,
    navigateHistory,
    navigatePrevHistory,
    navigateNextHistory,
    addAttribute,
    removeAttribute,
  } = useGame();
  const { scrollToMessage, highlightMessage, state: chatState } = useChat();
  const { state: settingsState, toggleInpaint, toggleNsfw } = useSettings();

  // 属性入力状態
  const [showAttributeInput, setShowAttributeInput] = useState(false);
  const [attributeText, setAttributeText] = useState("");
  const [isAddingAttribute, setIsAddingAttribute] = useState(false);
  const [editingAttributeId, setEditingAttributeId] = useState<string | null>(
    null,
  );
  const attributeInputRef = useRef<HTMLInputElement>(null);

  // 属性プリセット状態
  const [attributePresets, setAttributePresets] = useState<AttributePreset[]>(
    [],
  );
  const [showPresetSaveModal, setShowPresetSaveModal] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [showPresetList, setShowPresetList] = useState(false);

  // 属性プリセットをlocalStorageから読み込み
  useEffect(() => {
    try {
      const saved = localStorage.getItem(ATTRIBUTE_PRESET_STORAGE_KEY);
      if (saved) {
        setAttributePresets(JSON.parse(saved));
      }
    } catch {
      console.error("Failed to load attribute presets");
    }
  }, []);

  // localStorageの変更を監視（他コンポーネントからの変更を反映）
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === ATTRIBUTE_PRESET_STORAGE_KEY && e.newValue) {
        try {
          setAttributePresets(JSON.parse(e.newValue));
        } catch {
          console.error("Failed to parse attribute presets");
        }
      }
    };
    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  // インペイントトグルハンドラ
  const handleInpaintToggle = (event: ChangeEvent<HTMLInputElement>) => {
    const newEnabled = event.target.checked;
    toggleInpaint();
    onInpaintToggle?.(newEnabled);
  };

  const {
    character,
    currentImage,
    stats,
    history: rawHistory,
    currentHistoryIndex,
    attributes,
  } = state;
  // historyが配列でない場合のフォールバック
  const history = Array.isArray(rawHistory) ? rawHistory : [];
  const isNovelAI = settingsState.imageProvider === "novelai";
  const historyStripRef = useRef<HTMLDivElement>(null);

  // 選択中のサムネイルが横方向の表示範囲外に出た場合だけ中央へ寄せる
  useEffect(() => {
    const strip = historyStripRef.current;
    if (!strip) return;

    const activeThumbnail = strip.querySelector<HTMLElement>(
      `[data-history-index="${currentHistoryIndex}"]`,
    );
    if (!activeThumbnail) return;

    const visibleLeft = strip.scrollLeft;
    const visibleRight = visibleLeft + strip.clientWidth;
    const thumbnailLeft = activeThumbnail.offsetLeft;
    const thumbnailRight = thumbnailLeft + activeThumbnail.offsetWidth;

    if (thumbnailLeft >= visibleLeft && thumbnailRight <= visibleRight) {
      return;
    }

    strip.scrollTo({
      left:
        thumbnailLeft - (strip.clientWidth - activeThumbnail.offsetWidth) / 2,
      behavior: "smooth",
    });
  }, [currentHistoryIndex, history.length]);

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

  // 属性プリセット保存
  const handleSaveAttributePreset = () => {
    if (!presetName.trim() || attributes.length === 0) return;

    const newPreset: AttributePreset = {
      id: Date.now().toString(),
      name: presetName.trim(),
      attributes: attributes.map((a) => a.text),
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
    setShowPresetList(false);
  };

  // 属性プリセット削除
  const handleDeleteAttributePreset = (id: string) => {
    const updated = attributePresets.filter((p) => p.id !== id);
    setAttributePresets(updated);
    localStorage.setItem(ATTRIBUTE_PRESET_STORAGE_KEY, JSON.stringify(updated));
  };

  // 履歴選択時にチャットメッセージへスクロール
  const handleHistoryNavigate = (direction: "prev" | "next") => {
    if (direction === "prev") {
      navigatePrevHistory();
    } else {
      navigateNextHistory();
    }

    // linkChatToImage が有効な場合のみ、対応メッセージにスクロール
    if (!settingsState.linkChatToImage) return;

    // 遷移先の履歴に対応するメッセージIDを取得
    const targetIndex =
      direction === "prev" ? currentHistoryIndex - 1 : currentHistoryIndex + 1;
    const targetHistory = history[targetIndex];

    if (targetHistory?.relatedMessageId) {
      scrollToMessage(targetHistory.relatedMessageId);
      highlightMessage(targetHistory.relatedMessageId, 2000);
    }
  };

  // サムネイルクリック時の履歴ジャンプ
  const handleThumbnailClick = (index: number) => {
    if (index === currentHistoryIndex) return;

    // GameContextのnavigate関数を使って指定インデックスにジャンプ
    navigateHistory(index);

    // linkChatToImage が有効な場合のみ、対応メッセージにスクロール
    if (!settingsState.linkChatToImage) return;

    const targetHistory = history[index];
    if (targetHistory?.relatedMessageId) {
      scrollToMessage(targetHistory.relatedMessageId);
      highlightMessage(targetHistory.relatedMessageId, 2000);
    }
  };

  const canNavigatePrev = currentHistoryIndex > 0;
  const canNavigateNext = currentHistoryIndex < history.length - 1;

  // パラメータバー幅計算 (0-100)
  const getBarWidth = (value: number | undefined) => {
    return Math.max(0, Math.min(100, value ?? 0));
  };

  // Center-origin adaptation bar style (-50~50 -> left/width from center)
  const getAdaptationBarStyle = (value: number | undefined) => {
    const clamped = Math.max(-50, Math.min(50, value ?? 0));
    const normalized = clamped + 50; // 0-100, 50 = center
    const barWidth = Math.abs(normalized - 50);
    const barLeft = Math.min(normalized, 50);
    return { width: `${barWidth}%`, left: `${barLeft}%` };
  };

  return (
    <div className="character-state-panel">
      <div className="character-state-panel__primary">
        {/* NSFWモードトグル（左上） */}
        {showNsfwToggle && (
          <div className="character-state-panel__nsfw-toggle">
            <label className="character-state-panel__toggle character-state-panel__toggle--nsfw">
              <span className="character-state-panel__toggle-label">
                🔞 NSFW
              </span>
              <input
                type="checkbox"
                checked={settingsState.nsfwMode}
                onChange={() => toggleNsfw()}
                className="character-state-panel__toggle-input"
              />
              <span className="character-state-panel__toggle-switch character-state-panel__toggle-switch--nsfw" />
            </label>
          </div>
        )}

        {/* キャラクター名 */}
        {character && (
          <h2 className="character-state-panel__name">{character.name}</h2>
        )}

        {/* キャラクター画像 */}
        <div className="character-state-panel__image-container">
          {currentImage ? (
            <button
              type="button"
              className="character-state-panel__image-btn"
              onClick={onImageClick}
              aria-label={t("characterPanel.expandImage")}
            >
              <img
                src={currentImage}
                alt={character?.name || t("characterPanel.characterAlt")}
                className="character-state-panel__image"
              />
            </button>
          ) : (
            <div className="character-state-panel__no-image">
              <span>{t("characterPanel.noImage")}</span>
            </div>
          )}

          {/* 変身中/行動中オーバーレイ */}
          {isTransforming && (
            <div className="character-state-panel__loading-overlay">
              <div className="character-state-panel__spinner" />
              <p>
                {chatState.instructionType === "action"
                  ? t("characterPanel.acting")
                  : t("characterPanel.transforming")}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 変身経過サムネイル */}
      {history.length > 1 && (
        <div
          ref={historyStripRef}
          className="character-state-panel__history-strip"
        >
          {history.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={`character-state-panel__history-thumb ${
                index === currentHistoryIndex ? "is-active" : ""
              }`}
              data-history-index={index}
              onClick={() => handleThumbnailClick(index)}
              aria-label={t("characterPanel.transformHistory", {
                index: index + 1,
              })}
              title={
                item.instruction ||
                t("characterPanel.transformHistory", { index: index + 1 })
              }
            >
              <img
                src={item.imageUrl}
                alt={t("characterPanel.transformHistory", {
                  index: index + 1,
                })}
                loading="lazy"
              />
              <span className="character-state-panel__history-thumb-num">
                {index + 1}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* 履歴ナビゲーション（4ボタン） - 常に表示 */}
      <div className="character-state-panel__nav-full">
        <button
          type="button"
          className="character-state-panel__nav-btn"
          onClick={() => handleThumbnailClick(0)}
          disabled={history.length === 0 || currentHistoryIndex === 0}
          aria-label={t("characterPanel.navFirstAria")}
          title={t("characterPanel.navFirstTitle")}
        >
          «
        </button>
        <button
          type="button"
          className="character-state-panel__nav-btn"
          onClick={() => handleHistoryNavigate("prev")}
          disabled={history.length === 0 || !canNavigatePrev}
          aria-label={t("characterPanel.navPrevAria")}
          title={t("characterPanel.navPrevTitle")}
        >
          ‹
        </button>
        <span className="character-state-panel__nav-count">
          {history.length > 0
            ? `${currentHistoryIndex + 1} / ${history.length}`
            : "0 / 0"}
        </span>
        <button
          type="button"
          className="character-state-panel__nav-btn"
          onClick={() => handleHistoryNavigate("next")}
          disabled={history.length === 0 || !canNavigateNext}
          aria-label={t("characterPanel.navNextAria")}
          title={t("characterPanel.navNextTitle")}
        >
          ›
        </button>
        <button
          type="button"
          className="character-state-panel__nav-btn"
          onClick={() => handleThumbnailClick(history.length - 1)}
          disabled={
            history.length === 0 || currentHistoryIndex === history.length - 1
          }
          aria-label={t("characterPanel.navLastAria")}
          title={t("characterPanel.navLastTitle")}
        >
          »
        </button>
      </div>
      {/* インペイントトグル - NovelAIのみ表示 (FR-017準拠) */}
      {isNovelAI && (
        <div className="character-state-panel__inpaint-toggle">
          <label className="character-state-panel__toggle">
            <span className="character-state-panel__toggle-label">
              {t("characterPanel.inpaintMode")}
            </span>
            <input
              type="checkbox"
              checked={settingsState.inpaintEnabled}
              onChange={handleInpaintToggle}
              className="character-state-panel__toggle-input"
            />
            <span className="character-state-panel__toggle-switch" />
          </label>
          {/* インペイント有効時のマスク編集ボタン */}
          {settingsState.inpaintEnabled && onOpenInpaintModal && (
            <button
              type="button"
              className="character-state-panel__mask-edit-btn"
              onClick={onOpenInpaintModal}
              title={t("characterPanel.editMaskTitle")}
            >
              {t("characterPanel.editMask")}
            </button>
          )}
        </div>
      )}

      {/* 属性セクション */}
      <div className="character-state-panel__attributes-section">
        <h4 className="character-state-panel__section-title">
          {t("characterPanel.attributes")}
        </h4>
        <div className="character-state-panel__attributes">
          {attributes.map((attr) => (
            <span
              key={attr.id}
              className="character-state-panel__attribute-badge"
            >
              <span className="character-state-panel__attribute-text">
                {attr.text}
              </span>
              <button
                type="button"
                className="character-state-panel__attribute-action"
                onClick={() => handleEditAttribute(attr.id, attr.text)}
                aria-label={t("characterPanel.editAttrAria", {
                  text: attr.text,
                })}
                title={t("common.edit")}
              >
                ✎
              </button>
              <button
                type="button"
                className="character-state-panel__attribute-action"
                onClick={() => handleRemoveAttribute(attr.id)}
                aria-label={t("characterPanel.deleteAttrAria", {
                  text: attr.text,
                })}
                title={t("common.delete")}
              >
                ×
              </button>
            </span>
          ))}

          {/* 追加ボタン / 入力フォーム */}
          {showAttributeInput ? (
            <div className="character-state-panel__attribute-input">
              <input
                ref={attributeInputRef}
                type="text"
                value={attributeText}
                onChange={(e) => setAttributeText(e.target.value)}
                onKeyDown={handleAttributeKeyDown}
                placeholder={t("characterPanel.attrPlaceholder")}
                maxLength={50}
                disabled={isAddingAttribute}
              />
              <button
                type="button"
                className="character-state-panel__btn-add"
                onClick={handleAddAttribute}
                disabled={isAddingAttribute || !attributeText.trim()}
              >
                {isAddingAttribute
                  ? t("rightPanel.loadingDots")
                  : editingAttributeId
                    ? t("common.update")
                    : "✓"}
              </button>
              <button
                type="button"
                className="character-state-panel__btn-cancel"
                onClick={() => {
                  setShowAttributeInput(false);
                  setAttributeText("");
                  setEditingAttributeId(null);
                }}
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="character-state-panel__attribute-add-btn"
              onClick={() => {
                setShowAttributeInput(true);
                setTimeout(() => attributeInputRef.current?.focus(), 0);
              }}
            >
              {t("characterPanel.addMore")}
            </button>
          )}
        </div>

        {/* プリセット管理ボタン */}
        <div className="character-state-panel__preset-actions">
          <button
            type="button"
            className="character-state-panel__preset-btn"
            onClick={() => setShowPresetList(!showPresetList)}
            title={t("characterPanel.loadPresetTitle")}
          >
            {t("characterPanel.loadPresetButton")}
          </button>
          <button
            type="button"
            className="character-state-panel__preset-btn"
            onClick={() => setShowPresetSaveModal(true)}
            disabled={attributes.length === 0}
            title={t("characterPanel.saveCurrentAttrsTitle")}
          >
            {t("characterPanel.savePresetButton")}
          </button>
        </div>

        {/* プリセット一覧ドロップダウン */}
        {showPresetList && (
          <div className="character-state-panel__preset-list">
            {attributePresets.length === 0 ? (
              <p className="character-state-panel__preset-empty">
                {t("characterPanel.noPresets")}
              </p>
            ) : (
              attributePresets.map((preset) => (
                <div
                  key={preset.id}
                  className="character-state-panel__preset-item"
                >
                  <button
                    type="button"
                    className="character-state-panel__preset-load-btn"
                    onClick={() => handleLoadAttributePreset(preset)}
                    title={preset.attributes.join(", ")}
                  >
                    {preset.name}
                  </button>
                  <button
                    type="button"
                    className="character-state-panel__preset-delete-btn"
                    onClick={() => handleDeleteAttributePreset(preset.id)}
                    title={t("common.delete")}
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {/* プリセット保存モーダル */}
        {showPresetSaveModal && (
          <div className="character-state-panel__preset-modal">
            <div className="character-state-panel__preset-modal-content">
              <h5>{t("characterPanel.savePresetHeading")}</h5>
              <input
                type="text"
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                placeholder={t("characterPanel.presetNamePlaceholder")}
                maxLength={30}
              />
              <div className="character-state-panel__preset-modal-actions">
                <button
                  type="button"
                  onClick={handleSaveAttributePreset}
                  disabled={!presetName.trim()}
                >
                  {t("common.save")}
                </button>
                <button
                  type="button"
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
      </div>

      {/* パラメータ表示 */}
      {stats && (
        <div className="character-state-panel__stats">
          {/* 変身回数 (両モード共通) */}
          <div className="character-state-panel__stat character-state-panel__stat--count">
            <span className="character-state-panel__stat-label">
              {t("characterPanel.transformCountLabel")}
            </span>
            <span className="character-state-panel__stat-value character-state-panel__stat-value--count">
              {t("characterPanel.transformCountValue", {
                count: transformationCount,
              })}
            </span>
          </div>

          {/* 自分自身モード インジケーター */}
          {state.selfMode && (
            <>
              <div className="character-state-panel__self-mode-badge">
                <span className="character-state-panel__self-mode-icon">
                  👤
                </span>
                <span className="character-state-panel__self-mode-label">
                  {t("characterPanel.selfModeLabel")}
                </span>
              </div>
              <p className="character-state-panel__self-mode-desc">
                {t("characterPanel.selfModeDesc")}
              </p>
            </>
          )}

          {/* パラメータバー (通常モードのみ) */}
          {!state.selfMode && (
            <>
              <div className="character-state-panel__stat">
                <span className="character-state-panel__stat-label">
                  {t("characterPanel.bloom")}
                </span>
                <div className="character-state-panel__stat-bar">
                  <div
                    className="character-state-panel__stat-fill character-state-panel__stat-fill--bloom"
                    style={{ width: `${getBarWidth(stats.bloom)}%` }}
                  />
                </div>
                <span className="character-state-panel__stat-value">
                  {stats.bloom ?? 0}
                </span>
              </div>

              <div className="character-state-panel__stat">
                <span className="character-state-panel__stat-label">
                  {t("characterPanel.shame")}
                </span>
                <div className="character-state-panel__stat-bar">
                  <div
                    className="character-state-panel__stat-fill character-state-panel__stat-fill--shame"
                    style={{ width: `${getBarWidth(stats.shame)}%` }}
                  />
                </div>
                <span className="character-state-panel__stat-value">
                  {stats.shame ?? 0}
                </span>
              </div>

              <div className="character-state-panel__stat">
                <span className="character-state-panel__stat-label">
                  {t("characterPanel.adaptation")}
                </span>
                <div className="character-state-panel__adaptation-meter">
                  <div className="character-state-panel__adaptation-labels">
                    <span>{t("characterPanel.adaptationSexy")}</span>
                    <span>{t("characterPanel.adaptationNeutral")}</span>
                    <span>{t("characterPanel.adaptationCute")}</span>
                  </div>
                  <div
                    className="character-state-panel__stat-bar character-state-panel__stat-bar--adaptation"
                    style={{ height: "10px", minHeight: "10px" }}
                  >
                    <div
                      className={`character-state-panel__stat-fill character-state-panel__stat-fill--adaptation ${
                        (stats.adaptation ?? 0) < 0
                          ? "character-state-panel__stat-fill--adaptation-sexy"
                          : "character-state-panel__stat-fill--adaptation-cute"
                      }`}
                      style={getAdaptationBarStyle(stats.adaptation)}
                    />
                    <span className="character-state-panel__adaptation-center" />
                  </div>
                </div>
                <span className="character-state-panel__stat-value">
                  {stats.adaptation ?? 0}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* 現在の状態説明 */}
      {history[currentHistoryIndex]?.afterDescription && (
        <p className="character-state-panel__description">
          {history[currentHistoryIndex].afterDescription}
        </p>
      )}
    </div>
  );
}
