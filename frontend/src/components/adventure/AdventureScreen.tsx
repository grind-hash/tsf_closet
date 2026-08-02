import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import type { AdventurePreset } from "../../apis/adventure";
import { fetchGalleryList, fetchGallerySessions } from "../../apis/gallery";
import { useAdventure } from "../../contexts/AdventureContext";
import type { GalleryItem, GallerySession } from "../../types";
import { API_BASE } from "../../utils/api";
import ImagePreviewModal from "../ImagePreviewModal";
import MainLayout from "../layout/MainLayout";
import AdventureImagePromptModal from "./AdventureImagePromptModal";
import "./AdventureScreen.css";

const PRESETS: AdventurePreset[] = [
  "infiltration",
  "escape",
  "negotiation",
  "disguise",
];

function mediaUrl(url: string): string {
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

function AdventureHub() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    runs,
    templates,
    loading,
    setupGenerating,
    error,
    loadRuns,
    loadTemplates,
    generateSetup,
    createRun,
    removeRun,
    clearError,
  } = useAdventure();
  const [sessions, setSessions] = useState<GallerySession[]>([]);
  const [historyItems, setHistoryItems] = useState<GalleryItem[]>([]);
  const [sourceSessionId, setSourceSessionId] = useState("");
  const [sourceHistoryId, setSourceHistoryId] = useState<string | undefined>();
  const [startMode, setStartMode] = useState<"generated" | "authored">(
    "generated",
  );
  const [preset, setPreset] = useState<AdventurePreset>("infiltration");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedReplayRunId, setSelectedReplayRunId] = useState("");
  const [scenarioPickerOpen, setScenarioPickerOpen] = useState(false);
  const [scenarioPickerTab, setScenarioPickerTab] = useState<
    "authored" | "played"
  >("authored");
  const [scenarioSetting, setScenarioSetting] = useState("");
  const [scenarioObjective, setScenarioObjective] = useState("");
  const [scenarioConstraints, setScenarioConstraints] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void loadRuns();
    void loadTemplates();
    void fetchGallerySessions(1, 50).then((response) => {
      setSessions(response.sessions);
      if (response.sessions[0])
        setSourceSessionId(response.sessions[0].session_id);
    });
  }, [loadRuns, loadTemplates]);

  useEffect(() => {
    if (!sourceSessionId) {
      setHistoryItems([]);
      return;
    }
    setSourceHistoryId(undefined);
    setScenarioSetting("");
    setScenarioObjective("");
    setScenarioConstraints("");
    void fetchGalleryList(1, 50, sourceSessionId).then((response) =>
      setHistoryItems(response.items),
    );
  }, [sourceSessionId]);

  const selectedSession = sessions.find(
    (session) => session.session_id === sourceSessionId,
  );
  const selectedTemplate = templates.find(
    (template) => template.id === selectedTemplateId,
  );
  const selectedReplayRun = runs.find((run) => run.id === selectedReplayRunId);
  const selectedScenario = selectedReplayRun ?? selectedTemplate;
  const selectedScenarioPreset =
    selectedReplayRun?.preset ?? selectedTemplate?.preset;

  const sortedRuns = useMemo(
    () =>
      [...runs].sort((a, b) => {
        if (a.status === "active" && b.status !== "active") return -1;
        if (b.status === "active" && a.status !== "active") return 1;
        return (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
      }),
    [runs],
  );

  useEffect(() => {
    if (!scenarioPickerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setScenarioPickerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [scenarioPickerOpen]);

  const clearGeneratedSetup = () => {
    setScenarioSetting("");
    setScenarioObjective("");
    setScenarioConstraints("");
  };

  const openScenarioPicker = () => {
    setScenarioPickerTab(selectedReplayRunId ? "played" : "authored");
    setScenarioPickerOpen(true);
  };
  const handleGenerateSetup = async () => {
    if (!sourceSessionId) return;
    try {
      const generated = await generateSetup({
        source_session_id: sourceSessionId,
        source_history_id: sourceHistoryId,
        preset,
      });
      setScenarioSetting(generated.setting);
      setScenarioObjective(generated.objective);
      setScenarioConstraints(generated.constraints.join("\n"));
      setDetailsOpen(true);
    } catch {
      return;
    }
  };

  const startDisabledReason = (): string | null => {
    if (!sourceSessionId) return t("adventure.disabledReason.noSession");
    if (startMode === "generated" && !scenarioObjective.trim())
      return t("adventure.disabledReason.noObjective");
    if (startMode === "authored" && !selectedScenario)
      return t("adventure.disabledReason.noScenario");
    return null;
  };

  const handleCreate = async () => {
    if (!sourceSessionId) return;
    const authoredTemplate =
      startMode === "authored" && !selectedReplayRun ? selectedTemplate : null;
    setCreating(true);
    try {
      const run = await createRun({
        source_session_id: sourceSessionId,
        source_history_id: sourceHistoryId,
        preset: selectedReplayRun?.preset ?? authoredTemplate?.preset ?? preset,
        custom_setup: "",
        scenario_setting: startMode === "generated" ? scenarioSetting : "",
        scenario_objective: startMode === "generated" ? scenarioObjective : "",
        scenario_constraints:
          startMode === "generated"
            ? scenarioConstraints
                .split("\n")
                .map((item) => item.trim())
                .filter(Boolean)
            : [],
        scenario_template_id: authoredTemplate?.id,
        replay_run_id: selectedReplayRun?.id,
      });
      navigate(`/adventure/${run.id}`);
    } catch {
      return;
    } finally {
      setCreating(false);
    }
  };

  const disabledReason = startDisabledReason();

  return (
    <MainLayout>
      <div className="adventure-hub">
        <header className="adventure-hub__header">
          <div>
            <p className="adventure-eyebrow">TSF Closet</p>
            <h1>{t("adventure.title")}</h1>
          </div>
        </header>

        {error && (
          <button
            type="button"
            className="adventure-error"
            onClick={clearError}
          >
            {error}
          </button>
        )}

        <section className="adventure-card adventure-card--source">
          <h2>{t("adventure.stepSource")}</h2>
          <p className="adventure-card__hint">
            {t("adventure.stepSourceHint")}
          </p>
          <label className="adventure-source-select">
            <span>{t("adventure.sourceSession")}</span>
            <select
              value={sourceSessionId}
              disabled={setupGenerating || loading}
              onChange={(event) => setSourceSessionId(event.target.value)}
            >
              {sessions.map((session) => (
                <option key={session.session_id} value={session.session_id}>
                  {session.character_name ?? t("adventure.unnamedCharacter")} ·{" "}
                  {session.item_count}
                </option>
              ))}
            </select>
          </label>

          {selectedSession && (
            <>
              <div
                className="adventure-source-grid"
                role="group"
                aria-label={t("adventure.sourceState")}
              >
                <button
                  type="button"
                  disabled={setupGenerating || loading}
                  className={!sourceHistoryId ? "is-selected" : ""}
                  onClick={() => {
                    setSourceHistoryId(undefined);
                    clearGeneratedSetup();
                  }}
                >
                  <img
                    src={mediaUrl(selectedSession.thumbnail_url)}
                    alt={t("adventure.currentState")}
                  />
                  <span>{t("adventure.currentState")}</span>
                </button>
                {historyItems.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    disabled={setupGenerating || loading}
                    className={sourceHistoryId === item.id ? "is-selected" : ""}
                    onClick={() => {
                      setSourceHistoryId(item.id);
                      clearGeneratedSetup();
                    }}
                  >
                    <img
                      src={mediaUrl(item.image_url)}
                      alt={item.instruction}
                    />
                    <span>{item.instruction}</span>
                  </button>
                ))}
              </div>
              <p className="adventure-source-summary">
                {t("adventure.selectedSourceSummary", {
                  name:
                    selectedSession.character_name ??
                    t("adventure.unnamedCharacter"),
                  state: sourceHistoryId
                    ? (historyItems.find((item) => item.id === sourceHistoryId)
                        ?.instruction ?? t("adventure.currentState"))
                    : t("adventure.currentState"),
                })}
              </p>
            </>
          )}
        </section>

        <section className="adventure-card adventure-card--mission">
          <h2>{t("adventure.stepMission")}</h2>
          <p className="adventure-card__hint">
            {t("adventure.stepMissionHint")}
          </p>

          <fieldset className="adventure-start-mode-cards">
            <legend>{t("adventure.startMode")}</legend>
            <div className="adventure-mode-cards">
              <button
                type="button"
                disabled={setupGenerating || loading}
                className={startMode === "generated" ? "is-active" : ""}
                onClick={() => setStartMode("generated")}
                aria-pressed={startMode === "generated"}
              >
                <strong>{t("adventure.startModes.generated")}</strong>
                <span>{t("adventure.startModeHints.generated")}</span>
              </button>
              <button
                type="button"
                disabled={setupGenerating || loading}
                className={startMode === "authored" ? "is-active" : ""}
                onClick={() => {
                  setStartMode("authored");
                  openScenarioPicker();
                }}
                aria-pressed={startMode === "authored"}
              >
                <strong>{t("adventure.startModes.authored")}</strong>
                <span>{t("adventure.startModeHints.authored")}</span>
              </button>
            </div>
          </fieldset>

          {startMode === "generated" ? (
            <>
              <fieldset className="adventure-setup__mission">
                <legend>{t("adventure.preset")}</legend>
                <div className="adventure-preset-cards">
                  {PRESETS.map((value) => (
                    <button
                      type="button"
                      key={value}
                      disabled={setupGenerating || loading}
                      className={preset === value ? "is-active" : ""}
                      onClick={() => {
                        setPreset(value);
                        clearGeneratedSetup();
                        setDetailsOpen(false);
                      }}
                      aria-pressed={preset === value}
                    >
                      <strong>{t(`adventure.presets.${value}`)}</strong>
                      <span>{t(`adventure.presetHints.${value}`)}</span>
                      <small>{t(`adventure.presetExamples.${value}`)}</small>
                    </button>
                  ))}
                </div>
              </fieldset>

              <ol className="adventure-mission-flow">
                <li>{t("adventure.missionFlow.step1")}</li>
                <li>{t("adventure.missionFlow.step2")}</li>
                <li>{t("adventure.missionFlow.step3")}</li>
              </ol>

              <div className="adventure-setup-generator">
                <button
                  type="button"
                  disabled={!sourceSessionId || setupGenerating || loading}
                  aria-busy={setupGenerating}
                  onClick={() => void handleGenerateSetup()}
                >
                  {setupGenerating && (
                    <span className="adventure-setup-generator__spinner" />
                  )}
                  {setupGenerating
                    ? t("adventure.generatingSetup")
                    : t("adventure.generateSetup")}
                </button>
              </div>

              <details
                className="adventure-setup-details-wrapper"
                open={detailsOpen}
                onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
              >
                <summary>{t("adventure.detailsToggle")}</summary>
                <div className="adventure-setup-details">
                  <label>
                    <span>{t("adventure.setting")}</span>
                    <textarea
                      value={scenarioSetting}
                      maxLength={600}
                      rows={2}
                      onChange={(event) =>
                        setScenarioSetting(event.target.value)
                      }
                      placeholder={t("adventure.settingPlaceholder")}
                    />
                  </label>
                  <label>
                    <span>{t("adventure.goal")}</span>
                    <textarea
                      value={scenarioObjective}
                      maxLength={600}
                      rows={2}
                      onChange={(event) =>
                        setScenarioObjective(event.target.value)
                      }
                      placeholder={t("adventure.goalPlaceholder")}
                    />
                  </label>
                  <label>
                    <span>{t("adventure.constraints")}</span>
                    <textarea
                      value={scenarioConstraints}
                      maxLength={1200}
                      rows={3}
                      onChange={(event) =>
                        setScenarioConstraints(event.target.value)
                      }
                      placeholder={t("adventure.constraintsPlaceholder")}
                    />
                  </label>
                </div>
              </details>
            </>
          ) : (
            <div className="adventure-selected-scenario">
              <span>{t("adventure.selectedScenario")}</span>
              {selectedScenario ? (
                <>
                  <strong>{selectedScenario.title}</strong>
                  <p>{selectedScenario.objective}</p>
                  <small>
                    {selectedReplayRun
                      ? t("adventure.scenarioTabs.played")
                      : t("adventure.scenarioTabs.authored")}
                    {selectedScenarioPreset &&
                      ` · ${t("adventure.presetFromScenario")}: ${t(
                        `adventure.presets.${selectedScenarioPreset}`,
                      )}`}
                  </small>
                </>
              ) : (
                <p>{t("adventure.noScenarioSelected")}</p>
              )}
              <button
                type="button"
                disabled={loading}
                onClick={openScenarioPicker}
              >
                {selectedScenario
                  ? t("adventure.chooseScenarioAgain")
                  : t("adventure.selectScenario")}
              </button>
            </div>
          )}

          {disabledReason && (
            <p className="adventure-disabled-reason" role="status">
              {disabledReason}
            </p>
          )}

          <button
            type="button"
            className="adventure-primary"
            disabled={
              loading || setupGenerating || creating || !!disabledReason
            }
            onClick={() => void handleCreate()}
          >
            {creating ? t("adventure.preparing") : t("adventure.start")}
          </button>
        </section>

        <section className="adventure-runs">
          <h2>{t("adventure.savedRuns")}</h2>
          {runs.length === 0 ? (
            <p className="adventure-empty">{t("adventure.noRuns")}</p>
          ) : (
            <div className="adventure-run-list">
              {sortedRuns.map((run) => (
                <article key={run.id} className="adventure-run-item">
                  <img src={run.current_image_url} alt={run.title} />
                  <div>
                    <div className="adventure-run-item__title-row">
                      <strong>{run.title}</strong>
                      <span
                        className={`adventure-run-badge adventure-run-badge--${run.status}`}
                      >
                        {t(`adventure.status.${run.status}`)}
                      </span>
                    </div>
                    <p>{run.objective}</p>
                    <div className="adventure-run-progress">
                      <span className="adventure-run-progress__bar">
                        <span
                          style={{
                            width: `${Math.min(100, (run.turn_count / run.max_turns) * 100)}%`,
                          }}
                        />
                      </span>
                      <span className="adventure-run-progress__label">
                        {run.turn_count}/{run.max_turns}
                      </span>
                    </div>
                  </div>
                  <div className="adventure-run-item__actions">
                    <button
                      type="button"
                      onClick={() => navigate(`/adventure/${run.id}`)}
                    >
                      {t("adventure.resume")}
                    </button>
                    <button
                      type="button"
                      className="is-danger"
                      onClick={() => {
                        if (window.confirm(t("adventure.deleteConfirm"))) {
                          void removeRun(run.id);
                        }
                      }}
                    >
                      {t("adventure.delete")}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
      {scenarioPickerOpen && (
        <div
          className="adventure-scenario-modal"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target)
              setScenarioPickerOpen(false);
          }}
        >
          <section
            className="adventure-scenario-modal__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="adventure-scenario-modal-title"
          >
            <header>
              <h2 id="adventure-scenario-modal-title">
                {t("adventure.selectScenario")}
              </h2>
              <button
                type="button"
                className="adventure-scenario-modal__close"
                aria-label={t("adventure.closeScenarioPicker")}
                onClick={() => setScenarioPickerOpen(false)}
              >
                ×
              </button>
            </header>
            <div className="adventure-scenario-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={scenarioPickerTab === "played"}
                className={scenarioPickerTab === "played" ? "is-active" : ""}
                onClick={() => setScenarioPickerTab("played")}
              >
                {t("adventure.scenarioTabs.played")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={scenarioPickerTab === "authored"}
                className={scenarioPickerTab === "authored" ? "is-active" : ""}
                onClick={() => setScenarioPickerTab("authored")}
              >
                {t("adventure.scenarioTabs.authored")}
              </button>
            </div>
            <div className="adventure-scenario-modal__list">
              {scenarioPickerTab === "authored" ? (
                templates.length === 0 ? (
                  <p className="adventure-empty">
                    {t("adventure.noTemplates")}
                  </p>
                ) : (
                  templates.map((template) => (
                    <button
                      type="button"
                      key={template.id}
                      className={
                        selectedTemplateId === template.id &&
                        !selectedReplayRunId
                          ? "is-selected"
                          : ""
                      }
                      onClick={() => {
                        setSelectedTemplateId(template.id);
                        setSelectedReplayRunId("");
                        setStartMode("authored");
                        setScenarioPickerOpen(false);
                      }}
                    >
                      <span className="adventure-template-item__title">
                        <strong>{template.title}</strong>
                        {template.content_rating === "mature" && (
                          <small>{t("adventure.matureScenario")}</small>
                        )}
                      </span>
                      <span>{template.synopsis}</span>
                      <span className="adventure-scenario-option__meta">
                        {t("adventure.templateMeta", {
                          turns: template.max_turns,
                          preset: t(`adventure.presets.${template.preset}`),
                        })}
                      </span>
                      <span className="adventure-scenario-option__detail">
                        <b>{t("adventure.goal")}</b>
                        <span>{template.objective}</span>
                      </span>
                      <span className="adventure-scenario-option__detail">
                        <b>{t("adventure.constraints")}</b>
                        <span>{template.constraints.join(" / ")}</span>
                      </span>
                    </button>
                  ))
                )
              ) : runs.length === 0 ? (
                <p className="adventure-empty">
                  {t("adventure.noPlayedScenarios")}
                </p>
              ) : (
                runs.map((run) => (
                  <button
                    type="button"
                    key={run.id}
                    className={
                      selectedReplayRunId === run.id ? "is-selected" : ""
                    }
                    onClick={() => {
                      setSelectedReplayRunId(run.id);
                      setSelectedTemplateId("");
                      setStartMode("authored");
                      setScenarioPickerOpen(false);
                    }}
                  >
                    <span className="adventure-template-item__title">
                      <strong>{run.title}</strong>
                      <small>{t(`adventure.status.${run.status}`)}</small>
                    </span>
                    <span>{run.objective}</span>
                    <span className="adventure-scenario-option__meta">
                      {t("adventure.playedScenarioMeta", {
                        turns: run.turn_count,
                        maxTurns: run.max_turns,
                      })}
                    </span>
                  </button>
                ))
              )}
            </div>
          </section>
        </div>
      )}
      {creating && (
        <div
          className="adventure-preparing-overlay"
          role="status"
          aria-live="polite"
        >
          <span className="adventure-preparing-overlay__spinner" aria-hidden />
          <strong>{t("adventure.preparingTitle")}</strong>
          <p>{t("adventure.preparingDetail")}</p>
        </div>
      )}
    </MainLayout>
  );
}

interface AdventureStageFrame {
  key: string;
  turnNumber: number;
  imageUrl: string;
  userInput: string | null;
  narrative: string;
}

function AdventurePlay({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    activeRun,
    loading,
    streaming,
    phase,
    streamingNarrative,
    pendingUserInput,
    error,
    loadRun,
    submitTurn,
    regenerateImage,
    clearError,
  } = useAdventure();
  const [input, setInput] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const turnStripEndRef = useRef<HTMLDivElement>(null);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number | null>(
    null,
  );
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [promptModalOpen, setPromptModalOpen] = useState(false);

  useEffect(() => {
    void loadRun(runId).catch(() => navigate("/adventure"));
  }, [loadRun, navigate, runId]);

  useEffect(() => {
    if (!activeRun) return;
    transcriptEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeRun]);

  useEffect(() => {
    if (!streamingNarrative) return;
    transcriptEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [streamingNarrative]);

  const frames = useMemo<AdventureStageFrame[]>(() => {
    if (!activeRun) return [];
    const list: AdventureStageFrame[] = [];
    if (activeRun.opening_image_url) {
      list.push({
        key: "opening",
        turnNumber: 0,
        imageUrl: activeRun.opening_image_url,
        userInput: null,
        narrative: activeRun.opening_narrative,
      });
    }
    for (const turn of activeRun.turns) {
      if (!turn.image_url) continue;
      list.push({
        key: turn.id,
        turnNumber: turn.turn_number,
        imageUrl: turn.image_url,
        userInput: turn.user_input,
        narrative: turn.narrative,
      });
    }
    return list;
  }, [activeRun]);

  // 新しいターン到着・画像再生成時は自動的に最新表示へ復帰する
  // biome-ignore lint/correctness/useExhaustiveDependencies: turn_count/current_image_url の変化を検知するための依存
  useEffect(() => {
    setSelectedFrameIndex(null);
  }, [activeRun?.turn_count, activeRun?.current_image_url]);

  useEffect(() => {
    if (frames.length === 0) return;
    turnStripEndRef.current?.scrollIntoView({
      block: "nearest",
      inline: "end",
    });
  }, [frames.length]);

  if (loading || !activeRun || activeRun.id !== runId) {
    return (
      <MainLayout>
        <div className="adventure-loading">{t("adventure.loading")}</div>
      </MainLayout>
    );
  }

  const isStageLoading = streaming && phase !== null;
  const isViewingPast = selectedFrameIndex !== null;
  const effectiveIndex =
    selectedFrameIndex ?? (frames.length > 0 ? frames.length - 1 : -1);
  const selectedFrame =
    effectiveIndex >= 0 ? frames[effectiveIndex] : undefined;
  const displayedImageUrl = isViewingPast
    ? (selectedFrame?.imageUrl ?? activeRun.current_image_url)
    : activeRun.current_image_url;

  const goToFrame = (index: number) => {
    if (index < 0 || index >= frames.length) return;
    setSelectedFrameIndex(index === frames.length - 1 ? null : index);
  };

  const submit = (value: string, kind: "choice" | "free_text") => {
    const trimmed = value.trim();
    if (!trimmed || streaming || activeRun.status !== "active") return;
    setInput("");
    void submitTurn(trimmed, kind);
  };

  return (
    <MainLayout>
      <div className="adventure-play">
        <header className="adventure-play__header">
          <button
            type="button"
            onClick={() => navigate("/adventure")}
            aria-label={t("adventure.back")}
          >
            ←
          </button>
          <div>
            <p>{activeRun.title}</p>
            <span className="adventure-objective-label">
              {t("adventure.goal")}
            </span>
            <h1>{activeRun.objective}</h1>
          </div>
          <div className="adventure-turn-counter">
            <span>{t("adventure.remaining")}</span>
            <strong>{activeRun.remaining_turns}</strong>
          </div>
        </header>

        {error && (
          <button
            type="button"
            className="adventure-error"
            onClick={clearError}
          >
            {error}
          </button>
        )}

        <div className="adventure-play__body">
          <section className="adventure-stage" aria-busy={isStageLoading}>
            <div className="adventure-stage__frame">
              <button
                type="button"
                className="adventure-stage__image-button"
                onClick={() => setLightboxOpen(true)}
                disabled={frames.length === 0}
                aria-label={t("adventure.viewFullScreen")}
              >
                <img
                  className={isStageLoading ? "is-generating" : undefined}
                  src={displayedImageUrl}
                  alt={activeRun.title}
                />
              </button>
              {isStageLoading && !isViewingPast && (
                <div className="adventure-stage__loading" role="status">
                  <span className="adventure-stage__loading-spinner" />
                  <strong>{t(`adventure.phase.${phase}`)}</strong>
                </div>
              )}
              {isViewingPast && (
                <div className="adventure-stage__past-banner">
                  <span>{t("adventure.turnStrip.viewingPast")}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedFrameIndex(null)}
                  >
                    {t("adventure.turnStrip.backToLatest")}
                  </button>
                </div>
              )}
              <button
                type="button"
                className="adventure-stage__regenerate"
                onClick={() => setPromptModalOpen(true)}
                disabled={streaming || isViewingPast}
                title={t("adventure.regenerateImage")}
                aria-label={t("adventure.regenerateImage")}
              >
                ↻
              </button>
            </div>

            {frames.length > 1 && (
              <div className="adventure-turn-strip">
                {frames.map((frame, index) => {
                  const isActive =
                    selectedFrameIndex === index ||
                    (selectedFrameIndex === null &&
                      index === frames.length - 1);
                  return (
                    <button
                      type="button"
                      key={frame.key}
                      className={`adventure-turn-strip__item${isActive ? " is-active" : ""}`}
                      onClick={() => goToFrame(index)}
                      aria-current={isActive ? "true" : undefined}
                      title={
                        frame.turnNumber === 0
                          ? t("adventure.turnStrip.opening")
                          : t("adventure.turn", { number: frame.turnNumber })
                      }
                    >
                      <img
                        src={frame.imageUrl}
                        alt={t("adventure.turnStrip.thumbAlt", {
                          number: frame.turnNumber,
                        })}
                        className="adventure-turn-strip__thumb"
                      />
                      <span className="adventure-turn-strip__badge">
                        {frame.turnNumber === 0
                          ? t("adventure.turnStrip.opening")
                          : frame.turnNumber}
                      </span>
                    </button>
                  );
                })}
                <div ref={turnStripEndRef} />
              </div>
            )}

            {isViewingPast && selectedFrame && (
              <div className="adventure-turn-caption">
                <strong>
                  {selectedFrame.turnNumber === 0
                    ? t("adventure.turnStrip.opening")
                    : t("adventure.turn", {
                        number: selectedFrame.turnNumber,
                      })}
                </strong>
                {selectedFrame.userInput && <p>{selectedFrame.userInput}</p>}
                <p>{selectedFrame.narrative}</p>
              </div>
            )}
          </section>

          <section className="adventure-story" aria-live="polite">
            <div className="adventure-story__text">
              <div className="adventure-transcript">
                <article className="adventure-transcript__entry is-opening">
                  <span>{t("adventure.openingScene")}</span>
                  <p>{activeRun.opening_narrative}</p>
                </article>
                {activeRun.turns.map((turn) => (
                  <article
                    className="adventure-transcript__entry"
                    key={turn.id}
                  >
                    <div className="adventure-transcript__action">
                      <span>
                        {t("adventure.turn", { number: turn.turn_number })}
                      </span>
                      <p>{turn.user_input}</p>
                    </div>
                    <p>{turn.narrative}</p>
                  </article>
                ))}
                {pendingUserInput !== null && (
                  <article className="adventure-transcript__entry is-streaming">
                    <div className="adventure-transcript__action">
                      <span>
                        {t("adventure.turn", {
                          number: activeRun.turn_count + 1,
                        })}
                      </span>
                      <p>{pendingUserInput}</p>
                    </div>
                    <p>
                      {streamingNarrative}
                      <span className="adventure-transcript__caret" />
                    </p>
                  </article>
                )}
                <div ref={transcriptEndRef} />
              </div>
              {streaming && !isStageLoading && (
                <div className="adventure-progress">
                  <span />
                  {t(`adventure.phase.${phase ?? "narrative"}`)}
                </div>
              )}
            </div>

            {activeRun.clues.length > 0 && (
              <div className="adventure-clues">
                <h2>{t("adventure.clues")}</h2>
                <ul>
                  {activeRun.clues.map((clue) => (
                    <li key={clue}>{clue}</li>
                  ))}
                </ul>
              </div>
            )}

            {activeRun.status === "active" ? (
              <div className="adventure-controls">
                <div className="adventure-choices">
                  {activeRun.choices.map((choice) => (
                    <button
                      type="button"
                      key={choice.id}
                      disabled={streaming}
                      onClick={() => submit(choice.label, "choice")}
                    >
                      {choice.label}
                    </button>
                  ))}
                </div>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    submit(input, "free_text");
                  }}
                >
                  <textarea
                    value={input}
                    rows={2}
                    maxLength={1000}
                    disabled={streaming}
                    onChange={(event) => setInput(event.target.value)}
                    placeholder={t("adventure.freeInput")}
                  />
                  <button type="submit" disabled={!input.trim() || streaming}>
                    {t("adventure.send")}
                  </button>
                </form>
              </div>
            ) : (
              <div className={`adventure-ending is-${activeRun.status}`}>
                <span>{t(`adventure.status.${activeRun.status}`)}</span>
                <h2>{activeRun.ending_title}</h2>
                <p>{activeRun.ending_summary}</p>
              </div>
            )}
          </section>
        </div>
      </div>

      <ImagePreviewModal
        isOpen={lightboxOpen}
        imageUrl={selectedFrame?.imageUrl ?? null}
        onClose={() => setLightboxOpen(false)}
        alt={activeRun.title}
        onPrev={() => goToFrame(effectiveIndex - 1)}
        onNext={() => goToFrame(effectiveIndex + 1)}
        hasPrev={effectiveIndex > 0}
        hasNext={effectiveIndex < frames.length - 1}
        caption={
          selectedFrame && (
            <>
              <strong>
                {selectedFrame.turnNumber === 0
                  ? t("adventure.turnStrip.opening")
                  : t("adventure.turn", { number: selectedFrame.turnNumber })}
              </strong>
              {selectedFrame.userInput && <p>{selectedFrame.userInput}</p>}
              <p>{selectedFrame.narrative}</p>
            </>
          )
        }
      />

      <AdventureImagePromptModal
        isOpen={promptModalOpen}
        prompt={activeRun.current_image_prompt}
        onClose={() => setPromptModalOpen(false)}
        onSubmit={(options) => {
          setPromptModalOpen(false);
          void regenerateImage(options);
        }}
      />
    </MainLayout>
  );
}

export default function AdventureScreen() {
  const location = useLocation();
  const runId = location.pathname.split("/")[2];
  return runId ? <AdventurePlay runId={runId} /> : <AdventureHub />;
}
