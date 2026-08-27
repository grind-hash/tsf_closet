/**
 * PromptExpanderInpaintModal - インペイント用のマスク編集モーダル
 *
 * i2i 元の画像の上にブラシでマスクを描き、塗った領域だけを描き直させる。
 * マスクのプリセットは通常ゲームと同じ /api/game/masks を共用する
 * （顔だけの形などは一度描いて保存すれば以後 1 クリックで呼べる）。
 *
 * 書き出しサイズは NovelAI のマスク解像度に合わせてベース画像の 1/8 で求める。
 * 固定値にすると landscape / square でマスクの縦横比が崩れる。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type CanvasPath,
  ReactSketchCanvas,
  type ReactSketchCanvasRef,
} from "react-sketch-canvas";
import {
  DEFAULT_PROMPT_EXPANDER_BRUSH_SIZE,
  PROMPT_EXPANDER_BRUSH_SIZE_MAX,
  PROMPT_EXPANDER_BRUSH_SIZE_MIN,
  PROMPT_EXPANDER_MASK_GRID_DIVISOR,
} from "../../constants/promptExpander";
import type { MaskInfo, MaskListResponse } from "../../types";
import { API_BASE } from "../../utils/api";
import PromptExpanderDeleteButton from "./PromptExpanderDeleteButton";
import PromptExpanderModal from "./PromptExpanderModal";
import "./PromptExpanderShared.css";
import "./PromptExpanderInpaintModal.css";

/**
 * キャンバス置き場（ステージ）の実寸が測れるまでの仮サイズ。
 * 実際の表示サイズはステージの大きさに合わせて決め直す。
 */
const FALLBACK_STAGE_SIZE = { width: 520, height: 460 };

const EMPTY_MASKS: MaskListResponse = { system: [], history: [], presets: [] };

interface PromptExpanderInpaintModalProps {
  open: boolean;
  onClose: () => void;
  /** マスクを描く元画像。null のときはモーダルを開かない想定 */
  baseImageUrl: string | null;
  /** 既に設定済みのマスク（開いたときに下敷きとして表示する） */
  initialMaskUrl?: string | null;
  onApply: (maskDataUrl: string, label: string) => void;
}

export default function PromptExpanderInpaintModal({
  open,
  onClose,
  baseImageUrl,
  initialMaskUrl = null,
  onApply,
}: PromptExpanderInpaintModalProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<ReactSketchCanvasRef>(null);

  const [brushSize, setBrushSize] = useState(
    DEFAULT_PROMPT_EXPANDER_BRUSH_SIZE,
  );
  const [eraser, setEraser] = useState(false);
  const [baseMaskUrl, setBaseMaskUrl] = useState<string | null>(null);
  const [selectedMaskId, setSelectedMaskId] = useState<string | null>(null);
  const [masks, setMasks] = useState<MaskListResponse>(EMPTY_MASKS);
  const [busy, setBusy] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [savingPreset, setSavingPreset] = useState(false);
  const [emptyWarning, setEmptyWarning] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState(FALLBACK_STAGE_SIZE);
  const [baseSize, setBaseSize] = useState({ width: 832, height: 1216 });

  // 元画像の縦横比を保ったままステージいっぱいに収める表示サイズ
  const canvasSize = useMemo(() => {
    const ratio = Math.min(
      stageSize.width / baseSize.width,
      stageSize.height / baseSize.height,
    );
    return {
      width: Math.max(1, Math.floor(baseSize.width * ratio)),
      height: Math.max(1, Math.floor(baseSize.height * ratio)),
    };
  }, [stageSize, baseSize]);

  const loadMasks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/game/masks`);
      if (res.ok) setMasks((await res.json()) as MaskListResponse);
    } catch {
      // 一覧が取れなくてもブラシでの描画は続けられる
    }
  }, []);

  // 開くたびに状態を初期化する（前回のストロークを持ち越さない）
  useEffect(() => {
    if (!open) return;
    setEraser(false);
    setSelectedMaskId(null);
    setPresetName("");
    setEmptyWarning(false);
    setBaseMaskUrl(initialMaskUrl);
    canvasRef.current?.resetCanvas();
    void loadMasks();
  }, [open, initialMaskUrl, loadMasks]);

  // 元画像の実寸（マスクの書き出し解像度と表示の縦横比の基準になる）
  useEffect(() => {
    if (!open || !baseImageUrl) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      setBaseSize({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.src = baseImageUrl;
  }, [open, baseImageUrl]);

  // ステージの実寸を追いかける（モーダルは画面サイズに追従するため固定値にしない）
  useEffect(() => {
    if (!open) return;
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === "undefined") return;
    const update = () => {
      const rect = stage.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      setStageSize((prev) => {
        const next = {
          width: Math.floor(rect.width),
          height: Math.floor(rect.height),
        };
        return prev.width === next.width && prev.height === next.height
          ? prev
          : next;
      });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [open]);

  // 表示サイズが変わったら、描き済みのストロークも同じ比率で置き直す
  // （ReactSketchCanvas の座標は表示ピクセルなので、そのままだと画像とずれる）
  const prevCanvasSizeRef = useRef(canvasSize);
  useEffect(() => {
    const prev = prevCanvasSizeRef.current;
    prevCanvasSizeRef.current = canvasSize;
    if (prev.width === canvasSize.width && prev.height === canvasSize.height) {
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) return;
    const scaleX = canvasSize.width / prev.width;
    const scaleY = canvasSize.height / prev.height;
    void canvas.exportPaths().then((paths: CanvasPath[]) => {
      if (paths.length === 0) return;
      canvas.resetCanvas();
      canvas.loadPaths(
        paths.map((path) => ({
          ...path,
          strokeWidth: path.strokeWidth * scaleX,
          paths: path.paths.map((pt) => ({
            x: pt.x * scaleX,
            y: pt.y * scaleY,
          })),
        })),
      );
    });
  }, [canvasSize]);

  const selectMask = useCallback(async (mask: MaskInfo) => {
    setBusy(true);
    try {
      const res = await fetch(mask.url);
      if (!res.ok) return;
      const blob = await res.blob();
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      });
      setBaseMaskUrl(dataUrl);
      setSelectedMaskId(mask.id);
      // プリセットが下敷きになるので、手描きのストロークは畳む
      canvasRef.current?.resetCanvas();
    } catch {
      // 読み込めなかったプリセットは無視する
    } finally {
      setBusy(false);
    }
  }, []);

  /** 下敷き（プリセット）と手描きを合成し、白 + アルファのマスク PNG を返す */
  const mergeMask = useCallback(async (): Promise<string | null> => {
    const work = document.createElement("canvas");
    work.width = baseSize.width;
    work.height = baseSize.height;
    const workCtx = work.getContext("2d");
    if (!workCtx) return null;
    workCtx.clearRect(0, 0, work.width, work.height);

    if (baseMaskUrl) {
      const preset = new Image();
      preset.src = baseMaskUrl;
      await preset.decode().catch(() => undefined);
      workCtx.drawImage(preset, 0, 0, work.width, work.height);
    }
    const strokes = await canvasRef.current?.exportImage("png");
    if (strokes) {
      const strokeImg = new Image();
      strokeImg.src = strokes;
      await strokeImg.decode().catch(() => undefined);
      workCtx.drawImage(strokeImg, 0, 0, work.width, work.height);
    }

    // NovelAI のマスク解像度（ベースの 1/8）へ落として送る
    const saveWidth = Math.max(
      1,
      Math.round(baseSize.width / PROMPT_EXPANDER_MASK_GRID_DIVISOR),
    );
    const saveHeight = Math.max(
      1,
      Math.round(baseSize.height / PROMPT_EXPANDER_MASK_GRID_DIVISOR),
    );
    const out = document.createElement("canvas");
    out.width = saveWidth;
    out.height = saveHeight;
    const outCtx = out.getContext("2d");
    if (!outCtx) return null;
    outCtx.clearRect(0, 0, saveWidth, saveHeight);
    outCtx.drawImage(work, 0, 0, saveWidth, saveHeight);

    // 塗った画素を白にし、アルファは元の値のまま残す（サーバー側で二値化する）
    const imageData = outCtx.getImageData(0, 0, saveWidth, saveHeight);
    const data = imageData.data;
    let painted = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] > 0) {
        data[i] = 255;
        data[i + 1] = 255;
        data[i + 2] = 255;
        painted += 1;
      }
    }
    if (painted === 0) return null;
    outCtx.putImageData(imageData, 0, 0);
    return out.toDataURL("image/png");
  }, [baseMaskUrl, baseSize]);

  const handleApply = useCallback(async () => {
    setBusy(true);
    try {
      const merged = await mergeMask();
      if (!merged) {
        setEmptyWarning(true);
        return;
      }
      setEmptyWarning(false);
      const label =
        masks.system.find((m) => m.id === selectedMaskId)?.name ??
        masks.presets.find((m) => m.id === selectedMaskId)?.name ??
        t("promptExpander.inpaint.maskDrawn");
      onApply(merged, label);
      onClose();
    } finally {
      setBusy(false);
    }
  }, [mergeMask, masks, selectedMaskId, onApply, onClose, t]);

  const handleClear = useCallback(() => {
    canvasRef.current?.resetCanvas();
    setBaseMaskUrl(null);
    setSelectedMaskId(null);
    setEmptyWarning(false);
  }, []);

  const handleSavePreset = useCallback(async () => {
    const name = presetName.trim();
    if (!name) return;
    setSavingPreset(true);
    try {
      const merged = await mergeMask();
      if (!merged) {
        setEmptyWarning(true);
        return;
      }
      const res = await fetch(`${API_BASE}/game/masks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mask_base64: merged, name }),
      });
      if (res.ok) {
        setMasks((await res.json()) as MaskListResponse);
        setPresetName("");
      }
    } catch {
      // 保存に失敗しても編集は続けられる
    } finally {
      setSavingPreset(false);
    }
  }, [presetName, mergeMask]);

  const handleDeletePreset = useCallback(
    async (maskId: string) => {
      try {
        const res = await fetch(
          `${API_BASE}/game/masks/preset/${maskId.replace("preset:", "")}`,
          { method: "DELETE" },
        );
        if (res.ok) {
          setMasks((await res.json()) as MaskListResponse);
          if (selectedMaskId === maskId) {
            setSelectedMaskId(null);
            setBaseMaskUrl(null);
          }
        }
      } catch {
        // 削除に失敗しても一覧はそのまま
      }
    },
    [selectedMaskId],
  );

  const renderMaskList = (items: MaskInfo[], deletable: boolean) =>
    items.length > 0 ? (
      <ul className="prompt-expander__mask-list">
        {items.map((mask) => (
          <li key={mask.id} className="prompt-expander__mask-item">
            <button
              type="button"
              className={`prompt-expander__mask-btn ${
                selectedMaskId === mask.id ? "is-active" : ""
              }`}
              onClick={() => void selectMask(mask)}
              title={mask.name}
            >
              <img src={mask.url} alt="" crossOrigin="anonymous" />
              <span className="prompt-expander__mask-name">{mask.name}</span>
            </button>
            {deletable && (
              <PromptExpanderDeleteButton
                label={t("promptExpander.inpaint.deletePreset")}
                onClick={() => void handleDeletePreset(mask.id)}
                className="prompt-expander__mask-delete"
              />
            )}
          </li>
        ))}
      </ul>
    ) : (
      <p className="prompt-expander__hint">
        {t("promptExpander.inpaint.noMasks")}
      </p>
    );

  return (
    <PromptExpanderModal
      open={open}
      title={t("promptExpander.inpaint.modalTitle")}
      onClose={onClose}
      closeLabel={t("common.close")}
      size="xl"
      className="prompt-expander__inpaint-modal"
      footer={
        <>
          <button
            type="button"
            className="prompt-expander__btn"
            onClick={onClose}
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--primary"
            onClick={() => void handleApply()}
            disabled={busy}
          >
            {t("promptExpander.inpaint.applyMask")}
          </button>
        </>
      }
    >
      <div className="prompt-expander__inpaint">
        <div className="prompt-expander__inpaint-canvas-col">
          <div
            className="prompt-expander__inpaint-toolbar"
            role="toolbar"
            aria-label={t("promptExpander.inpaint.toolbarLabel")}
          >
            <button
              type="button"
              className={`prompt-expander__btn prompt-expander__btn--sm ${
                eraser ? "" : "prompt-expander__btn--primary"
              }`}
              onClick={() => {
                setEraser(false);
                canvasRef.current?.eraseMode(false);
              }}
            >
              {t("promptExpander.inpaint.brush")}
            </button>
            <button
              type="button"
              className={`prompt-expander__btn prompt-expander__btn--sm ${
                eraser ? "prompt-expander__btn--primary" : ""
              }`}
              onClick={() => {
                setEraser(true);
                canvasRef.current?.eraseMode(true);
              }}
            >
              {t("promptExpander.inpaint.eraser")}
            </button>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={() => canvasRef.current?.undo()}
            >
              {t("promptExpander.inpaint.undo")}
            </button>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={() => canvasRef.current?.redo()}
            >
              {t("promptExpander.inpaint.redo")}
            </button>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={handleClear}
            >
              {t("promptExpander.inpaint.clear")}
            </button>
            <div className="prompt-expander__inpaint-brush">
              <label
                className="prompt-expander__label"
                htmlFor="prompt-expander-brush-size"
              >
                {t("promptExpander.inpaint.brushSize")}: {brushSize}
              </label>
              <input
                id="prompt-expander-brush-size"
                type="range"
                className="prompt-expander__range"
                min={PROMPT_EXPANDER_BRUSH_SIZE_MIN}
                max={PROMPT_EXPANDER_BRUSH_SIZE_MAX}
                value={brushSize}
                onChange={(e) => setBrushSize(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="prompt-expander__inpaint-stage" ref={stageRef}>
            <div
              className="prompt-expander__inpaint-canvas"
              style={{ width: canvasSize.width, height: canvasSize.height }}
            >
              {baseImageUrl && (
                <img
                  className="prompt-expander__inpaint-base"
                  src={baseImageUrl}
                  alt=""
                  style={{ width: canvasSize.width, height: canvasSize.height }}
                  crossOrigin="anonymous"
                />
              )}
              {baseMaskUrl && (
                <img
                  className="prompt-expander__inpaint-preset"
                  src={baseMaskUrl}
                  alt=""
                  style={{ width: canvasSize.width, height: canvasSize.height }}
                />
              )}
              <div
                className="prompt-expander__inpaint-overlay"
                style={{ width: canvasSize.width, height: canvasSize.height }}
              >
                <ReactSketchCanvas
                  ref={canvasRef}
                  width={`${canvasSize.width}px`}
                  height={`${canvasSize.height}px`}
                  strokeWidth={brushSize}
                  eraserWidth={brushSize}
                  strokeColor="rgba(233, 69, 96, 0.55)"
                  canvasColor="transparent"
                  style={{ background: "transparent", border: "none" }}
                />
              </div>
            </div>
          </div>

          {emptyWarning && (
            <p
              className="prompt-expander__hint prompt-expander__hint--warning"
              role="alert"
            >
              {t("promptExpander.inpaint.emptyMask")}
            </p>
          )}
        </div>

        <div className="prompt-expander__inpaint-side">
          <p className="prompt-expander__hint">
            {t("promptExpander.inpaint.modalHint")}
          </p>
          <h3 className="prompt-expander__label">
            {t("promptExpander.inpaint.systemMasks")}
          </h3>
          {renderMaskList(masks.system, false)}
          <h3 className="prompt-expander__label">
            {t("promptExpander.inpaint.presetMasks")}
          </h3>
          {renderMaskList(masks.presets, true)}
          <div className="prompt-expander__inpaint-save">
            <input
              type="text"
              className="prompt-expander__input"
              value={presetName}
              maxLength={50}
              placeholder={t("promptExpander.inpaint.presetNamePlaceholder")}
              onChange={(e) => setPresetName(e.target.value)}
            />
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={() => void handleSavePreset()}
              disabled={savingPreset || !presetName.trim()}
            >
              {t("promptExpander.inpaint.savePreset")}
            </button>
          </div>
          <p className="prompt-expander__hint">
            {t("promptExpander.inpaint.presetSharedHint")}
          </p>
        </div>
      </div>
    </PromptExpanderModal>
  );
}
