/**
 * 色の選択欄: プリセット色、ブラウザ標準のカラーピッカー、#RRGGBB の直接入力。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

export const DEFAULT_FAVORITE_PROMPT_COLOR = "#6B7280";

const PRESET_COLORS = [
  "#6B7280",
  "#EF4444",
  "#F97316",
  "#EAB308",
  "#22C55E",
  "#3B82F6",
  "#A855F7",
  "#EC4899",
];

/** "#abc123" / "abc123" を "#ABC123" にそろえる。形式が違えば null */
export function normalizeHexColor(text: string): string | null {
  const trimmed = text.trim();
  const withHash = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  return /^#[0-9a-fA-F]{6}$/.test(withHash) ? withHash.toUpperCase() : null;
}

interface FavoritePromptColorFieldProps {
  value: string;
  onChange: (color: string) => void;
  /** 「色」見出しの id（グループ名として読み上げる） */
  labelId: string;
}

export default function FavoritePromptColorField({
  value,
  onChange,
  labelId,
}: FavoritePromptColorFieldProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(value);

  // プリセットやピッカーで変わった値を入力欄にも反映する
  useEffect(() => {
    setDraft(value);
  }, [value]);

  return (
    <div
      className="favorite-prompts__color"
      role="group"
      aria-labelledby={labelId}
    >
      <div className="favorite-prompts__swatches">
        {PRESET_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            className="favorite-prompts__swatch"
            style={{ backgroundColor: color }}
            aria-label={t("favoritePrompts.colorPreset", { color })}
            aria-pressed={value === color}
            onClick={() => onChange(color)}
          />
        ))}
      </div>
      <div className="favorite-prompts__color-row">
        <input
          type="color"
          className="favorite-prompts__color-input"
          value={value.toLowerCase()}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          aria-label={t("favoritePrompts.colorPicker")}
        />
        <input
          type="text"
          className="favorite-prompts__input favorite-prompts__hex"
          value={draft}
          maxLength={7}
          spellCheck={false}
          aria-label={t("favoritePrompts.colorHex")}
          onChange={(e) => {
            setDraft(e.target.value);
            const normalized = normalizeHexColor(e.target.value);
            if (normalized) onChange(normalized);
          }}
          onBlur={() => setDraft(value)}
        />
      </div>
    </div>
  );
}
