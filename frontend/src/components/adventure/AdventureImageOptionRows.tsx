import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ADVENTURE_IMAGE_MODEL_CHOICES } from "../../constants/novelaiImageModels";
import {
  type AdventureTurnImageSettings,
  estimateAdventureTurnSeconds,
  isAdventureTurnTextOnly,
} from "../../utils/adventureTurnTimeEstimate";

// セットアップ画面(AdventureHub)とプレイ中の画像設定ポップオーバー(AdventurePlay)で
// 共有する画像生成オプションの行。見出し・説明・トグルスイッチの markup を 1 か所に置く。

interface AdventureToggleRowProps {
  label: ReactNode;
  hint: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  /** adventure-precise-toggle に追加するクラス(例: adventure-inventory-toggle) */
  className?: string;
}

/** 見出し + 説明 + トグルスイッチの 1 行 */
export function AdventureToggleRow({
  label,
  hint,
  checked,
  disabled,
  onChange,
  className,
}: AdventureToggleRowProps) {
  return (
    <label
      className={`adventure-precise-toggle${className ? ` ${className}` : ""}`}
    >
      <span className="adventure-precise-toggle__info">
        <strong>{label}</strong>
        <small>{hint}</small>
      </span>
      <input
        type="checkbox"
        className="adventure-precise-toggle__input"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="adventure-precise-toggle__switch" />
    </label>
  );
}

interface AdventureImageModelPickerProps {
  /** "default" はグローバル設定に従う */
  value: string;
  hint: ReactNode;
  disabled?: boolean;
  onChange: (next: string) => void;
}

/** この run 専用の NovelAI 画像モデル選択 */
export function AdventureImageModelPicker({
  value,
  hint,
  disabled,
  onChange,
}: AdventureImageModelPickerProps) {
  const { t } = useTranslation();
  return (
    <label className="adventure-image-model-picker">
      <span className="adventure-precise-toggle__info">
        <strong>{t("adventure.imageModel")}</strong>
        <small>{hint}</small>
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="default">{t("adventure.imageModelDefault")}</option>
        {ADVENTURE_IMAGE_MODEL_CHOICES.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * 各トグルの結果である所要時間の見積もりと「テキストのみ」の告知。
 * スクロールしても見える先頭へ置く。
 */
export function AdventureTurnEstimate({
  settings,
}: {
  settings: AdventureTurnImageSettings;
}) {
  const { t } = useTranslation();
  return (
    <>
      <p className="adventure-turn-estimate">
        {t("adventure.turnTimeEstimate", {
          seconds: estimateAdventureTurnSeconds(settings),
        })}
      </p>
      {isAdventureTurnTextOnly(settings) && (
        <p className="adventure-turn-note">
          {t(
            settings.preset === "romance"
              ? "adventure.turnImagesDisabledNoticeRomance"
              : "adventure.turnImagesDisabledNotice",
          )}
        </p>
      )}
    </>
  );
}
