/**
 * 設定項目の択一選択。
 *
 * 従来の画面ではラジオカード（選択肢ごとに説明付き）を出す。
 * 新しい設定画面ではセグメント型を出し、選んでいる選択肢の説明だけを下に出す。
 */

import { useContext } from "react";
import { SettingsViewContext } from "./SettingsView";

interface SettingsChoiceOption<T extends string> {
  id: T;
  label: string;
  description: string;
}

interface SettingsChoiceProps<T extends string> {
  /** radio の name */
  name: string;
  /** セグメント型の radiogroup に付ける名前（項目のラベル） */
  label: string;
  value: T;
  options: readonly SettingsChoiceOption<T>[];
  onChange: (value: T) => void;
}

export default function SettingsChoice<T extends string>({
  name,
  label,
  value,
  options,
  onChange,
}: SettingsChoiceProps<T>) {
  const { mode } = useContext(SettingsViewContext);

  if (mode === "classic") {
    return (
      <div className="settings-screen__radio-group">
        {options.map((option) => (
          <label key={option.id} className="settings-screen__radio">
            <input
              type="radio"
              name={name}
              value={option.id}
              checked={value === option.id}
              onChange={() => onChange(option.id)}
            />
            <div className="settings-screen__radio-content">
              <span className="settings-screen__radio-label">
                {option.label}
              </span>
              <span className="settings-screen__radio-desc">
                {option.description}
              </span>
            </div>
          </label>
        ))}
      </div>
    );
  }

  const selected = options.find((option) => option.id === value);
  return (
    <>
      <div
        className="settings-screen__segmented"
        role="radiogroup"
        aria-label={label}
      >
        {options.map((option) => (
          <label
            key={option.id}
            className={`settings-screen__segment${
              value === option.id ? " is-active" : ""
            }`}
          >
            <input
              type="radio"
              name={name}
              value={option.id}
              checked={value === option.id}
              onChange={() => onChange(option.id)}
            />
            {option.label}
          </label>
        ))}
      </div>
      {selected && (
        <p className="settings-screen__choice-desc">{selected.description}</p>
      )}
    </>
  );
}
