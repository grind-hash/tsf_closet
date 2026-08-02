/**
 * ComparisonSliderModal - 変身前後のワイプ比較スライダー
 * spec 010: 起点画像(先頭フレーム)と選択ターンをワイプで比較し、
 * ターンスライダー・サムネイルストリップ・自動再生で経過を辿る
 */

import type { PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchSessionFrames } from "../../apis/gallery";
import { generateStandingPortrait } from "../../apis/game";
import { useSettings } from "../../contexts/SettingsContext";
import type { GalleryItem } from "../../types";
import { API_BASE } from "../../utils/api";
import "./ComparisonSliderModal.css";

type BasisMode = "origin" | "prev";

interface ComparisonSliderModalProps {
  isOpen: boolean;
  sessionId: string | null;
  onClose: () => void;
}

const PLAY_INTERVAL_MS = 1600;

export default function ComparisonSliderModal({
  isOpen,
  sessionId,
  onClose,
}: ComparisonSliderModalProps) {
  const { t, i18n } = useTranslation();
  const { state } = useSettings();

  const [frames, setFrames] = useState<GalleryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedTurnIndex, setSelectedTurnIndex] = useState(0);
  const [basisMode, setBasisMode] = useState<BasisMode>("origin");
  const [wipePosition, setWipePosition] = useState(50);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // 立ち絵再生成（履歴には保存しないおまけ機能）
  const [portraitImage, setPortraitImage] = useState<string | null>(null);
  const [isPortraitLoading, setIsPortraitLoading] = useState(false);
  const [portraitError, setPortraitError] = useState<string | null>(null);
  const [usePortraitAsAfter, setUsePortraitAsAfter] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);

  // モーダルを開くたびに全フレームを取得
  useEffect(() => {
    if (!isOpen || !sessionId) return;
    setError(null);
    setIsLoading(true);
    setSelectedTurnIndex(0);
    setBasisMode("origin");
    setWipePosition(50);
    setIsPlaying(false);
    setPortraitImage(null);
    setPortraitError(null);
    setIsPortraitLoading(false);
    setUsePortraitAsAfter(false);
    let cancelled = false;
    fetchSessionFrames(sessionId)
      .then((data) => {
        if (cancelled) return;
        setFrames(data);
        setSelectedTurnIndex(Math.max(0, data.length - 2));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : t("gallery.comparison.fetchError"),
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, sessionId, t]);

  const origin = frames[0] ?? null;
  const turnFrames = useMemo(() => frames.slice(1), [frames]);
  const selectedFrame = turnFrames[selectedTurnIndex] ?? null;
  const prevFrame =
    selectedTurnIndex > 0 ? turnFrames[selectedTurnIndex - 1] : origin;
  const beforeFrame = basisMode === "origin" ? origin : prevFrame;
  const isPortraitAfterActive = usePortraitAsAfter && !!portraitImage;

  const beforeUrl = beforeFrame ? `${API_BASE}${beforeFrame.image_url}` : "";
  const afterUrl = isPortraitAfterActive
    ? portraitImage
    : selectedFrame
      ? `${API_BASE}${selectedFrame.image_url}`
      : "";

  // ESCキーで閉じる + 背景スクロール抑止
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, onClose]);

  // 自動再生: ターンを一定間隔で進めつつワイプを起点(0)から反復させる
  useEffect(() => {
    if (!isPlaying || turnFrames.length === 0) return;
    setWipePosition(0);
    const id = window.setInterval(() => {
      setSelectedTurnIndex((idx) => {
        if (idx >= turnFrames.length - 1) {
          setIsPlaying(false);
          return idx;
        }
        return idx + 1;
      });
    }, PLAY_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [isPlaying, turnFrames.length]);

  // selectedTurnIndex はワイプ再生をターン切替のたびに再トリガーするために必要
  // biome-ignore lint/correctness/useExhaustiveDependencies: 上記コメント参照
  useEffect(() => {
    if (!isPlaying) return;
    setWipePosition(0);
    const raf = window.requestAnimationFrame(() => setWipePosition(100));
    return () => window.cancelAnimationFrame(raf);
  }, [isPlaying, selectedTurnIndex]);

  const updatePositionFromClientX = useCallback((clientX: number) => {
    const el = stageRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = (clientX - rect.left) / rect.width;
    setWipePosition(Math.min(100, Math.max(0, ratio * 100)));
  }, []);

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    setIsPlaying(false);
    setIsDragging(true);
    updatePositionFromClientX(e.clientX);
  };

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (e: PointerEvent) =>
      updatePositionFromClientX(e.clientX);
    const handleUp = () => setIsDragging(false);
    document.addEventListener("pointermove", handleMove);
    document.addEventListener("pointerup", handleUp);
    return () => {
      document.removeEventListener("pointermove", handleMove);
      document.removeEventListener("pointerup", handleUp);
    };
  }, [isDragging, updatePositionFromClientX]);

  const handleHandleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") {
      setWipePosition((p) => Math.max(0, p - 5));
    } else if (e.key === "ArrowRight") {
      setWipePosition((p) => Math.min(100, p + 5));
    }
  };

  const formatDate = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleDateString(
        i18n.language === "en" ? "en-US" : "ja-JP",
        { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" },
      );
    } catch {
      return timestamp;
    }
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  const handleGeneratePortrait = useCallback(async () => {
    if (!sessionId || isPortraitLoading) return;
    setIsPortraitLoading(true);
    setPortraitError(null);
    try {
      const result = await generateStandingPortrait(sessionId, state.nsfwMode);
      setPortraitImage(`data:image/png;base64,${result.image}`);
      setUsePortraitAsAfter(true);
    } catch (err) {
      setPortraitError(
        err instanceof Error
          ? err.message
          : t("gallery.comparison.portraitError"),
      );
    } finally {
      setIsPortraitLoading(false);
    }
  }, [sessionId, isPortraitLoading, state.nsfwMode, t]);

  if (!isOpen) return null;

  return (
    <div
      className="comparison-slider-modal__overlay"
      onClick={handleOverlayClick}
      onKeyDown={() => {}}
      role="dialog"
      aria-modal="true"
      aria-label={t("gallery.comparison.dialogAria")}
    >
      <div className="comparison-slider-modal__content">
        <button
          type="button"
          className="comparison-slider-modal__close"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          ✕
        </button>

        {isLoading && (
          <p className="comparison-slider-modal__status">
            {t("gallery.comparison.loading")}
          </p>
        )}
        {error && !isLoading && (
          <p className="comparison-slider-modal__status">{error}</p>
        )}
        {!isLoading && !error && turnFrames.length === 0 && (
          <p className="comparison-slider-modal__status">
            {t("gallery.comparison.notEnoughFrames")}
          </p>
        )}

        {!isLoading && !error && origin && selectedFrame && (
          <>
            <div
              ref={stageRef}
              className="comparison-slider-modal__stage"
              onPointerDown={handlePointerDown}
            >
              <img
                src={beforeUrl}
                alt=""
                className="comparison-slider-modal__image comparison-slider-modal__image--before"
              />
              <div
                className="comparison-slider-modal__after-wrap"
                style={{ clipPath: `inset(0 0 0 ${wipePosition}%)` }}
              >
                <img
                  src={afterUrl}
                  alt=""
                  className="comparison-slider-modal__image comparison-slider-modal__image--after"
                />
              </div>
              <span className="comparison-slider-modal__label comparison-slider-modal__label--before">
                {t("gallery.comparison.beforeLabel")}
              </span>
              <span className="comparison-slider-modal__label comparison-slider-modal__label--after">
                {isPortraitAfterActive
                  ? t("gallery.comparison.portraitAfterLabel")
                  : t("gallery.comparison.afterLabel")}
              </span>
              <div
                className="comparison-slider-modal__handle"
                style={{ left: `${wipePosition}%` }}
                role="slider"
                tabIndex={0}
                aria-valuenow={Math.round(wipePosition)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={t("gallery.comparison.handleAria")}
                onPointerDown={handlePointerDown}
                onKeyDown={handleHandleKeyDown}
              >
                <span
                  className="comparison-slider-modal__handle-grip"
                  aria-hidden="true"
                />
              </div>
            </div>

            <div className="comparison-slider-modal__controls">
              <div className="comparison-slider-modal__basis-toggle">
                <button
                  type="button"
                  className={`comparison-slider-modal__basis-btn${basisMode === "origin" ? " is-active" : ""}`}
                  onClick={() => setBasisMode("origin")}
                >
                  {t("gallery.comparison.basisOrigin")}
                </button>
                <button
                  type="button"
                  className={`comparison-slider-modal__basis-btn${basisMode === "prev" ? " is-active" : ""}`}
                  onClick={() => setBasisMode("prev")}
                  disabled={selectedTurnIndex === 0}
                >
                  {t("gallery.comparison.basisPrev")}
                </button>
              </div>

              <div className="comparison-slider-modal__turn-row">
                <button
                  type="button"
                  className="comparison-slider-modal__play-btn"
                  onClick={() => setIsPlaying((p) => !p)}
                >
                  {isPlaying
                    ? `⏸ ${t("gallery.comparison.pause")}`
                    : `▶ ${t("gallery.comparison.play")}`}
                </button>
                <input
                  type="range"
                  className="comparison-slider-modal__turn-slider"
                  min={0}
                  max={Math.max(0, turnFrames.length - 1)}
                  value={selectedTurnIndex}
                  aria-label={t("gallery.comparison.turnSliderAria")}
                  onChange={(e) => {
                    setIsPlaying(false);
                    setSelectedTurnIndex(Number(e.target.value));
                  }}
                />
                <span className="comparison-slider-modal__turn-label">
                  {t("gallery.comparison.turnLabel", {
                    current: selectedTurnIndex + 1,
                    total: turnFrames.length,
                  })}
                </span>
              </div>

              <div className="comparison-slider-modal__strip">
                <div className="comparison-slider-modal__strip-item is-origin">
                  <img src={`${API_BASE}${origin.image_url}`} alt="" />
                  <span>{t("gallery.comparison.originLabel")}</span>
                </div>
                {turnFrames.map((frame, idx) => (
                  <button
                    type="button"
                    key={frame.id}
                    className={`comparison-slider-modal__strip-item${idx === selectedTurnIndex ? " is-active" : ""}`}
                    onClick={() => {
                      setIsPlaying(false);
                      setSelectedTurnIndex(idx);
                    }}
                  >
                    <img src={`${API_BASE}${frame.image_url}`} alt="" />
                    <span>{idx + 1}</span>
                  </button>
                ))}
              </div>

              <div className="comparison-slider-modal__meta">
                <p className="comparison-slider-modal__meta-instruction">
                  {isPortraitAfterActive
                    ? t("gallery.comparison.portraitAfterMeta")
                    : selectedFrame.instruction || t("gallery.noInstruction")}
                </p>
                {!isPortraitAfterActive && (
                  <span className="comparison-slider-modal__meta-date">
                    {formatDate(selectedFrame.timestamp)}
                  </span>
                )}
              </div>

              <div className="comparison-slider-modal__portrait">
                <button
                  type="button"
                  className="comparison-slider-modal__portrait-btn"
                  onClick={handleGeneratePortrait}
                  disabled={isPortraitLoading}
                >
                  {isPortraitLoading
                    ? t("gallery.comparison.portraitGenerating")
                    : t("gallery.comparison.portraitButton")}
                </button>
                <p className="comparison-slider-modal__portrait-hint">
                  {t("gallery.comparison.portraitHint")}
                </p>
                {portraitError && (
                  <p className="comparison-slider-modal__portrait-error">
                    {portraitError}
                  </p>
                )}
                {portraitImage && (
                  <div className="comparison-slider-modal__portrait-result">
                    <button
                      type="button"
                      className="comparison-slider-modal__portrait-toggle"
                      onClick={() => setUsePortraitAsAfter((v) => !v)}
                    >
                      {usePortraitAsAfter
                        ? t("gallery.comparison.portraitDisableInSlider")
                        : t("gallery.comparison.portraitEnableInSlider")}
                    </button>
                    <a
                      className="comparison-slider-modal__portrait-download"
                      href={portraitImage}
                      download={`standing-portrait-${sessionId ?? "session"}.png`}
                    >
                      {t("gallery.comparison.portraitDownload")}
                    </a>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
