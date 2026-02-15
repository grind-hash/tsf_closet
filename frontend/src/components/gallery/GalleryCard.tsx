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
}

export default function GalleryCard({ item, onClick }: GalleryCardProps) {
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
    <button
      type="button"
      className="gallery-card"
      onClick={onClick}
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
        <span className="gallery-card__date">{formatDate(item.timestamp)}</span>
      </div>
    </button>
  );
}
