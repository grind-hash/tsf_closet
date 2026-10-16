/**
 * 各画面に置く「お気に入りプロンプト」ボタン。
 *
 * - FavoritePromptInsertButton: 一覧ダイアログを開き、選ばれた内容を onInsert に渡す
 * - FavoritePromptSaveButton: text を内容に入れた新規フォームを開く（保存はフォームで行う）
 */

import { useTranslation } from "react-i18next";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import {
  FavoritePromptInsertIcon,
  FavoritePromptSaveIcon,
} from "./FavoritePromptIcons";
import "./FavoritePromptButtons.css";

interface CommonProps {
  /**
   * 既定の見た目（favorite-prompt-btn）の代わりに使うクラス。
   * 置き場所に既存のアイコンボタン様式がある場合はそれに合わせる。
   */
  className?: string;
  /** アイコンの一辺(px) */
  iconSize?: number;
  disabled?: boolean;
}

function buttonClass(className?: string): string {
  return className ?? "favorite-prompt-btn";
}

export function FavoritePromptInsertButton({
  onInsert,
  className,
  iconSize,
  disabled = false,
}: CommonProps & { onInsert: (content: string) => void }) {
  const { t } = useTranslation();
  const { openPicker } = useFavoritePrompts();
  const label = t("favoritePrompts.insertButton");
  return (
    <button
      type="button"
      className={buttonClass(className)}
      onClick={() => openPicker(onInsert)}
      aria-label={label}
      title={label}
      disabled={disabled}
    >
      <FavoritePromptInsertIcon size={iconSize} />
    </button>
  );
}

export function FavoritePromptSaveButton({
  text,
  className,
  iconSize,
  disabled = false,
}: CommonProps & { text: string }) {
  const { t } = useTranslation();
  const { openSaveDialog } = useFavoritePrompts();
  const label = t("favoritePrompts.saveButton");
  return (
    <button
      type="button"
      className={buttonClass(className)}
      onClick={() => openSaveDialog(text)}
      aria-label={label}
      title={label}
      disabled={disabled || !text.trim()}
    >
      <FavoritePromptSaveIcon size={iconSize} />
    </button>
  );
}
