import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import type { AdventurePreset } from "../../apis/adventure";
import { fetchGalleryList, fetchGallerySessions } from "../../apis/gallery";
import { useAdventure } from "../../contexts/AdventureContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useTransparentImage } from "../../hooks/useTransparentImage";
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

const LAST_INSTRUCTION_PREVIEW_LEN = 24;

const PORTRAIT_ALPHA_OPTIONS = { threshold: 12, featherRadius: 1.8 };

function formatSessionDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(locale.startsWith("en") ? "en-US" : "ja-JP", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

function truncateText(text: string, maxLen: number): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, maxLen)}…`;
}

function formatSourceSessionOption(
  session: GallerySession,
  t: (key: string, options?: Record<string, string | number>) => string,
  locale: string,
): string {
  const name = session.character_name ?? t("adventure.unnamedCharacter");
  const date = formatSessionDate(session.first_timestamp, locale);
  const unit = t("gallery.itemsUnit");
  const preview = session.last_instruction
    ? truncateText(session.last_instruction, LAST_INSTRUCTION_PREVIEW_LEN)
    : "";
  if (preview) {
    return t("adventure.sourceSessionOption", {
      name,
      count: session.item_count,
      unit,
      date,
      preview,
    });
  }
  return t("adventure.sourceSessionOptionNoPreview", {
    name,
    count: session.item_count,
    unit,
    date,
  });
}

function AdventureHub() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const replayRunId = (useLocation().state as { replayRunId?: string } | null)
    ?.replayRunId;
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
  const { state: settingsState } = useSettings();
  // 精密参照は既定OFF。ユーザーが明示的にONした場合のみAnlas追加消費
  const [usePreciseReference, setUsePreciseReference] = useState(false);
  // グローバル設定を初期値とし、作成フォームで上書き可能
  const [enableCompositeScene, setEnableCompositeScene] = useState(
    settingsState.adventureEnableCompositeScene,
  );

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
    if (!replayRunId) return;
    setStartMode("authored");
    setSelectedReplayRunId(replayRunId);
  }, [replayRunId]);

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
        use_precise_reference: usePreciseReference,
        enable_composite_scene: enableCompositeScene,
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
                  {formatSourceSessionOption(session, t, i18n.language)}
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
                  <span className="adventure-source-grid__thumb">
                    <img
                      src={mediaUrl(selectedSession.thumbnail_url)}
                      alt={t("adventure.currentState")}
                    />
                  </span>
                  <span className="adventure-source-grid__label">
                    {t("adventure.currentState")}
                  </span>
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
                    <span className="adventure-source-grid__thumb">
                      <img
                        src={mediaUrl(item.image_url)}
                        alt={item.instruction}
                      />
                    </span>
                    <span className="adventure-source-grid__label">
                      {item.instruction}
                    </span>
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

          <details className="adventure-setup-details-wrapper">
            <summary>{t("adventure.imageGenOptions")}</summary>
            <div className="adventure-setup-details adventure-image-gen-options">
              <label className="adventure-precise-toggle">
                <input
                  type="checkbox"
                  checked={usePreciseReference}
                  disabled={setupGenerating || loading || creating}
                  onChange={(event) =>
                    setUsePreciseReference(event.target.checked)
                  }
                />
                <span>
                  <strong>{t("adventure.preciseReference")}</strong>
                  <small>{t("adventure.preciseReferenceHint")}</small>
                </span>
              </label>
              <label className="adventure-precise-toggle">
                <input
                  type="checkbox"
                  checked={enableCompositeScene}
                  disabled={setupGenerating || loading || creating}
                  onChange={(event) =>
                    setEnableCompositeScene(event.target.checked)
                  }
                />
                <span>
                  <strong>{t("adventure.enableCompositeScene")}</strong>
                  <small>{t("adventure.enableCompositeSceneHint")}</small>
                </span>
              </label>
            </div>
          </details>

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
  location: string | null;
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
    regenerateChoices,
    updateSettings,
    clearError,
  } = useAdventure();
  const [input, setInput] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const turnStripEndRef = useRef<HTMLDivElement>(null);
  const messageTextRef = useRef<HTMLDivElement>(null);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number | null>(
    null,
  );
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [imageSettingsOpen, setImageSettingsOpen] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [freeInputOpen, setFreeInputOpen] = useState(false);
  const [messageWindowHidden, setMessageWindowHidden] = useState(false);
  const [hudPanel, setHudPanel] = useState<"milestones" | "clues" | null>(null);
  const [resultDismissed, setResultDismissed] = useState(false);

  useEffect(() => {
    void loadRun(runId).catch(() => navigate("/adventure"));
  }, [loadRun, navigate, runId]);

  useEffect(() => {
    if (!logOpen) return;
    transcriptEndRef.current?.scrollIntoView({ block: "end" });
  }, [logOpen]);

  useEffect(() => {
    if (!streamingNarrative) return;
    const node = messageTextRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [streamingNarrative]);

  const frames = useMemo<AdventureStageFrame[]>(() => {
    if (!activeRun) return [];
    const list: AdventureStageFrame[] = [];
    if (activeRun.enable_composite_scene) {
      if (activeRun.opening_image_url) {
        list.push({
          key: "opening",
          turnNumber: 0,
          imageUrl: activeRun.opening_image_url,
          userInput: null,
          narrative: activeRun.opening_narrative,
          location: null,
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
          location: turn.location,
        });
      }
    } else {
      if (activeRun.opening_portrait_url) {
        list.push({
          key: "opening",
          turnNumber: 0,
          imageUrl: activeRun.opening_portrait_url,
          userInput: null,
          narrative: activeRun.opening_narrative,
          location: null,
        });
      }
      for (const turn of activeRun.turns) {
        if (!turn.portrait_image_url) continue;
        list.push({
          key: turn.id,
          turnNumber: turn.turn_number,
          imageUrl: turn.portrait_image_url,
          userInput: turn.user_input,
          narrative: turn.narrative,
          location: turn.location,
        });
      }
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

  const submit = useCallback(
    (value: string, kind: "choice" | "free_text") => {
      const trimmed = value.trim();
      if (!trimmed || streaming || activeRun?.status !== "active") return;
      setInput("");
      void submitTurn(trimmed, kind);
    },
    [activeRun?.status, streaming, submitTurn],
  );

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select")) return;
      if (event.key === "Escape") {
        setLogOpen(false);
        setImageSettingsOpen(false);
        setHudPanel(null);
        setMessageWindowHidden(false);
        return;
      }
      if (event.key === "l" || event.key === "L") {
        setLogOpen((current) => !current);
        return;
      }
      if (event.key === "h" || event.key === "H") {
        setMessageWindowHidden((current) => !current);
        return;
      }
      if (logOpen) return;
      const choice = (activeRun?.choices ?? []).filter((item) =>
        item.label.trim(),
      )[Number(event.key) - 1];
      if (choice) submit(choice.label, "choice");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [activeRun?.choices, logOpen, submit]);

  const portraitSource = useMemo(() => {
    if (!activeRun || activeRun.enable_composite_scene) return null;
    if (selectedFrameIndex !== null) {
      return (
        frames[selectedFrameIndex]?.imageUrl ?? activeRun.portrait_image_url
      );
    }
    return activeRun.portrait_image_url ?? activeRun.opening_portrait_url;
  }, [activeRun, frames, selectedFrameIndex]);
  // 生成画像の白背景はわずかに灰色に振れるため、既定より広めの許容差で抜く。
  const { url: transparentPortraitUrl } = useTransparentImage(
    portraitSource,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const { url: transparentResultUrl } = useTransparentImage(
    activeRun?.enable_composite_scene ? null : activeRun?.portrait_image_url,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );

  if (loading || !activeRun || activeRun.id !== runId) {
    return (
      <MainLayout>
        <div className="adventure-loading">{t("adventure.loading")}</div>
      </MainLayout>
    );
  }

  const isStageLoading = streaming && phase !== null;
  const isViewingPast = selectedFrameIndex !== null;
  const isCompositeMode = activeRun.enable_composite_scene;
  const effectiveIndex =
    selectedFrameIndex ?? (frames.length > 0 ? frames.length - 1 : -1);
  const selectedFrame =
    effectiveIndex >= 0 ? frames[effectiveIndex] : undefined;
  const backgroundUrl =
    activeRun.background_image_url ?? activeRun.current_image_url;
  const displayedImageUrl = isCompositeMode
    ? isViewingPast
      ? (selectedFrame?.imageUrl ?? activeRun.current_image_url)
      : activeRun.current_image_url
    : backgroundUrl;
  const displayedPortraitUrl = transparentPortraitUrl;

  const goToFrame = (index: number) => {
    if (index < 0 || index >= frames.length) return;
    setSelectedFrameIndex(index === frames.length - 1 ? null : index);
  };

  const latestTurn = activeRun.turns.at(-1) ?? null;
  const isStreamingNarrative = pendingUserInput !== null;
  const activeNarrative = isStreamingNarrative
    ? streamingNarrative
    : isViewingPast
      ? (selectedFrame?.narrative ?? activeRun.opening_narrative)
      : (latestTurn?.narrative ?? activeRun.opening_narrative);
  const activeAction = isStreamingNarrative
    ? pendingUserInput
    : isViewingPast
      ? selectedFrame?.userInput
      : latestTurn?.user_input;
  const activeLocation = isViewingPast
    ? selectedFrame?.location
    : (latestTurn?.location ?? activeRun.visual_state?.location);
  const availableChoices = activeRun.choices.filter(
    (choice) => choice.label.trim().length > 0,
  );
  const completedMilestones = new Set(activeRun.completed_milestones);
  const cast = activeRun.visual_state?.main_characters ?? [];
  const resultImageUrl = isCompositeMode
    ? (activeRun.current_image_url ?? activeRun.portrait_image_url)
    : (transparentResultUrl ?? activeRun.current_image_url);
  const turnRatio =
    activeRun.max_turns > 0
      ? Math.round((activeRun.remaining_turns / activeRun.max_turns) * 100)
      : 0;

  return (
    <MainLayout>
      <div className="adventure-play">
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
          <div className="adventure-hud">
            <button
              type="button"
              className="adventure-hud__back"
              onClick={() => navigate("/adventure")}
              aria-label={t("adventure.back")}
            >
              ←
            </button>
            <div className="adventure-hud__title">
              <p>{activeRun.title}</p>
              <h1 title={activeRun.objective}>
                <span>{t("adventure.goal")}</span>
                {activeRun.objective}
              </h1>
            </div>
            {activeLocation && (
              <span className="adventure-hud__location" title={activeLocation}>
                <b>{t("adventure.currentLocation")}</b>
                {activeLocation}
              </span>
            )}
            <div className="adventure-hud__metrics">
              <div
                className="adventure-hud__turns"
                title={t("adventure.remaining")}
              >
                <span>{t("adventure.remaining")}</span>
                <strong>
                  {activeRun.remaining_turns}
                  <i>/{activeRun.max_turns}</i>
                </strong>
                <span className="adventure-hud__gauge" aria-hidden>
                  <i style={{ width: `${turnRatio}%` }} />
                </span>
              </div>
              {activeRun.milestones.length > 0 && (
                <button
                  type="button"
                  className={`adventure-hud__chip${hudPanel === "milestones" ? " is-open" : ""}`}
                  aria-expanded={hudPanel === "milestones"}
                  onClick={() =>
                    setHudPanel((current) =>
                      current === "milestones" ? null : "milestones",
                    )
                  }
                >
                  <span>{t("adventure.milestones")}</span>
                  <strong>
                    {completedMilestones.size}
                    <i>/{activeRun.milestones.length}</i>
                  </strong>
                </button>
              )}
              <button
                type="button"
                className={`adventure-hud__chip${hudPanel === "clues" ? " is-open" : ""}`}
                aria-expanded={hudPanel === "clues"}
                disabled={activeRun.clues.length === 0}
                onClick={() =>
                  setHudPanel((current) =>
                    current === "clues" ? null : "clues",
                  )
                }
              >
                <span>{t("adventure.clues")}</span>
                <strong>{activeRun.clues.length}</strong>
              </button>
            </div>
            {hudPanel && (
              <div
                className="adventure-hud__popover"
                role="dialog"
                aria-label={t(`adventure.${hudPanel}`)}
              >
                {hudPanel === "milestones" ? (
                  <ul className="adventure-hud__milestones">
                    {activeRun.milestones.map((milestone) => {
                      const done = completedMilestones.has(milestone.id);
                      return (
                        <li
                          key={milestone.id}
                          className={done ? "is-done" : ""}
                        >
                          <span aria-hidden>{done ? "✓" : "・"}</span>
                          {milestone.label}
                          {done && <em>{t("adventure.milestoneDone")}</em>}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <ul className="adventure-hud__clues">
                    {activeRun.clues.map((clue) => (
                      <li key={clue}>{clue}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {cast.length > 0 && (
            <ul className="adventure-cast" aria-label={t("adventure.cast")}>
              {cast.map((member) => (
                <li key={member.name}>
                  <strong>{member.name}</strong>
                  {member.action && <span>{member.action}</span>}
                </li>
              ))}
            </ul>
          )}
          <section className="adventure-stage" aria-busy={isStageLoading}>
            <div
              className={`adventure-stage__frame ${isCompositeMode ? "is-composite" : "is-background"}`}
            >
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
              <div className="adventure-stage__scrim" aria-hidden />
              {displayedPortraitUrl && (
                <img
                  key={displayedPortraitUrl}
                  className="adventure-stage__portrait"
                  src={displayedPortraitUrl}
                  alt={t("adventure.portraitAlt")}
                />
              )}
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
              <button
                type="button"
                className="adventure-stage__settings"
                onClick={() => setImageSettingsOpen((current) => !current)}
                title={t("adventure.imageSettings")}
                aria-label={t("adventure.imageSettings")}
                aria-expanded={imageSettingsOpen}
              >
                ⚙
              </button>
              {imageSettingsOpen && (
                <div className="adventure-image-settings-popover">
                  <label className="adventure-precise-toggle">
                    <input
                      type="checkbox"
                      checked={activeRun.use_precise_reference}
                      disabled={streaming || settingsSaving}
                      onChange={(event) => {
                        const next = event.target.checked;
                        setSettingsSaving(true);
                        void updateSettings({
                          use_precise_reference: next,
                          enable_composite_scene:
                            activeRun.enable_composite_scene,
                        })
                          .catch(() => undefined)
                          .finally(() => setSettingsSaving(false));
                      }}
                    />
                    <span>
                      <strong>{t("adventure.preciseReference")}</strong>
                      <small>{t("adventure.preciseReferencePlayHint")}</small>
                    </span>
                  </label>
                  <label className="adventure-precise-toggle">
                    <input
                      type="checkbox"
                      checked={activeRun.enable_composite_scene}
                      disabled={streaming || settingsSaving}
                      onChange={(event) => {
                        const next = event.target.checked;
                        setSettingsSaving(true);
                        void updateSettings({
                          use_precise_reference:
                            activeRun.use_precise_reference,
                          enable_composite_scene: next,
                        })
                          .catch(() => undefined)
                          .finally(() => setSettingsSaving(false));
                      }}
                    />
                    <span>
                      <strong>{t("adventure.enableCompositeScene")}</strong>
                      <small>
                        {t("adventure.enableCompositeScenePlayHint")}
                      </small>
                    </span>
                  </label>
                </div>
              )}
            </div>
          </section>

          {messageWindowHidden && (
            <button
              type="button"
              className="adventure-window-restore"
              onClick={() => setMessageWindowHidden(false)}
              title={t("adventure.window.showHint")}
            >
              {t("adventure.window.show")}
            </button>
          )}

          <section
            className={`adventure-messagebox${
              messageWindowHidden ? " is-hidden" : ""
            }`}
            aria-live="polite"
            aria-hidden={messageWindowHidden}
          >
            <div className="adventure-messagebox__meta">
              <button
                type="button"
                className="adventure-messagebox__log-button"
                onClick={() => setLogOpen(true)}
                title={t("adventure.log.openHint")}
              >
                {t("adventure.log.open")}
              </button>
              <button
                type="button"
                className="adventure-messagebox__hide-button"
                onClick={() => setMessageWindowHidden(true)}
                title={t("adventure.window.hideHint")}
                tabIndex={messageWindowHidden ? -1 : undefined}
              >
                {t("adventure.window.hide")}
              </button>
            </div>

            <div className="adventure-messagebox__text" ref={messageTextRef}>
              {activeAction && (
                <p className="adventure-messagebox__action">
                  <span>{t("adventure.yourAction")}</span>
                  {activeAction}
                </p>
              )}
              <p className="adventure-messagebox__narrative">
                {activeNarrative}
                {isStreamingNarrative && (
                  <span className="adventure-transcript__caret" />
                )}
              </p>
              {streaming && !isStageLoading && (
                <div className="adventure-progress">
                  <span />
                  {t(`adventure.phase.${phase ?? "narrative"}`)}
                </div>
              )}
            </div>

            {activeRun.status === "active" ? (
              <div className="adventure-controls">
                <div className="adventure-choices">
                  {availableChoices.map((choice, index) => (
                    <button
                      type="button"
                      key={choice.id}
                      disabled={streaming}
                      onClick={() => submit(choice.label, "choice")}
                    >
                      <span className="adventure-choices__key">
                        {index + 1}
                      </span>
                      {choice.label}
                    </button>
                  ))}
                </div>
                {availableChoices.length === 0 && (
                  <p className="adventure-choices__empty">
                    {t("adventure.emptyChoices")}
                  </p>
                )}
                <div className="adventure-controls__actions">
                  <button
                    type="button"
                    className="adventure-choices__regenerate"
                    onClick={() => void regenerateChoices()}
                    disabled={streaming}
                    title={t("adventure.regenerateChoices")}
                  >
                    {streaming && phase === "clue_check"
                      ? t("adventure.regeneratingChoices")
                      : t("adventure.regenerateChoices")}
                  </button>
                  <button
                    type="button"
                    className="adventure-controls__free-toggle"
                    onClick={() => setFreeInputOpen((current) => !current)}
                    aria-expanded={freeInputOpen}
                  >
                    {t("adventure.freeInputToggle")}
                  </button>
                </div>
                {freeInputOpen && (
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
                )}
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

      {activeRun.status !== "active" && !resultDismissed && (
        <div className={`adventure-result is-${activeRun.status}`}>
          <div
            className="adventure-result__card"
            role="dialog"
            aria-modal="true"
            aria-label={activeRun.ending_title ?? activeRun.title}
          >
            {resultImageUrl && (
              <img
                className="adventure-result__image"
                src={resultImageUrl}
                alt={t("adventure.portraitAlt")}
              />
            )}
            <div className="adventure-result__body">
              <span className="adventure-result__badge">
                {t(`adventure.status.${activeRun.status}`)}
              </span>
              <h2>{activeRun.ending_title ?? activeRun.title}</h2>
              <p className="adventure-result__summary">
                {activeRun.ending_summary}
              </p>
              <dl className="adventure-result__stats">
                <div>
                  <dt>{t("adventure.result.turns")}</dt>
                  <dd>
                    {activeRun.turn_count}
                    <i>/{activeRun.max_turns}</i>
                  </dd>
                </div>
                <div>
                  <dt>{t("adventure.milestones")}</dt>
                  <dd>
                    {completedMilestones.size}
                    <i>/{activeRun.milestones.length}</i>
                  </dd>
                </div>
                <div>
                  <dt>{t("adventure.clues")}</dt>
                  <dd>{activeRun.clues.length}</dd>
                </div>
              </dl>
              {activeRun.milestones.length > 0 && (
                <ul className="adventure-result__milestones">
                  {activeRun.milestones.map((milestone) => {
                    const done = completedMilestones.has(milestone.id);
                    return (
                      <li key={milestone.id} className={done ? "is-done" : ""}>
                        <span aria-hidden>{done ? "✓" : "・"}</span>
                        {milestone.label}
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="adventure-result__actions">
                <button
                  type="button"
                  onClick={() => {
                    setResultDismissed(true);
                    setLogOpen(true);
                  }}
                >
                  {t("adventure.result.readLog")}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    navigate("/adventure", {
                      state: { replayRunId: activeRun.id },
                    })
                  }
                >
                  {t("adventure.result.replay")}
                </button>
                <button type="button" onClick={() => navigate("/adventure")}>
                  {t("adventure.result.backToHub")}
                </button>
              </div>
              <button
                type="button"
                className="adventure-result__close"
                onClick={() => setResultDismissed(true)}
              >
                {t("adventure.result.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {logOpen && (
        <div className="adventure-log">
          <button
            type="button"
            className="adventure-log__backdrop"
            aria-label={t("adventure.log.close")}
            onClick={() => setLogOpen(false)}
          />
          <aside
            className="adventure-log__panel"
            role="dialog"
            aria-modal="true"
            aria-label={t("adventure.log.title")}
          >
            <header className="adventure-log__header">
              <h2>{t("adventure.log.title")}</h2>
              <button
                type="button"
                onClick={() => setLogOpen(false)}
                aria-label={t("adventure.log.close")}
              >
                ×
              </button>
            </header>
            <div className="adventure-log__body">
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
              </div>
              <div ref={transcriptEndRef} />
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
                      onClick={() => {
                        goToFrame(index);
                        setLogOpen(false);
                      }}
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
          </aside>
        </div>
      )}

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
