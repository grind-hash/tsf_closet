/**
 * GalleryCard - ギャラリーカードコンポーネント
 * 007-chat-interactive-ux
 */

import type { GalleryItem } from "../../types";
import { useTranslation } from "react-i18next";
import { API_BASE } from "../../utils/api";
import "./GalleryCard.css";

interface GalleryCardProps {
  item: GalleryItem;
  onClick?: () => void;
  onDelete?: (item: GalleryItem) => void;
}

export default function GalleryCard({
  item,
  onClick,
  onDelete,
}: GalleryCardProps) {
  const { t, i18n } = useTranslation();
  // 日時をフォーマット
  const formatDate = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleDateString(
        i18n.language === "en" ? "en-US" : "ja-JP",
        {
          month: "short",
          day: "numeric",
        },
      );
    } catch {
      return "";
    }
  };

  return (
    <div
      className="gallery-card"
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          onClick?.();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={t("gallery.imageAria", {
        text: item.instruction || t("gallery.viewDetail"),
      })}
    >
      <div className="gallery-card__image-container">
        <img
          src={`${API_BASE}${item.image_url}`}
          alt={item.instruction || t("gallery.generatedImage")}
          className="gallery-card__image"
          loading="lazy"
        />
        {item.costume_category && (
          <span className="gallery-card__category">
            {item.costume_category}
          </span>
        )}
      </div>

      <div className="gallery-card__info">
        <p className="gallery-card__instruction">
          {item.instruction || t("gallery.noInstruction")}
        </p>
        <div className="gallery-card__meta-row">
          <span className="gallery-card__date">
            {formatDate(item.timestamp)}
          </span>
          {onDelete && (
            <button
              type="button"
              className="gallery-card__delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(item);
              }}
              aria-label={t("gallery.deleteItemTitle")}
              title={t("gallery.deleteItemTitle")}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
