/**
 * PromptExpanderSessionList - Prompt Expander のセッション一覧
 *
 * 新規作成（タイトル入力 + ボタン）、インライン改名、削除（確認あり）、開く。
 * 各行にサムネイル・タイトル・件数・更新日時を表示する。
 */

import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { PromptExpanderSession } from "../../apis/promptExpander";
import { promptExpanderImageUrl } from "../../apis/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import PromptExpanderDeleteButton from "./PromptExpanderDeleteButton";
import "./PromptExpanderShared.css";
import "./PromptExpanderSessionList.css";

function formatDateTime(iso: string, language: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(language.startsWith("en") ? "en-US" : "ja-JP", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface SessionRowProps {
  session: PromptExpanderSession;
}

function SessionRow({ session }: SessionRowProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { renameSession, deleteSession } = usePromptExpander();
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(session.title);
  const [busy, setBusy] = useState(false);

  const title = session.title || t("promptExpander.sessions.untitled");

  const submitRename = async (event: FormEvent) => {
    event.preventDefault();
    const next = draftTitle.trim();
    if (!next || next === session.title) {
      setEditing(false);
      setDraftTitle(session.title);
      return;
    }
    setBusy(true);
    await renameSession(session.id, next);
    setBusy(false);
    setEditing(false);
  };

  const handleDelete = async () => {
    if (
      !window.confirm(t("promptExpander.sessions.deleteConfirm", { title }))
    ) {
      return;
    }
    setBusy(true);
    await deleteSession(session.id);
    setBusy(false);
  };

  return (
    <li className="prompt-expander__session-row">
      <button
        type="button"
        className="prompt-expander__session-open"
        onClick={() => navigate(`/prompt-expander/${session.id}`)}
        aria-label={t("promptExpander.sessions.open", { title })}
      >
        {session.thumbnail_url ? (
          <img
            className="prompt-expander__thumb"
            src={promptExpanderImageUrl(session.thumbnail_url)}
            alt=""
            loading="lazy"
          />
        ) : (
          <span className="prompt-expander__thumb prompt-expander__thumb--placeholder">
            {t("promptExpander.sessions.noThumb")}
          </span>
        )}
      </button>
      <div className="prompt-expander__session-main">
        {editing ? (
          <form
            className="prompt-expander__session-rename"
            onSubmit={submitRename}
          >
            <input
              className="prompt-expander__input"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              maxLength={200}
              disabled={busy}
              aria-label={t("promptExpander.sessions.renameLabel")}
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
              onClick={() => {
                setEditing(false);
                setDraftTitle(session.title);
              }}
              disabled={busy}
            >
              {t("promptExpander.sessions.renameCancel")}
            </button>
          </form>
        ) : (
          <button
            type="button"
            className="prompt-expander__session-title"
            onClick={() => navigate(`/prompt-expander/${session.id}`)}
          >
            {title}
          </button>
        )}
        <div className="prompt-expander__session-meta">
          <span>
            {t("promptExpander.sessions.entryCount", {
              count: session.entry_count,
            })}
          </span>
          <span>
            {t("promptExpander.sessions.updatedAt", {
              value: formatDateTime(session.updated_at, i18n.language),
            })}
          </span>
        </div>
      </div>
      <div className="prompt-expander__session-actions">
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm"
          onClick={() => setEditing(true)}
          disabled={busy || editing}
        >
          {t("promptExpander.sessions.rename")}
        </button>
        <PromptExpanderDeleteButton
          label={t("promptExpander.sessions.delete")}
          onClick={handleDelete}
          disabled={busy}
        />
      </div>
    </li>
  );
}

export default function PromptExpanderSessionList() {
  const { t } = useTranslation();
  const { sessions, loadingSessions, createSession } = usePromptExpander();
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (creating) return;
    setCreating(true);
    const created = await createSession(newTitle.trim() || undefined);
    setCreating(false);
    if (created) setNewTitle("");
  };

  return (
    <section
      className="prompt-expander__sessions"
      aria-label={t("promptExpander.sessions.title")}
    >
      <form className="prompt-expander__session-create" onSubmit={handleCreate}>
        <input
          className="prompt-expander__input"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder={t("promptExpander.sessions.newPlaceholder")}
          maxLength={200}
          disabled={creating}
          aria-label={t("promptExpander.sessions.newPlaceholder")}
        />
        <button
          type="submit"
          className="prompt-expander__btn prompt-expander__btn--primary"
          disabled={creating}
        >
          {creating
            ? t("promptExpander.sessions.creating")
            : t("promptExpander.sessions.create")}
        </button>
      </form>

      <h2 className="prompt-expander__sessions-heading">
        {t("promptExpander.sessions.title")}
      </h2>

      {loadingSessions && sessions.length === 0 ? (
        <p className="prompt-expander__empty">
          {t("promptExpander.sessions.loading")}
        </p>
      ) : sessions.length === 0 ? (
        <p className="prompt-expander__empty">
          {t("promptExpander.sessions.empty")}
        </p>
      ) : (
        <ul className="prompt-expander__session-list">
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </ul>
      )}
    </section>
  );
}
