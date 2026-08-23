/**
 * PromptExpanderSection - 開閉できるコンポーザのセクション
 *
 * 見出しは <button aria-expanded aria-controls> で、クリックで開閉する。
 * 見出し右側の toolbar は見出しボタンの外に置き、操作してもセクションは開閉しない。
 * 開閉状態は usePersistedSectionState で localStorage に保持する。
 * 閉じている間も中身は DOM に残し（hidden）、入力状態を保つ。
 */

import { type ReactNode, useId } from "react";
import { usePersistedSectionState } from "../../hooks/usePersistedSectionState";
import "./PromptExpanderShared.css";
import "./PromptExpanderSection.css";

interface PromptExpanderSectionProps {
  /** localStorage 上のキー（params / prompt / characters / i2i / history） */
  id: string;
  title: ReactNode;
  /** 見出し右側の操作（クリックしても開閉しない） */
  toolbar?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
  /** 見出しの見出しレベル（既定 h3） */
  headingLevel?: "h2" | "h3";
}

export default function PromptExpanderSection({
  id,
  title,
  toolbar,
  defaultOpen = true,
  children,
  className,
  headingLevel = "h3",
}: PromptExpanderSectionProps) {
  const { open, toggle } = usePersistedSectionState(id, defaultOpen);
  const contentId = useId();
  const Heading = headingLevel;

  return (
    <section
      className={[
        "prompt-expander__section",
        open ? "is-open" : "is-collapsed",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-section-id={id}
    >
      <div className="prompt-expander__section-head">
        <Heading className="prompt-expander__section-heading">
          <button
            type="button"
            className="prompt-expander__section-toggle"
            aria-expanded={open}
            aria-controls={contentId}
            onClick={toggle}
          >
            <span
              className="prompt-expander__section-chevron"
              aria-hidden="true"
            >
              ▾
            </span>
            <span className="prompt-expander__section-title">{title}</span>
          </button>
        </Heading>
        {toolbar && (
          <div className="prompt-expander__section-toolbar">{toolbar}</div>
        )}
      </div>
      <div
        id={contentId}
        className="prompt-expander__section-body"
        hidden={!open}
      >
        {children}
      </div>
    </section>
  );
}
