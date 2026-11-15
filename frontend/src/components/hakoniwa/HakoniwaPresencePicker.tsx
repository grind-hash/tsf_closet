import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaPlayerPresence } from "../../apis/hakoniwa";

const PRESENCES: readonly HakoniwaPlayerPresence[] = ["known", "hidden"];

interface HakoniwaPresencePickerProps {
  value: HakoniwaPlayerPresence;
  onChange: (presence: HakoniwaPlayerPresence) => void;
  /** 世界の違和感を使うか(使わない世界の「見えない存在」は、声が謎のまま残る) */
  dissonanceEnabled: boolean;
  disabled?: boolean;
  /** 説明文の後ろに足す一文(設定タブでの切り替えの扱いなど) */
  extraNote?: string;
}

/**
 * 住民とあなた(顔なじみ / 見えない存在)の選択。作成画面と設定タブで使う。
 * 説明文には選んだ側の遊び方と、違和感の設定との組み合わせで変わる点を出す。
 */
export default function HakoniwaPresencePicker({
  value,
  onChange,
  dissonanceEnabled,
  disabled = false,
  extraNote,
}: HakoniwaPresencePickerProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const notes = [
    t(`hakoniwa.presence.notes.${value}`),
    value === "hidden" && !dissonanceEnabled
      ? t("hakoniwa.presence.hiddenWithoutDissonance")
      : null,
    extraNote ?? null,
  ].filter((note): note is string => Boolean(note));

  return (
    <div className="hakoniwa-presence">
      <div className="hakoniwa-presence__row">
        <span id={labelId}>{t("hakoniwa.presence.label")}</span>
        <div
          className="hakoniwa-segments"
          role="group"
          aria-labelledby={labelId}
        >
          {PRESENCES.map((option) => (
            <button
              key={option}
              type="button"
              className={value === option ? "is-active" : undefined}
              aria-pressed={value === option}
              disabled={disabled}
              onClick={() => onChange(option)}
            >
              {t(`hakoniwa.presence.options.${option}`)}
            </button>
          ))}
        </div>
      </div>
      {notes.map((note) => (
        <p key={note} className="hakoniwa-note">
          {note}
        </p>
      ))}
    </div>
  );
}
