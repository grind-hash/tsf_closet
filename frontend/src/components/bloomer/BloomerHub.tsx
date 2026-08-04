import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type BloomerCharacter,
  type CreateRunRequest,
  fetchBloomerCharacters,
} from "../../apis/bloomer";
import { fetchGallerySessions } from "../../apis/gallery";
import { useBloomer } from "../../contexts/BloomerContext";
import type { GallerySession } from "../../types";
import MainLayout from "../layout/MainLayout";
import "./BloomerScreen.css";

export default function BloomerHub() {
  const { t } = useTranslation();
  const { runs, loading, error, loadRun, createRun, removeRun, clearError } =
    useBloomer();

  const [name, setName] = useState("");
  const [origin, setOrigin] = useState<"preset" | "session">("preset");
  const [creating, setCreating] = useState(false);

  // プリセットキャラ選択
  const [characters, setCharacters] = useState<BloomerCharacter[]>([]);
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);

  // セッション選択
  const [sessions, setSessions] = useState<GallerySession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  );
  const [sessionLoading, setSessionLoading] = useState(false);

  // キャラ・セッションを起動時ロード
  useEffect(() => {
    fetchBloomerCharacters().then((chars) => {
      setCharacters(chars);
      if (chars.length > 0) setSelectedCharId(chars[0].id);
    });
  }, []);

  useEffect(() => {
    if (origin !== "session") return;
    setSessionLoading(true);
    fetchGallerySessions(1, 30)
      .then((res) => {
        setSessions(res.sessions);
        if (res.sessions.length > 0)
          setSelectedSessionId(res.sessions[0].session_id);
      })
      .finally(() => setSessionLoading(false));
  }, [origin]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    if (origin === "session" && !selectedSessionId) return;
    setCreating(true);
    try {
      const req: CreateRunRequest = {
        origin,
        name: name.trim(),
        ...(origin === "preset" && selectedCharId
          ? { character_id: selectedCharId }
          : {}),
        ...(origin === "session" && selectedSessionId
          ? { source_session_id: selectedSessionId }
          : {}),
      };
      await createRun(req);
      setName("");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (runId: string) => {
    if (!window.confirm(t("bloomer.hub.confirmDelete"))) return;
    await removeRun(runId);
  };

  const canStart =
    !!name.trim() &&
    (origin === "preset" ? !!selectedCharId : !!selectedSessionId);

  return (
    <MainLayout>
      <div className="bloomer-hub">
        <h1 className="bloomer-hub__title">{t("bloomer.hub.title")}</h1>

        {error && (
          <div className="bloomer-hub__error" role="alert">
            {error}
            <button
              type="button"
              className="bloomer-hub__error-close"
              onClick={clearError}
            >
              ×
            </button>
          </div>
        )}

        <section className="bloomer-hub__create">
          <h2 className="bloomer-hub__section-title">
            {t("bloomer.hub.newRun")}
          </h2>

          {/* 起点選択 */}
          <div className="bloomer-hub__origin-tabs">
            <button
              type="button"
              className={`bloomer-hub__origin-tab${origin === "preset" ? " bloomer-hub__origin-tab--active" : ""}`}
              onClick={() => setOrigin("preset")}
            >
              {t("bloomer.hub.originPreset")}
            </button>
            <button
              type="button"
              className={`bloomer-hub__origin-tab${origin === "session" ? " bloomer-hub__origin-tab--active" : ""}`}
              onClick={() => setOrigin("session")}
            >
              {t("bloomer.hub.originSession")}
            </button>
          </div>

          {/* プリセットキャラ選択 */}
          {origin === "preset" && (
            <div className="bloomer-hub__char-list">
              {characters.map((ch) => (
                <button
                  key={ch.id}
                  type="button"
                  className={`bloomer-hub__char-card${selectedCharId === ch.id ? " bloomer-hub__char-card--selected" : ""}`}
                  onClick={() => setSelectedCharId(ch.id)}
                >
                  <span className="bloomer-hub__char-name">{ch.name}</span>
                  <span className="bloomer-hub__char-desc">
                    {ch.personality}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* セッション選択 */}
          {origin === "session" && (
            <div className="bloomer-hub__session-list">
              {sessionLoading && (
                <p className="bloomer-hub__loading">
                  {t("bloomer.hub.loading")}
                </p>
              )}
              {!sessionLoading && sessions.length === 0 && (
                <p className="bloomer-hub__empty">
                  {t("bloomer.hub.noSessions")}
                </p>
              )}
              {sessions.map((s) => (
                <button
                  key={s.session_id}
                  type="button"
                  className={`bloomer-hub__session-card${selectedSessionId === s.session_id ? " bloomer-hub__session-card--selected" : ""}`}
                  onClick={() => setSelectedSessionId(s.session_id)}
                >
                  <span className="bloomer-hub__session-name">
                    {s.character_name ?? s.session_id.slice(0, 8)}
                  </span>
                  <span className="bloomer-hub__session-meta">
                    {s.item_count} {t("bloomer.hub.sessionItems")}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* 名前入力 + 開始 */}
          <div className="bloomer-hub__create-row">
            <input
              className="bloomer-hub__name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canStart && !creating) handleCreate();
              }}
              placeholder={t("bloomer.hub.namePlaceholder")}
              maxLength={40}
            />
            <button
              type="button"
              className="bloomer-hub__create-btn"
              onClick={handleCreate}
              disabled={creating || !canStart}
            >
              {creating ? t("bloomer.hub.creating") : t("bloomer.hub.start")}
            </button>
          </div>
        </section>

        <section className="bloomer-hub__runs">
          <h2 className="bloomer-hub__section-title">
            {t("bloomer.hub.myRuns")}
          </h2>
          {loading && (
            <p className="bloomer-hub__loading">{t("bloomer.hub.loading")}</p>
          )}
          {!loading && runs.length === 0 && (
            <p className="bloomer-hub__empty">{t("bloomer.hub.noRuns")}</p>
          )}
          <ul className="bloomer-hub__run-list">
            {runs.map((run) => (
              <li
                key={run.id}
                className={`bloomer-hub__run-item bloomer-hub__run-item--${run.status}`}
              >
                <button
                  type="button"
                  className="bloomer-hub__run-name"
                  onClick={() => loadRun(run.id)}
                >
                  {run.name}
                </button>
                <span className="bloomer-hub__run-meta">
                  {t("bloomer.hub.dayLabel", {
                    day: run.day,
                    max: run.max_days,
                  })}
                  {" · "}
                  {t("bloomer.hub.stageLabel", { stage: run.stage })}
                  {run.status === "ended" && (
                    <span className="bloomer-hub__run-ended">
                      {" · "}
                      {t("bloomer.hub.ended")}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  className="bloomer-hub__run-delete"
                  onClick={() => handleDelete(run.id)}
                  aria-label={t("bloomer.hub.delete")}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </MainLayout>
  );
}
