/**
 * PromptExpanderModal - Prompt Expander 画面のモーダル共通シェル
 *
 * 背景クリック / Esc で閉じる。本文は children に任せる。
 */

import { type ReactNode, useEffect, useId } from "react";
import "./PromptExpanderShared.css";

interface PromptExpanderModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  closeLabel: string;
  children: ReactNode;
  footer?: ReactNode;
  /** ダイアログ幅のバリアント */
  size?: "sm" | "md" | "lg";
  className?: string;
}

export default function PromptExpanderModal({
  open,
  title,
  onClose,
  closeLabel,
  children,
  footer,
  size = "md",
  className,
}: PromptExpanderModalProps) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="prompt-expander__modal-backdrop"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className={[
          "prompt-expander__modal",
          `prompt-expander__modal--${size}`,
          className ?? "",
        ]
          .filter(Boolean)
          .join(" ")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="prompt-expander__modal-header">
          <h2 id={titleId} className="prompt-expander__modal-title">
            {title}
          </h2>
          <button
            type="button"
            className="prompt-expander__modal-close"
            aria-label={closeLabel}
            title={closeLabel}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="prompt-expander__modal-body">{children}</div>
        {footer && (
          <footer className="prompt-expander__modal-footer">{footer}</footer>
        )}
      </section>
    </div>
  );
}
