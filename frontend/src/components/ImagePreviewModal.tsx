/**
 * ImagePreviewModal - 画像拡大プレビューモーダル
 * T027-T032: キャラクター画像クリックで拡大表示
 */

import type { ReactNode } from "react";
import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import "./ImagePreviewModal.css";

interface ImagePreviewModalProps {
  isOpen: boolean;
  imageUrl: string | null;
  onClose: () => void;
  alt?: string;
  // 履歴ナビゲーション用（オプション）
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  /** お気に入り対象の履歴ID（未指定時は☆非表示） */
  historyId?: string | null;
  isFavorited?: boolean;
  favoriteBusy?: boolean;
  onToggleFavorite?: () => void;
  /** 画像下に表示する補足情報（未指定時は非表示） */
  caption?: ReactNode;
  /** 補足情報の配置（既定は画像下） */
  captionPlacement?: "below" | "side";
  /**
   * 単一の <img> の代わりに描画するノード（背景と立ち絵を重ねた合成プレビュー等）。
   * 未指定時は従来どおり imageUrl の <img> を描画する。
   */
  media?: ReactNode;
  /** ルート要素へ追加するテーマ用クラス（呼び出し側スタイルでの上書き用） */
  className?: string;
  /** 一覧の何件目を表示中か（例: "3 / 24"）。未指定時は非表示 */
  positionLabel?: string;
}

export default function ImagePreviewModal({
  isOpen,
  imageUrl,
  onClose,
  alt,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
  historyId = null,
  isFavorited = false,
  favoriteBusy = false,
  onToggleFavorite,
  caption,
  captionPlacement = "below",
  media,
  className,
  positionLabel,
}: ImagePreviewModalProps) {
  const { t } = useTranslation();
  const resolvedAlt = alt || t("imagePreview.imageAlt");
  const canFavorite = Boolean(historyId && onToggleFavorite);
  const useSideCaption = captionPlacement === "side" && Boolean(caption);
  // 画像下キャプション時は、長文の max-content 幅で枠が 90vw まで広がるのを防ぐ
  const useBelowCaption = captionPlacement !== "side" && Boolean(caption);

  // Swipe detection for mobile
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const SWIPE_THRESHOLD = 50;

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  }, []);

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!touchStartRef.current) return;
      const touch = e.changedTouches[0];
      const deltaX = touch.clientX - touchStartRef.current.x;
      const deltaY = touch.clientY - touchStartRef.current.y;
      touchStartRef.current = null;

      // Only trigger if horizontal swipe is dominant
      if (Math.abs(deltaX) < SWIPE_THRESHOLD) return;
      if (Math.abs(deltaY) > Math.abs(deltaX)) return;

      if (deltaX > 0 && onPrev && hasPrev) {
        onPrev();
      } else if (deltaX < 0 && onNext && hasNext) {
        onNext();
      }
    },
    [onPrev, onNext, hasPrev, hasNext],
  );

  // T028: ESC key and arrow key navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft" && onPrev && hasPrev) {
        onPrev();
      } else if (e.key === "ArrowRight" && onNext && hasNext) {
        onNext();
      }
    },
    [onClose, onPrev, onNext, hasPrev, hasNext],
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      // スクロール無効化
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleKeyDown]);

  // T029: オーバーレイクリックで閉じる
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen || (!imageUrl && !media)) return null;

  return (
    <div
      className={`image-preview-modal__overlay${className ? ` ${className}` : ""}`}
      onClick={handleOverlayClick}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      role="dialog"
      aria-modal="true"
      aria-label={t("imagePreview.dialogAria")}
    >
      <div
        className={`image-preview-modal__content${
          useSideCaption ? " image-preview-modal__content--side" : ""
        }${useBelowCaption ? " image-preview-modal__content--captioned" : ""}`}
      >
        <button
          type="button"
          className="image-preview-modal__close"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          ✕
        </button>

        {positionLabel && (
          <span className="image-preview-modal__position">{positionLabel}</span>
        )}

        {canFavorite && (
          <button
            type="button"
            className={`image-preview-modal__favorite${isFavorited ? " is-active" : ""}`}
            onClick={onToggleFavorite}
            disabled={favoriteBusy}
            aria-pressed={isFavorited}
            aria-label={
              isFavorited ? t("favorites.removeAria") : t("favorites.addAria")
            }
            title={
              isFavorited ? t("favorites.removeTitle") : t("favorites.addTitle")
            }
          >
            {isFavorited ? "★" : "☆"}
          </button>
        )}

        {/* 左ナビゲーションボタン */}
        {onPrev && (
          <button
            type="button"
            className={`image-preview-modal__nav image-preview-modal__nav--prev ${!hasPrev ? "is-disabled" : ""}`}
            onClick={hasPrev ? onPrev : undefined}
            disabled={!hasPrev}
            aria-label={t("imagePreview.prevImage")}
          >
            ‹
          </button>
        )}

        {media ?? (
          <img
            src={imageUrl as string}
            alt={resolvedAlt}
            className="image-preview-modal__image"
          />
        )}

        {caption && (
          <div
            className={`image-preview-modal__caption${useSideCaption ? " image-preview-modal__caption--side" : ""}`}
          >
            {caption}
          </div>
        )}

        {/* 右ナビゲーションボタン */}
        {onNext && (
          <button
            type="button"
            className={`image-preview-modal__nav image-preview-modal__nav--next ${!hasNext ? "is-disabled" : ""}`}
            onClick={hasNext ? onNext : undefined}
            disabled={!hasNext}
            aria-label={t("imagePreview.nextImage")}
          >
            ›
          </button>
        )}
      </div>
    </div>
  );
}
