import { useTranslation } from "react-i18next";
import type {
  GalleryOriginCounts,
  GallerySessionOrigin,
} from "../../apis/gallery";
import "./SessionOriginFilter.css";

const ORIGINS: readonly GallerySessionOrigin[] = ["all", "play", "salon"];

interface SessionOriginFilterProps {
  value: GallerySessionOrigin;
  counts: GalleryOriginCounts;
  onChange: (origin: GallerySessionOrigin) => void;
  className?: string;
}

/**
 * セッション一覧の絞り込みチップ(すべて / 通常プレイ / サロン経営)。
 * ギャラリーと、TSF シナリオ・Prompt Expander の姿を選ぶ画面で共有する。
 */
export default function SessionOriginFilter({
  value,
  counts,
  onChange,
  className,
}: SessionOriginFilterProps) {
  const { t } = useTranslation();
  return (
    <div
      className={`session-origin-filter${className ? ` ${className}` : ""}`}
      role="group"
      aria-label={t("gallery.origin.label")}
    >
      {ORIGINS.map((origin) => (
        <button
          key={origin}
          type="button"
          className={`session-origin-filter__chip${value === origin ? " is-active" : ""}`}
          aria-pressed={value === origin}
          onClick={() => onChange(origin)}
        >
          <span>{t(`gallery.origin.${origin}`)}</span>
          <span className="session-origin-filter__count">{counts[origin]}</span>
        </button>
      ))}
    </div>
  );
}
