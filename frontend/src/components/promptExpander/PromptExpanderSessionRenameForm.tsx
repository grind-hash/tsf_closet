/**
 * セッション名を変える入力欄（保存・キャンセル）。
 * 一覧の行と、セッションを開いているときの見出しの両方で使う。
 * Enter で保存、Esc でキャンセル。名前が空か変わっていなければ保存せずに閉じる。
 * 保存に失敗したときは閉じずに、入力した名前を残す。
 */

import { type FormEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PromptExpanderSession } from "../../apis/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";

interface PromptExpanderSessionRenameFormProps {
  session: PromptExpanderSession;
  /** 保存・キャンセルのあとに呼ぶ（入力欄を閉じる） */
  onDone: () => void;
  className?: string;
}

export default function PromptExpanderSessionRenameForm({
  session,
  onDone,
  className,
}: PromptExpanderSessionRenameFormProps) {
  const { t } = useTranslation();
  const { renameSession } = usePromptExpander();
  const [draftTitle, setDraftTitle] = useState(session.title);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const next = draftTitle.trim();
    if (!next || next === session.title) {
      onDone();
      return;
    }
    setBusy(true);
    const saved = await renameSession(session.id, next);
    setBusy(false);
    // 保存できなかったときは入力した名前を残し、そのまま保存し直せるようにする（エラーは通知で出る）
    if (saved) {
      onDone();
      return;
    }
    // 保存中は入力欄を無効にしていてフォーカスが外れるので、戻してから打ち直せるようにする
    window.requestAnimationFrame(() => inputRef.current?.focus());
  };

  return (
    <form
      className={["prompt-expander__session-rename", className]
        .filter(Boolean)
        .join(" ")}
      onSubmit={submit}
    >
      <input
        ref={inputRef}
        className="prompt-expander__input"
        value={draftTitle}
        onChange={(e) => setDraftTitle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onDone();
          }
        }}
        maxLength={200}
        disabled={busy}
        aria-label={t("promptExpander.sessions.renameLabel")}
        // 名前変更を押した直後にそのまま打ち直せるようにする
        autoFocus
      />
      <button
        type="submit"
        className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__btn--primary"
        disabled={busy}
      >
        {t("promptExpander.sessions.renameSave")}
      </button>
      <button
        type="button"
        className="prompt-expander__btn prompt-expander__btn--sm"
        onClick={onDone}
        disabled={busy}
      >
        {t("promptExpander.sessions.renameCancel")}
      </button>
    </form>
  );
}
