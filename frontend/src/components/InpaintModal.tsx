/**
 * InpaintModal - インペイント専用モーダルコンポーネント
 * マスク描画、履歴/プリセット選択、パラメータ設定を集約
 */

import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ReactSketchCanvas,
  type ReactSketchCanvasRef,
} from "react-sketch-canvas";
import type { InpaintSettings, MaskInfo, MaskListResponse } from "../types";
import { DEFAULT_INPAINT_SETTINGS } from "../types";
import { API_BASE } from "../utils/api";
import "./InpaintModal.css";

interface InpaintModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (
    settings: InpaintSettings,
    maskDataUrl: string | null,
    selectedMaskId: string | null,
  ) => void;
  currentImageUrl: string | null;
  initialSettings?: InpaintSettings;
  initialMaskId?: string | null;
  initialMaskDataUrl?: string | null;
}

export default function InpaintModal({
  isOpen,
  onClose,
  onApply,
  currentImageUrl,
  initialSettings,
  initialMaskId,
  initialMaskDataUrl,
}: InpaintModalProps) {
  const { t } = useTranslation();
  // 設定state
  const [settings, setSettings] = useState<InpaintSettings>(
    initialSettings ?? DEFAULT_INPAINT_SETTINGS,
  );

  // マスク関連state
  const [maskPresetUrl, setMaskPresetUrl] = useState<string | null>(null);
  const [selectedMaskId, setSelectedMaskId] = useState<string | null>(
    initialMaskId ?? null,
  );
  const [maskList, setMaskList] = useState<MaskListResponse>({
    system: [],
    history: [],
    presets: [],
  });
  const [maskLoading, setMaskLoading] = useState(false);

  // プリセット保存ダイアログ用
  const [showPresetSaveDialog, setShowPresetSaveDialog] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [isSavingPreset, setIsSavingPreset] = useState(false);

  // プリセット削除確認用
  const [deleteConfirmMaskId, setDeleteConfirmMaskId] = useState<string | null>(
    null,
  );

  // キャンバスサイズ
  const [canvasSize, setCanvasSize] = useState({ width: 512, height: 768 });
  const [baseImageSize, setBaseImageSize] = useState({
    width: 512,
    height: 768,
  });

  const maskCanvasRef = useRef<ReactSketchCanvasRef>(null);

  // モーダルが開いたときに設定を初期化
  // biome-ignore lint/correctness/useExhaustiveDependencies: loadMaskList は安定したローカル関数
  useEffect(() => {
    if (isOpen) {
      setSettings(initialSettings ?? DEFAULT_INPAINT_SETTINGS);
      setSelectedMaskId(initialMaskId ?? null);
      loadMaskList();
      setMaskPresetUrl(initialMaskDataUrl ?? null);
    }
  }, [isOpen, initialSettings, initialMaskId, initialMaskDataUrl]);

  // 画像サイズに合わせてキャンバスをリサイズ
  useEffect(() => {
    if (!currentImageUrl || !isOpen) return;
    const img = new Image();
    img.onload = () => {
      // モーダル内で表示するため、最大サイズを制限
      const maxWidth = 600;
      const maxHeight = 500;
      const ratio = Math.min(
        maxWidth / img.naturalWidth,
        maxHeight / img.naturalHeight,
        1,
      );
      setCanvasSize({
        width: Math.round(img.naturalWidth * ratio),
        height: Math.round(img.naturalHeight * ratio),
      });
      setBaseImageSize({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.crossOrigin = "anonymous";
    img.src = currentImageUrl;
  }, [currentImageUrl, isOpen]);

  // マスク一覧を取得
  const loadMaskList = async () => {
    try {
      const res = await fetch(`${API_BASE}/game/masks`);
      if (res.ok) {
        const data: MaskListResponse = await res.json();
        setMaskList(data);
      }
    } catch (e) {
      console.warn("Failed to load masks", e);
    }
  };

  // マスクを選択・適用
  const handleSelectMask = async (mask: MaskInfo) => {
    setMaskLoading(true);
    try {
      const res = await fetch(mask.url);
      if (res.ok) {
        const blob = await res.blob();
        const reader = new FileReader();
        reader.onload = () => {
          const dataUrl = reader.result as string;
          setMaskPresetUrl(dataUrl);
          setSelectedMaskId(mask.id);
          // キャンバスをクリア（プリセットが背景になる）
          maskCanvasRef.current?.resetCanvas();
        };
        reader.readAsDataURL(blob);
      }
    } catch (e) {
      console.warn("Failed to load mask", e);
    } finally {
      setMaskLoading(false);
    }
  };

  // 保存用の固定サイズ（アルファチャンネル付き、小さいサイズで保存）
  const MASK_SAVE_WIDTH = 104;
  const MASK_SAVE_HEIGHT = 152;

  // マスクを合成（プリセット + ストローク）→ 104x152pxでアルファチャンネル付きで返却
  const mergeMask = useCallback(async (): Promise<string | null> => {
    console.log("[InpaintModal] mergeMask called");
    console.log(
      "[InpaintModal] maskPresetUrl:",
      maskPresetUrl ? "set" : "null",
    );
    console.log(
      "[InpaintModal] maskCanvasRef.current:",
      maskCanvasRef.current ? "exists" : "null",
    );

    // 1) 作業用キャンバス（元画像サイズ）でマスクを合成
    const workCanvas = document.createElement("canvas");
    workCanvas.width = baseImageSize.width;
    workCanvas.height = baseImageSize.height;
    console.log(
      "[InpaintModal] workCanvas size:",
      workCanvas.width,
      "x",
      workCanvas.height,
    );
    const workCtx = workCanvas.getContext("2d");
    if (!workCtx) {
      console.error("[InpaintModal] Failed to get workCanvas context");
      return null;
    }
    workCtx.clearRect(0, 0, workCanvas.width, workCanvas.height);

    // 1-1) プリセット
    if (maskPresetUrl) {
      console.log("[InpaintModal] Drawing preset mask");
      const presetImg = new Image();
      presetImg.src = maskPresetUrl;
      await presetImg
        .decode()
        .catch((e) => console.error("[InpaintModal] Preset decode error:", e));
      workCtx.drawImage(presetImg, 0, 0, workCanvas.width, workCanvas.height);
    }

    // 1-2) ストローク (react-sketch-canvas)
    if (maskCanvasRef.current) {
      const strokeDataUrl = await maskCanvasRef.current.exportImage("png");
      console.log(
        "[InpaintModal] strokeDataUrl:",
        strokeDataUrl ? `${strokeDataUrl.length} chars` : "null",
      );
      if (strokeDataUrl) {
        const strokeImg = new Image();
        strokeImg.src = strokeDataUrl;
        await strokeImg
          .decode()
          .catch((e) =>
            console.error("[InpaintModal] Stroke decode error:", e),
          );
        workCtx.drawImage(strokeImg, 0, 0, workCanvas.width, workCanvas.height);
      }
    }

    // 2) 104x152に縮小してアルファチャンネル付きで保存
    const saveCanvas = document.createElement("canvas");
    saveCanvas.width = MASK_SAVE_WIDTH;
    saveCanvas.height = MASK_SAVE_HEIGHT;
    const saveCtx = saveCanvas.getContext("2d");
    if (!saveCtx) {
      console.error("[InpaintModal] Failed to get saveCanvas context");
      return null;
    }
    saveCtx.clearRect(0, 0, MASK_SAVE_WIDTH, MASK_SAVE_HEIGHT);
    saveCtx.drawImage(workCanvas, 0, 0, MASK_SAVE_WIDTH, MASK_SAVE_HEIGHT);

    // 3) アルファチャンネルを保持（白+アルファ形式）
    const imageData = saveCtx.getImageData(
      0,
      0,
      MASK_SAVE_WIDTH,
      MASK_SAVE_HEIGHT,
    );
    const data = imageData.data;
    let alphaPixels = 0;
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a > 0) {
        data[i] = 255; // R
        data[i + 1] = 255; // G
        data[i + 2] = 255; // B
        // アルファは元の値を保持（アルファチャンネル付き）
        alphaPixels++;
      }
      // a == 0 の場合は透明のまま
    }
    console.log(
      `[InpaintModal] Mask has ${alphaPixels} non-transparent pixels out of ${data.length / 4}`,
    );
    saveCtx.putImageData(imageData, 0, 0);

    const result = saveCanvas.toDataURL("image/png");
    console.log(`[InpaintModal] mergeMask result: ${result.length} chars`);
    return result;
  }, [maskPresetUrl, baseImageSize]);

  // クリア
  const handleClearMask = () => {
    maskCanvasRef.current?.resetCanvas();
    setMaskPresetUrl(null);
    setSelectedMaskId(null);
  };

  // 適用
  const handleApply = async () => {
    console.log("[InpaintModal] handleApply called");
    const mergedMask = await mergeMask();
    console.log(
      "[InpaintModal] mergedMask:",
      mergedMask ? `${mergedMask.length} chars` : "null",
    );
    console.log("[InpaintModal] selectedMaskId:", selectedMaskId);
    onApply({ ...settings, enabled: true }, mergedMask, selectedMaskId);
  };

  // キャンセル
  const handleCancel = () => {
    onClose();
  };

  // プリセット保存
  const handleSavePreset = async () => {
    if (!presetName.trim()) return;
    setIsSavingPreset(true);
    try {
      const mergedMask = await mergeMask();
      if (!mergedMask) {
        setIsSavingPreset(false);
        return;
      }
      const res = await fetch(`${API_BASE}/game/masks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mask_base64: mergedMask,
          name: presetName.trim(),
        }),
      });
      if (res.ok) {
        const data: MaskListResponse = await res.json();
        setMaskList(data);
        setPresetName("");
        setShowPresetSaveDialog(false);
      }
    } catch (e) {
      console.warn("Failed to save preset", e);
    } finally {
      setIsSavingPreset(false);
    }
  };

  // プリセット削除
  const handleDeletePreset = async (maskId: string) => {
    // maskId format: "preset:uuid"
    const uuid = maskId.replace("preset:", "");
    try {
      const res = await fetch(`${API_BASE}/game/masks/preset/${uuid}`, {
        method: "DELETE",
      });
      if (res.ok) {
        const data: MaskListResponse = await res.json();
        setMaskList(data);
        if (selectedMaskId === maskId) {
          setSelectedMaskId(null);
          setMaskPresetUrl(null);
        }
      }
    } catch (e) {
      console.warn("Failed to delete preset", e);
    } finally {
      setDeleteConfirmMaskId(null);
    }
  };

  // オーバーレイクリック
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // 設定更新ヘルパー
  const updateSetting = <K extends keyof InpaintSettings>(
    key: K,
    value: InpaintSettings[K],
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (!isOpen) return null;

  return (
    <div className="inpaint-modal-overlay" onClick={handleOverlayClick}>
      <div className="inpaint-modal" onClick={(e) => e.stopPropagation()}>
        {/* ヘッダー */}
        <div className="inpaint-modal-header">
          <h3>{t("inpaint.title")}</h3>
          <button
            type="button"
            className="inpaint-modal-close"
            onClick={handleCancel}
            aria-label={t("common.close")}
          >
            ×
          </button>
        </div>

        {/* ボディ: 2カラムレイアウト */}
        <div className="inpaint-modal-body">
          {/* 左カラム: キャンバス */}
          <div className="inpaint-canvas-column">
            {/* ツールバー */}
            <div className="inpaint-toolbar">
              <button
                type="button"
                className={`inpaint-tool-btn ${!settings.eraserMode ? "active" : ""}`}
                onClick={() => {
                  updateSetting("eraserMode", false);
                  maskCanvasRef.current?.eraseMode(false);
                }}
              >
                {t("inpaint.brush")}
              </button>
              <button
                type="button"
                className={`inpaint-tool-btn ${settings.eraserMode ? "active" : ""}`}
                onClick={() => {
                  updateSetting("eraserMode", true);
                  maskCanvasRef.current?.eraseMode(true);
                }}
              >
                {t("inpaint.eraser")}
              </button>
              <button
                type="button"
                className="inpaint-tool-btn"
                onClick={() => maskCanvasRef.current?.undo()}
                title={t("inpaint.undoTitle")}
              >
                {t("inpaint.undo")}
              </button>
              <button
                type="button"
                className="inpaint-tool-btn"
                onClick={() => maskCanvasRef.current?.redo()}
                title={t("inpaint.redoTitle")}
              >
                {t("inpaint.redo")}
              </button>
              <button
                type="button"
                className="inpaint-tool-btn"
                onClick={handleClearMask}
              >
                {t("inpaint.clear")}
              </button>
            </div>

            {/* キャンバスラッパー */}
            <div
              className="inpaint-canvas-wrapper"
              style={{ width: canvasSize.width, height: canvasSize.height }}
            >
              {/* 背景画像 */}
              {currentImageUrl && (
                <img
                  src={currentImageUrl}
                  alt="Base"
                  style={{ width: canvasSize.width, height: canvasSize.height }}
                  crossOrigin="anonymous"
                />
              )}
              {/* プリセットマスク */}
              {maskPresetUrl && (
                <img
                  src={maskPresetUrl}
                  alt="Preset mask"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: canvasSize.width,
                    height: canvasSize.height,
                    opacity: 0.5,
                    pointerEvents: "none",
                  }}
                />
              )}
              {/* 描画キャンバス */}
              <div
                className="inpaint-canvas-overlay"
                style={{ width: canvasSize.width, height: canvasSize.height }}
              >
                <ReactSketchCanvas
                  ref={maskCanvasRef}
                  width={`${canvasSize.width}px`}
                  height={`${canvasSize.height}px`}
                  strokeWidth={settings.brushSize}
                  strokeColor="rgba(255,0,0,0.6)"
                  canvasColor="transparent"
                  style={{ background: "transparent" }}
                  eraserWidth={settings.brushSize}
                />
              </div>
            </div>
          </div>

          {/* 右カラム: 設定パネル */}
          <div className="inpaint-settings-column">
            {/* ブラシサイズ */}
            <div className="inpaint-section">
              <div className="inpaint-section-title">
                {t("inpaint.brushSection")}
              </div>
              <div className="inpaint-slider-group">
                <div className="inpaint-slider-label">
                  <span>{t("inpaint.brushSize")}</span>
                  <span className="inpaint-slider-value">
                    {settings.brushSize}
                  </span>
                </div>
                <input
                  type="range"
                  className="inpaint-slider"
                  min={4}
                  max={96}
                  value={settings.brushSize}
                  onChange={(e) =>
                    updateSetting("brushSize", Number(e.target.value))
                  }
                />
              </div>
            </div>

            {/* パラメータ設定 */}
            <div className="inpaint-section">
              <div className="inpaint-section-title">
                {t("inpaint.paramsSection")}
              </div>

              <div className="inpaint-slider-group">
                <div className="inpaint-slider-label">
                  <span>{t("inpaint.maskStrength")}</span>
                  <span className="inpaint-slider-value">
                    {settings.maskStrength.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  className="inpaint-slider"
                  min={0.05}
                  max={1.0}
                  step={0.01}
                  value={settings.maskStrength}
                  onChange={(e) =>
                    updateSetting("maskStrength", Number(e.target.value))
                  }
                />
              </div>

              <div className="inpaint-slider-group">
                <div className="inpaint-slider-label">
                  <span>{t("inpaint.i2iStrength")}</span>
                  <span className="inpaint-slider-value">
                    {settings.i2iStrength.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  className="inpaint-slider"
                  min={0.05}
                  max={0.99}
                  step={0.01}
                  value={settings.i2iStrength}
                  onChange={(e) =>
                    updateSetting("i2iStrength", Number(e.target.value))
                  }
                />
              </div>

              <div className="inpaint-slider-group">
                <div className="inpaint-slider-label">
                  <span>{t("inpaint.noise")}</span>
                  <span className="inpaint-slider-value">
                    {settings.inpaintNoise.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  className="inpaint-slider"
                  min={0}
                  max={0.5}
                  step={0.01}
                  value={settings.inpaintNoise}
                  onChange={(e) =>
                    updateSetting("inpaintNoise", Number(e.target.value))
                  }
                />
              </div>

              <div className="inpaint-checkbox-group">
                <input
                  type="checkbox"
                  id="invertMask"
                  checked={settings.invertMask}
                  onChange={(e) =>
                    updateSetting("invertMask", e.target.checked)
                  }
                />
                <label htmlFor="invertMask">{t("inpaint.invertMask")}</label>
              </div>
            </div>

            {/* システムマスク */}
            <div className="inpaint-section">
              <div className="inpaint-section-title">
                {t("inpaint.systemMasks")}
              </div>
              {maskList.system.length > 0 ? (
                <div className="inpaint-mask-list">
                  {maskList.system.map((mask) => (
                    <div
                      key={mask.id}
                      className={`inpaint-mask-item ${selectedMaskId === mask.id ? "selected" : ""}`}
                      onClick={() => handleSelectMask(mask)}
                    >
                      <img
                        src={mask.url}
                        alt={mask.name}
                        crossOrigin="anonymous"
                      />
                      <div className="inpaint-mask-item-name">{mask.name}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="inpaint-empty-message">
                  {t("inpaint.noSystemMasks")}
                </div>
              )}
            </div>

            {/* 履歴マスク */}
            <div className="inpaint-section">
              <div className="inpaint-section-title">
                {t("inpaint.historyMasks")}
              </div>
              {maskList.history.length > 0 ? (
                <div className="inpaint-mask-list">
                  {maskList.history.map((mask) => (
                    <div
                      key={mask.id}
                      className={`inpaint-mask-item ${selectedMaskId === mask.id ? "selected" : ""}`}
                      onClick={() => handleSelectMask(mask)}
                    >
                      <img
                        src={mask.url}
                        alt={mask.name}
                        crossOrigin="anonymous"
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="inpaint-empty-message">
                  {t("inpaint.noHistoryMasks")}
                </div>
              )}
            </div>

            {/* プリセットマスク */}
            <div className="inpaint-section">
              <div className="inpaint-section-title">
                <span>{t("inpaint.presetMasks")}</span>
                <button
                  type="button"
                  className="inpaint-preset-save-btn"
                  onClick={() => setShowPresetSaveDialog(true)}
                  title={t("inpaint.saveCurrentPresetTitle")}
                >
                  {t("inpaint.savePresetButton")}
                </button>
              </div>
              {maskList.presets.length > 0 ? (
                <div className="inpaint-mask-list">
                  {maskList.presets.map((mask) => (
                    <div
                      key={mask.id}
                      className={`inpaint-mask-item ${selectedMaskId === mask.id ? "selected" : ""}`}
                      onClick={() => handleSelectMask(mask)}
                    >
                      <img
                        src={mask.url}
                        alt={mask.name}
                        crossOrigin="anonymous"
                      />
                      <div className="inpaint-mask-item-name">{mask.name}</div>
                      <button
                        type="button"
                        className="inpaint-mask-item-delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteConfirmMaskId(mask.id);
                        }}
                        title={t("inpaint.deletePresetTitle")}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="inpaint-empty-message">
                  {t("inpaint.noPresets")}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* フッター */}
        <div className="inpaint-modal-footer">
          <button
            type="button"
            className="inpaint-btn inpaint-btn-cancel"
            onClick={handleCancel}
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="inpaint-btn inpaint-btn-apply"
            onClick={handleApply}
            disabled={maskLoading}
          >
            {t("inpaint.apply")}
          </button>
        </div>
      </div>

      {/* プリセット保存ダイアログ */}
      {showPresetSaveDialog && (
        <div
          className="inpaint-dialog-overlay"
          onClick={() => setShowPresetSaveDialog(false)}
        >
          <div className="inpaint-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="inpaint-dialog-title">
              {t("inpaint.saveAsPreset")}
            </div>
            <input
              type="text"
              className="inpaint-dialog-input"
              placeholder={t("inpaint.presetNamePlaceholder")}
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              maxLength={50}
              autoFocus
            />
            <div className="inpaint-dialog-buttons">
              <button
                type="button"
                className="inpaint-btn inpaint-btn-cancel"
                onClick={() => {
                  setShowPresetSaveDialog(false);
                  setPresetName("");
                }}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="inpaint-btn inpaint-btn-apply"
                onClick={handleSavePreset}
                disabled={isSavingPreset || !presetName.trim()}
              >
                {isSavingPreset ? t("inpaint.saving") : t("inpaint.save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 削除確認ダイアログ */}
      {deleteConfirmMaskId && (
        <div
          className="inpaint-dialog-overlay"
          onClick={() => setDeleteConfirmMaskId(null)}
        >
          <div className="inpaint-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="inpaint-dialog-title">
              {t("inpaint.deletePresetHeading")}
            </div>
            <div className="inpaint-dialog-message">
              {t("inpaint.deletePresetConfirm")}
            </div>
            <div className="inpaint-dialog-buttons">
              <button
                type="button"
                className="inpaint-btn inpaint-btn-cancel"
                onClick={() => setDeleteConfirmMaskId(null)}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="inpaint-btn inpaint-btn-danger"
                onClick={() => handleDeletePreset(deleteConfirmMaskId)}
              >
                {t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
