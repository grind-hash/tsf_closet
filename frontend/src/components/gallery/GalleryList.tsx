/**
 * GalleryList - ギャラリーリスト表示コンポーネント
 * 007-chat-interactive-ux
 */

import type { GalleryItem } from "../../types";
import { useTranslation } from "react-i18next";
import { API_BASE } from "../../utils/api";
import "./GalleryList.css";

interface GalleryListProps {
  items: GalleryItem[];
  onItemClick?: (item: GalleryItem) => void;
}

export default function GalleryList({ items, onItemClick }: GalleryListProps) {
  const { t, i18n } = useTranslation();
  // 日時をフォーマット
  const formatDate = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString(i18n.language === "en" ? "en-US" : "ja-JP", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  };

  return (
    <div className="gallery-list">
      <table className="gallery-list__table">
        <thead>
          <tr>
            <th className="gallery-list__th gallery-list__th--image">
              {t("gallery.tableImage")}
            </th>
            <th className="gallery-list__th gallery-list__th--instruction">
              {t("gallery.tableInstruction")}
            </th>
            <th className="gallery-list__th gallery-list__th--category">
              {t("gallery.tableCategory")}
            </th>
            <th className="gallery-list__th gallery-list__th--date">
              {t("gallery.tableDate")}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              className="gallery-list__row"
              onClick={() => onItemClick?.(item)}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onItemClick?.(item);
                }
              }}
            >
              <td className="gallery-list__td gallery-list__td--image">
                <img
                  src={`${API_BASE}${item.image_url}`}
                  alt={item.instruction || t("gallery.generatedImage")}
                  className="gallery-list__thumbnail"
                  loading="lazy"
                />
              </td>
              <td className="gallery-list__td gallery-list__td--instruction">
                {item.instruction || t("gallery.noInstruction")}
              </td>
              <td className="gallery-list__td gallery-list__td--category">
                {item.costume_category || "-"}
              </td>
              <td className="gallery-list__td gallery-list__td--date">
                {formatDate(item.timestamp)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
