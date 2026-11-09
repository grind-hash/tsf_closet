import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaTheme, HakoniwaThemePreset } from "../../apis/hakoniwa";

export const THEME_PRESETS: HakoniwaThemePreset[] = [
  "swap",
  "dress",
  "dissonance",
  "transform",
  "free",
];
const THEME_TEXT_MAX = 100;

type Mode = "none" | HakoniwaThemePreset | "custom";

function modeOf(theme: HakoniwaTheme | null): Mode {
  if (!theme) return "none";
  if (theme.text) return "custom";
  return theme.preset_id ?? "none";
}

/** 自由文が空のテーマはテーマ無しとして扱う */
export function normalizeTheme(
  theme: HakoniwaTheme | null,
): HakoniwaTheme | null {
  if (!theme) return null;
  const text = theme.text.trim();
  if (text) return { preset_id: null, text };
  return theme.preset_id ? { preset_id: theme.preset_id, text: "" } : null;
}

interface HakoniwaThemePickerProps {
  value: HakoniwaTheme | null;
  onChange: (theme: HakoniwaTheme | null) => void;
  disabled?: boolean;
}

/**
 * 実験テーマの選択(プリセット / 自分で書く / テーマ無し)。
 * 外から値を入れ直すときは key を変えて作り直す。
 */
export default function HakoniwaThemePicker({
  value,
  onChange,
  disabled = false,
}: HakoniwaThemePickerProps) {
  const { t } = useTranslation();
  const selectId = useId();
  const textId = useId();
  const [mode, setMode] = useState<Mode>(() => modeOf(value));
  const [text, setText] = useState(value?.text ?? "");

  const choose = (next: Mode) => {
    setMode(next);
    if (next === "none") onChange(null);
    else if (next === "custom") onChange({ preset_id: null, text });
    else onChange({ preset_id: next, text: "" });
  };

  return (
    <div className="hakoniwa-theme">
      <label className="hakoniwa-field" htmlFor={selectId}>
        <span>{t("hakoniwa.theme.label")}</span>
        <select
          id={selectId}
          value={mode}
          disabled={disabled}
          onChange={(event) => choose(event.target.value as Mode)}
        >
          <option value="none">{t("hakoniwa.theme.none")}</option>
          {THEME_PRESETS.map((preset) => (
            <option key={preset} value={preset}>
              {t(`hakoniwa.theme.presets.${preset}.name`)}
            </option>
          ))}
          <option value="custom">{t("hakoniwa.theme.custom")}</option>
        </select>
      </label>
      {mode !== "none" && mode !== "custom" && (
        <p className="hakoniwa-note">
          {t(`hakoniwa.theme.presets.${mode}.description`)}
        </p>
      )}
      {mode === "custom" && (
        <label className="hakoniwa-field" htmlFor={textId}>
          <span>{t("hakoniwa.theme.textLabel", { max: THEME_TEXT_MAX })}</span>
          <input
            id={textId}
            type="text"
            value={text}
            maxLength={THEME_TEXT_MAX}
            disabled={disabled}
            placeholder={t("hakoniwa.theme.textPlaceholder")}
            onChange={(event) => {
              setText(event.target.value);
              onChange({ preset_id: null, text: event.target.value });
            }}
          />
        </label>
      )}
      <p className="hakoniwa-note">{t("hakoniwa.theme.note")}</p>
    </div>
  );
}
