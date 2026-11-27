/**
 * セッション名を変える入力欄（保存・キャンセル）。
 * 一覧の行と、セッションを開いているときの見出しの両方で使う。
 * Enter で保存、Esc でキャンセル。名前が空か変わっていなければ保存せずに閉じる。
 */

import { type FormEvent, useState } from "react";
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

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const next = draftTitle.trim();
    if (!next || next === session.title) {
      onDone();
      return;
    }
    setBusy(true);
    await renameSession(session.id, next);
    setBusy(false);
    onDone();
  };

  return (
    <form
      className={["prompt-expander__session-rename", className]
        .filter(Boolean)
        .join(" ")}
      onSubmit={submit}
    >
      <input
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
