/**
 * ImagePreviewModal - 画像拡大プレビューモーダル
 * T027-T032: キャラクター画像クリックで拡大表示
 */

import { useEffect, useCallback } from "react";
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
}: ImagePreviewModalProps) {
  const { t } = useTranslation();
  const resolvedAlt = alt || t("imagePreview.imageAlt");
  // T028: ESCキーで閉じる、左右キーでナビゲーション
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

  if (!isOpen || !imageUrl) return null;

  return (
    <div
      className="image-preview-modal__overlay"
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-label={t("imagePreview.dialogAria")}
    >
      <div className="image-preview-modal__content">
        <button
          type="button"
          className="image-preview-modal__close"
          onClick={onClose}
          aria-label={t("common.close")}
        >
          ✕
        </button>

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

        <img
          src={imageUrl}
          alt={resolvedAlt}
          className="image-preview-modal__image"
        />

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
