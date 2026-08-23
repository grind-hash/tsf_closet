/**
 * PromptExpanderDeleteButton - 削除用のアイコンボタン
 *
 * ギャラリーの gallery-card__delete-btn と同じ様式（ゴミ箱アイコン、通常は控えめ、
 * ホバー／フォーカスで赤くなる）。破壊的操作を「生成」などの主ボタンと同じ赤塗りや
 * 赤枠のテキストボタンにしないための共通部品。
 */

import "./PromptExpanderShared.css";

interface PromptExpanderDeleteButtonProps {
  /** アクセシブルな名前（aria-label / title に使う） */
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}

export default function PromptExpanderDeleteButton({
  label,
  onClick,
  disabled = false,
  className,
}: PromptExpanderDeleteButtonProps) {
  return (
    <button
      type="button"
      className={["prompt-expander__icon-btn", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
    </button>
  );
}
