import { type KeyboardEvent, type MouseEvent, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  type HakoniwaResident,
  type HakoniwaTouchPart,
  hakoniwaMediaUrl,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import HakoniwaPortrait from "./HakoniwaPortrait";

// 立ち絵の高さに対する境目: 上 30% は頭、58% までは胸、それより下は腰から下
const HEAD_LIMIT = 0.3;
const CHEST_LIMIT = 0.58;

export function touchPartAt(ratio: number): HakoniwaTouchPart {
  if (ratio < HEAD_LIMIT) return "head";
  if (ratio < CHEST_LIMIT) return "chest";
  return "lower";
}

interface HakoniwaTouchPreviewProps {
  resident: HakoniwaResident;
  onClose: () => void;
}

/** 住民の立ち絵の拡大表示。押した位置(頭・胸・腰から下)に触れ、住民の一言を出す */
export default function HakoniwaTouchPreview({
  resident,
  onClose,
}: HakoniwaTouchPreviewProps) {
  const { t } = useTranslation();
  const { busy, touchResident, touchReaction, clearTouchReaction } =
    useHakoniwa();
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const reaction =
    touchReaction?.residentId === resident.id ? touchReaction : null;
  const touching = busy === "touch";

  useEffect(() => {
    closeRef.current?.focus();
    return () => clearTouchReaction();
  }, [clearTouchReaction]);

  const handleTouch = (event: MouseEvent<HTMLButtonElement>) => {
    if (touching) return;
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = box.height > 0 ? (event.clientY - box.top) / box.height : 0;
    void touchResident(resident.id, touchPartAt(ratio));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };

  return (
    <div
      className="hakoniwa-touch"
      role="dialog"
      aria-modal="true"
      aria-label={t("hakoniwa.touch.title", { name: resident.name })}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-touch"
    >
      <div className="hakoniwa-touch__panel">
        <div className="hakoniwa-touch__head">
          <strong>{t("hakoniwa.touch.title", { name: resident.name })}</strong>
          <button
            ref={closeRef}
            type="button"
            className="hakoniwa-icon-button"
            aria-label={t("hakoniwa.touch.close")}
            title={t("hakoniwa.touch.close")}
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <p className="hakoniwa-note">{t("hakoniwa.touch.hint")}</p>
        <button
          type="button"
          className="hakoniwa-touch__figure"
          onClick={handleTouch}
          aria-label={t("hakoniwa.touch.figure", { name: resident.name })}
          data-testid="hakoniwa-touch-figure"
        >
          <HakoniwaPortrait
            src={hakoniwaMediaUrl(resident.display_avatar_url)}
            alt=""
            className="hakoniwa-touch__image"
          />
        </button>
        <div className="hakoniwa-touch__reaction" aria-live="polite">
          {touching ? (
            <span className="hakoniwa-chat__thinking" role="status">
              <span className="hakoniwa-spinner" aria-hidden />
              {t("hakoniwa.chat.thinking", { name: resident.name })}
            </span>
          ) : reaction ? (
            <span key={reaction.key}>
              <span className="hakoniwa-touch__part">
                {t(`hakoniwa.touch.part.${reaction.part}`)}
              </span>
              {t("hakoniwa.chronicle.line", { text: reaction.text })}
            </span>
          ) : (
            <span className="hakoniwa-note">{t("hakoniwa.touch.waiting")}</span>
          )}
        </div>
      </div>
    </div>
  );
}
