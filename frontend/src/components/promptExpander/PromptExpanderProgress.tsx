/**
 * PromptExpanderProgress - 処理中（LLM プロンプト化 / 画像生成）の進捗表示
 *
 * 通常のヒント文言と区別できるよう、スピナー + 落ち着いた情報色の帯 + 下端の不確定バーで描く。
 * 進行中は異常ではないので、警告色・アクセント色は使わない。
 */

import "./PromptExpanderShared.css";

interface PromptExpanderProgressProps {
  label: string;
  className?: string;
}

export default function PromptExpanderProgress({
  label,
  className,
}: PromptExpanderProgressProps) {
  return (
    <div
      className={["prompt-expander__progress", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-live="polite"
    >
      <span className="prompt-expander__progress-spinner" aria-hidden="true" />
      <span className="prompt-expander__progress-text">{label}</span>
      <span className="prompt-expander__progress-bar" aria-hidden="true" />
    </div>
  );
}
