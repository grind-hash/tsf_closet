/**
 * PromptExpanderSwitch - Prompt Expander 画面で使う ON/OFF トグルスイッチ
 *
 * ChatInput の chat-input__switch と同じ構造（checkbox + track + text）。
 * 素のチェックボックスを露出させないための共通部品。
 */

import type { ReactNode } from "react";
import "./PromptExpanderShared.css";

interface PromptExpanderSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
  title?: string;
  className?: string;
  /** テキスト→スイッチの順に並べる */
  labelFirst?: boolean;
}

export default function PromptExpanderSwitch({
  checked,
  onChange,
  label,
  disabled = false,
  title,
  className,
  labelFirst = false,
}: PromptExpanderSwitchProps) {
  const classes = [
    "prompt-expander__switch",
    labelFirst ? "prompt-expander__switch--label-first" : "",
    disabled ? "prompt-expander__switch--disabled" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  const text = <span className="prompt-expander__switch-text">{label}</span>;
  return (
    <label className={classes} title={title}>
      {labelFirst && text}
      <input
        type="checkbox"
        className="prompt-expander__switch-input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="prompt-expander__switch-track" aria-hidden="true" />
      {!labelFirst && text}
    </label>
  );
}
