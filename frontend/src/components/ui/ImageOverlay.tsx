/**
 * ImageOverlay - 画像拡大表示モーダル
 * US2: 周囲状況画像をクリックで拡大表示
 */

import { useEffect, useCallback } from "react";
import "./ImageOverlay.css";

interface ImageOverlayProps {
  imageUrl: string;
  alt?: string;
  onClose: () => void;
}

export default function ImageOverlay({
  imageUrl,
  alt = "拡大画像",
  onClose,
}: ImageOverlayProps) {
  // Escape キーで閉じる
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    // スクロール無効化
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  // 背景クリックで閉じる
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="image-overlay" onClick={handleBackdropClick}>
      <button
        className="image-overlay__close"
        onClick={onClose}
        aria-label="閉じる"
      >
        ×
      </button>
      <div className="image-overlay__content">
        <img src={imageUrl} alt={alt} className="image-overlay__image" />
      </div>
    </div>
  );
}
