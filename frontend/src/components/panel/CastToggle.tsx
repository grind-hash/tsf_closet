/**
 * CastToggle - 登場人物まわりの ON/OFF 用トグルスイッチ。
 */

import "./CastToggle.css";

interface CastToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** 読み上げ用のラベル。showLabel のときは画面にも出す */
  label: string;
  showLabel?: boolean;
  disabled?: boolean;
  /** 無効な理由などの補足 */
  title?: string;
  testId?: string;
}

export default function CastToggle({
  checked,
  onChange,
  label,
  showLabel = false,
  disabled = false,
  title,
  testId,
}: CastToggleProps) {
  return (
    <label
      className={`cast-toggle${disabled ? " cast-toggle--disabled" : ""}`}
      title={title}
    >
      {showLabel && <span className="cast-toggle__label">{label}</span>}
      <input
        type="checkbox"
        className="cast-toggle__input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={showLabel ? undefined : label}
        data-testid={testId}
      />
      <span className="cast-toggle__switch" aria-hidden="true" />
    </label>
  );
}
