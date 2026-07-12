import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import {
  type AivisStatus,
  downloadAivisEngine,
  extractAivisEngine,
  getAivisDefaults,
  getAivisSpeakers,
  getAivisStatus,
  installAivisModel,
  restartAivisEngine,
  startAivisEngine,
  stopAivisEngine,
  type AivisSpeaker,
} from "../../apis/speechSynthesis";
import "./SpeechSynthesisSettings.css";

export default function SpeechSynthesisSettings() {
  const { t } = useTranslation();
  const {
    state,
    setTtsEnabled,
    setTtsUseGpu,
    setTtsEngineDir,
    setTtsSpeakerId,
    setTtsStyleId,
    setTtsOutputFormat,
  } = useSettings();

  const [engineDownloadUrl, setEngineDownloadUrl] = useState("");
  const [speakers, setSpeakers] = useState<AivisSpeaker[]>([]);
  const [statusText, setStatusText] = useState("");
  const [currentAction, setCurrentAction] = useState("");
  const [statusInfo, setStatusInfo] = useState<AivisStatus | null>(null);
  const [setupStage, setSetupStage] = useState("initial");
  const [isModelGuideOpen, setIsModelGuideOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showGpuRestartHint, setShowGpuRestartHint] = useState(false);

  const modelHubUrl =
    "https://hub.aivis-project.com/aivm-models/7fc08a41-b64d-456d-8b22-8e1284674775";
  const targetModelFileName = "zonoko.aivmx";
  const modelPathDisplay = "%APPDATA%/AivisSpeech-Engine/Models";

  const setOperationFailed = useCallback(
    (error: unknown) => {
      const message = String((error as Error).message);
      setStatusText(
        t("settings.speech.operationFailed", {
          message,
        }),
      );
      if (
        message.includes("403") ||
        message.toLowerCase().includes("cloudflare")
      ) {
        setStatusText(t("settings.speech.modelDownloadBlocked"));
      }
      setCurrentAction(t("settings.speech.actionFailed"));
    },
    [t],
  );

  const refreshStatus = useCallback(async () => {
    const status = await getAivisStatus();
    setStatusInfo(status);
    return status;
  }, []);

  const markAction = useCallback(
    (key: string) => {
      setCurrentAction(t(key));
    },
    [t],
  );

  const reconcileSpeakerSelection = useCallback(
    async (result: AivisSpeaker[]) => {
      if (result.length === 0) {
        return;
      }

      const currentSpeaker =
        result.find((item) => item.speaker_uuid === state.ttsSpeakerId) ??
        result[0];

      if (currentSpeaker.speaker_uuid !== state.ttsSpeakerId) {
        await setTtsSpeakerId(currentSpeaker.speaker_uuid);
      }

      const currentStyleExists = currentSpeaker.styles.some(
        (style) => String(style.id) === state.ttsStyleId,
      );
      const fallbackStyle = currentSpeaker.styles[0];

      if (!currentStyleExists && fallbackStyle) {
        await setTtsStyleId(String(fallbackStyle.id));
      }
    },
    [setTtsSpeakerId, setTtsStyleId, state.ttsSpeakerId, state.ttsStyleId],
  );

  const selectedSpeaker = useMemo(
    () =>
      speakers.find((item) => item.speaker_uuid === state.ttsSpeakerId) ?? null,
    [speakers, state.ttsSpeakerId],
  );

  useEffect(() => {
    const loadInitial = async () => {
      try {
        const [defaults, status] = await Promise.all([
          getAivisDefaults(),
          getAivisStatus(),
        ]);
        setEngineDownloadUrl(defaults.engine_download_url);
        setStatusInfo(status);
        setStatusText(
          `${t("settings.speech.status")}: ${status.engine_http} (${status.process})`,
        );
        setCurrentAction(t("settings.speech.actionIdle"));
      } catch (error) {
        setStatusText(
          `${t("settings.speech.statusFailed")}: ${String((error as Error).message)}`,
        );
      }
    };
    void loadInitial();
  }, [t]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void refreshStatus().catch(() => undefined);
    }, 5000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [refreshStatus]);

  useEffect(() => {
    if (!statusInfo || statusInfo.process !== "running") {
      return;
    }
    if (!state.ttsSpeakerId && !state.ttsStyleId) {
      return;
    }

    const syncSpeakers = async () => {
      try {
        const result = await getAivisSpeakers();
        setSpeakers(result);
        await reconcileSpeakerSelection(result);
      } catch {
        // Keep current UI state; manual fetch remains available.
      }
    };

    void syncSpeakers();
  }, [
    reconcileSpeakerSelection,
    state.ttsSpeakerId,
    state.ttsStyleId,
    statusInfo,
  ]);

  const handlePrepareEngine = async () => {
    setBusy(true);
    try {
      const status = await refreshStatus();
      if (status.process === "running" || status.engine_http === "ok") {
        setSetupStage("engine_started");
        setStatusText(t("settings.speech.engineAlreadyReady"));
        setCurrentAction(t("settings.speech.actionIdle"));
        return;
      }

      try {
        markAction("settings.speech.actionStartEngine");
        const started = await startAivisEngine({
          engine_dir: state.ttsEngineDir,
          use_gpu: state.ttsUseGpu,
        });
        setSetupStage("engine_started");
        await refreshStatus();
        setStatusText(
          t("settings.speech.engineStarted", {
            status: started.status,
            pid: started.pid ?? "-",
          }),
        );
        setCurrentAction(t("settings.speech.actionIdle"));
        return;
      } catch {
        // Continue with full preparation when direct start is not available.
      }

      setStatusText(t("settings.speech.preparingStep", { step: 1, total: 3 }));
      markAction("settings.speech.actionDownloadEngine");
      const downloaded = await downloadAivisEngine({
        url: engineDownloadUrl,
        target_dir: state.ttsEngineDir,
      });
      setSetupStage("engine_downloaded");

      setStatusText(t("settings.speech.preparingStep", { step: 2, total: 3 }));
      markAction("settings.speech.actionExtractEngine");
      await extractAivisEngine({
        zip_path: downloaded.path,
        destination_dir: state.ttsEngineDir,
      });
      setSetupStage("engine_extracted");

      setStatusText(t("settings.speech.preparingStep", { step: 3, total: 3 }));
      markAction("settings.speech.actionStartEngine");
      const started = await startAivisEngine({
        engine_dir: state.ttsEngineDir,
        use_gpu: state.ttsUseGpu,
      });
      setSetupStage("engine_started");
      await refreshStatus();

      setStatusText(
        t("settings.speech.prepareDone", {
          pid: started.pid ?? "-",
          path: downloaded.path,
        }),
      );
      setCurrentAction(t("settings.speech.actionIdle"));
    } catch (error) {
      setOperationFailed(error);
    } finally {
      setBusy(false);
    }
  };

  const handleRestartEngine = async () => {
    setBusy(true);
    try {
      markAction("settings.speech.actionRestartEngine");
      const result = await restartAivisEngine({
        engine_dir: state.ttsEngineDir,
        use_gpu: state.ttsUseGpu,
      });
      setSetupStage("engine_started");
      await refreshStatus();
      setStatusText(
        t("settings.speech.engineRestarted", {
          status: result.status,
          pid: result.pid ?? "-",
        }),
      );
      setCurrentAction(t("settings.speech.actionIdle"));
      setShowGpuRestartHint(false);
    } catch (error) {
      setOperationFailed(error);
    } finally {
      setBusy(false);
    }
  };

  const handleStopEngine = async () => {
    setBusy(true);
    try {
      markAction("settings.speech.actionStopEngine");
      const result = await stopAivisEngine();
      setSetupStage("engine_extracted");
      await refreshStatus();
      setStatusText(
        t("settings.speech.engineStopped", {
          status: result.status,
          pid: result.pid ?? "-",
        }),
      );
      setCurrentAction(t("settings.speech.actionIdle"));
    } catch (error) {
      setOperationFailed(error);
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadModel = async () => {
    markAction("settings.speech.actionDownloadModel");
    setIsModelGuideOpen(true);
    setStatusText(t("settings.speech.modelGuideOpened"));
    setCurrentAction(t("settings.speech.actionIdle"));
  };

  const handleConfirmModelPlaced = async () => {
    setBusy(true);
    try {
      markAction("settings.speech.actionInstallModel");
      await installAivisModel({ model_path: state.ttsModelDir });
      setSetupStage("model_installed");
      setStatusText(t("settings.speech.modelInstalled"));
      setCurrentAction(t("settings.speech.actionIdle"));
      setIsModelGuideOpen(false);
    } catch (error) {
      setOperationFailed(error);
    } finally {
      setBusy(false);
    }
  };

  const handleFetchSpeakers = async () => {
    setBusy(true);
    try {
      markAction("settings.speech.actionFetchSpeakers");
      const result = await getAivisSpeakers();
      setSpeakers(result);
      await reconcileSpeakerSelection(result);
      setSetupStage("speakers_ready");
      setStatusText(
        t("settings.speech.speakersFetched", { count: result.length }),
      );
      setCurrentAction(t("settings.speech.actionIdle"));
    } catch (error) {
      setOperationFailed(error);
    } finally {
      setBusy(false);
    }
  };

  const engineReady =
    statusInfo?.engine_http === "ok" || statusInfo?.process === "running";
  const hasError = currentAction === t("settings.speech.actionFailed");

  let bannerVariant: "busy" | "error" | "ready" | "idle" = "idle";
  if (busy) {
    bannerVariant = "busy";
  } else if (hasError) {
    bannerVariant = "error";
  } else if (engineReady) {
    bannerVariant = "ready";
  }

  const bannerTitle =
    bannerVariant === "busy"
      ? t("settings.speech.statusBusy")
      : bannerVariant === "error"
        ? t("settings.speech.statusError")
        : bannerVariant === "ready"
          ? t("settings.speech.statusReady")
          : t("settings.speech.statusIdle");

  const bannerSubtitle = busy
    ? currentAction || t("settings.speech.statusBusy")
    : statusText || t("settings.speech.statusIdleDesc");

  return (
    <div className="speech-settings">
      <div className="settings-screen__item">
        <div className="speech-settings__guide speech-settings__guide--section">
          <p className="speech-settings__guide-title">
            {t("settings.speech.section1Title")}
          </p>

          <div className="settings-screen__item">
            <label className="settings-screen__toggle">
              <div className="settings-screen__toggle-info">
                <span className="settings-screen__item-label">
                  {t("settings.speech.enable")}
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.speech.enableDesc")}
                </span>
              </div>
              <input
                type="checkbox"
                checked={state.ttsEnabled}
                onChange={(e) => void setTtsEnabled(e.target.checked)}
                className="settings-screen__toggle-input"
              />
              <span className="settings-screen__toggle-switch" />
            </label>
          </div>

          <div className="settings-screen__item">
            <label className="settings-screen__toggle">
              <div className="settings-screen__toggle-info">
                <span className="settings-screen__item-label">
                  {t("settings.speech.useGpu")}
                </span>
                <span className="settings-screen__item-desc">
                  {t("settings.speech.useGpuDesc")}
                </span>
              </div>
              <input
                type="checkbox"
                checked={state.ttsUseGpu}
                onChange={(e) => {
                  void setTtsUseGpu(e.target.checked);
                  setShowGpuRestartHint(true);
                }}
                className="settings-screen__toggle-input"
              />
              <span className="settings-screen__toggle-switch" />
            </label>
          </div>

          {showGpuRestartHint && (
            <div className="speech-settings__restart-hint">
              <span>{t("settings.speech.gpuRestartHint")}</span>
              <button
                className="speech-settings__button"
                type="button"
                disabled={busy}
                onClick={() => void handleRestartEngine()}
              >
                {t("settings.speech.restartEngine")}
              </button>
            </div>
          )}

          <div className="settings-screen__item">
            <div className="settings-screen__item-header">
              <span className="settings-screen__item-label">
                {t("settings.speech.engineDir")}
              </span>
            </div>
            <input
              className="speech-settings__input"
              type="text"
              value={state.ttsEngineDir}
              onChange={(e) => void setTtsEngineDir(e.target.value)}
            />
          </div>

          <button
            className="speech-settings__button speech-settings__button--primary speech-settings__button--block"
            type="button"
            disabled={busy}
            onClick={() => void handlePrepareEngine()}
          >
            {busy ? (
              <span className="speech-settings__button-loading">
                <span
                  className="speech-settings__spinner speech-settings__spinner--sm"
                  aria-hidden="true"
                />
                {t("settings.speech.processing")}
              </span>
            ) : (
              t("settings.speech.runEnginePreparation")
            )}
          </button>

          <div className="speech-settings__engine-controls">
            <span className="speech-settings__controls-label">
              {t("settings.speech.engineControlsLabel")}
            </span>
            <div className="speech-settings__button-group">
              <button
                className="speech-settings__button"
                type="button"
                disabled={busy}
                onClick={() => void handleRestartEngine()}
              >
                {t("settings.speech.restartEngine")}
              </button>
              <button
                className="speech-settings__button"
                type="button"
                disabled={busy}
                onClick={() => void handleStopEngine()}
              >
                {t("settings.speech.stopEngine")}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-screen__item">
        <div
          className={`speech-settings__banner speech-settings__banner--${bannerVariant}`}
          role="status"
          aria-live="polite"
        >
          <span
            className="speech-settings__banner-indicator"
            aria-hidden="true"
          >
            {busy ? (
              <span className="speech-settings__spinner" />
            ) : (
              <span className="speech-settings__banner-dot" />
            )}
          </span>
          <span className="speech-settings__banner-body">
            <span className="speech-settings__banner-title">{bannerTitle}</span>
            <span className="speech-settings__banner-sub">
              {bannerSubtitle}
            </span>
          </span>
        </div>

        <details className="speech-settings__details">
          <summary className="speech-settings__details-summary">
            {t("settings.speech.detailsSummary")}
          </summary>
          <div className="speech-settings__status-card">
            <div className="speech-settings__status-row">
              <span>{t("settings.speech.setupStageLabel")}</span>
              <strong>{t(`settings.speech.stage.${setupStage}`)}</strong>
            </div>
            <div className="speech-settings__status-row">
              <span>{t("settings.speech.engineProcessLabel")}</span>
              <strong>{statusInfo?.process ?? "-"}</strong>
            </div>
            <div className="speech-settings__status-row">
              <span>{t("settings.speech.engineHttpLabel")}</span>
              <strong>{statusInfo?.engine_http ?? "-"}</strong>
            </div>
            <div className="speech-settings__status-row">
              <span>{t("settings.speech.enginePidLabel")}</span>
              <strong>{statusInfo?.pid ?? "-"}</strong>
            </div>
            <div className="speech-settings__status-row">
              <span>{t("settings.speech.engineManagedLabel")}</span>
              <strong>
                {statusInfo?.managed == null
                  ? "-"
                  : statusInfo.managed
                    ? t("settings.speech.engineManagedYes")
                    : t("settings.speech.engineManagedNo")}
              </strong>
            </div>
          </div>
        </details>
      </div>

      <div className="settings-screen__item">
        <div className="speech-settings__guide speech-settings__guide--section">
          <p className="speech-settings__guide-title">
            {t("settings.speech.section2Title")}
          </p>
          <button
            className="speech-settings__button"
            type="button"
            disabled={busy}
            onClick={() => void handleDownloadModel()}
          >
            {t("settings.speech.downloadModel")}
          </button>
          <p className="speech-settings__modal-text">
            {t("settings.speech.modelPlacementHint", {
              path: modelPathDisplay,
            })}
          </p>
          <button
            className="speech-settings__button speech-settings__button--primary"
            type="button"
            disabled={busy}
            onClick={() => void handleConfirmModelPlaced()}
          >
            {busy ? (
              <span className="speech-settings__button-loading">
                <span
                  className="speech-settings__spinner speech-settings__spinner--sm"
                  aria-hidden="true"
                />
                {t("settings.speech.processing")}
              </span>
            ) : (
              t("settings.speech.installModel")
            )}
          </button>
        </div>
      </div>

      <div className="settings-screen__item">
        <div className="speech-settings__guide speech-settings__guide--section">
          <p className="speech-settings__guide-title">
            {t("settings.speech.section3Title")}
          </p>
          <div className="speech-settings__button-group">
            <button
              className="speech-settings__button"
              type="button"
              disabled={busy}
              onClick={() => void handleFetchSpeakers()}
            >
              {busy ? (
                <span className="speech-settings__button-loading">
                  <span
                    className="speech-settings__spinner speech-settings__spinner--sm"
                    aria-hidden="true"
                  />
                  {t("settings.speech.processing")}
                </span>
              ) : (
                t("settings.speech.fetchSpeakers")
              )}
            </button>
          </div>
        </div>
      </div>

      {isModelGuideOpen && (
        <div
          className="speech-settings__modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="speech-model-guide-title"
        >
          <div className="speech-settings__modal">
            <h3
              id="speech-model-guide-title"
              className="speech-settings__modal-title"
            >
              {t("settings.speech.modelGuideTitle")}
            </h3>

            <p className="speech-settings__modal-text">
              {t("settings.speech.modelGuideIntro")}
            </p>
            <p className="speech-settings__modal-code">{modelHubUrl}</p>

            <p className="speech-settings__modal-text">
              {t("settings.speech.modelGuideTargetFile", {
                fileName: targetModelFileName,
              })}
            </p>

            <p className="speech-settings__modal-text">
              {t("settings.speech.modelGuideFolderIntro")}
            </p>
            <p className="speech-settings__modal-code">
              %APPDATA%/AivisSpeech-Engine/Models
            </p>

            <p className="speech-settings__modal-text">
              {t("settings.speech.modelGuidePlaceFile", {
                fileName: targetModelFileName,
              })}
            </p>

            <div className="speech-settings__modal-actions">
              <button
                className="speech-settings__button"
                type="button"
                onClick={() =>
                  window.open(modelHubUrl, "_blank", "noopener,noreferrer")
                }
              >
                {t("settings.speech.openModelUrl")}
              </button>
              <button
                className="speech-settings__button"
                type="button"
                onClick={() => {
                  setIsModelGuideOpen(false);
                  setStatusText(
                    t("settings.speech.modelGuideClosedReadyInstall", {
                      fileName: targetModelFileName,
                    }),
                  );
                }}
              >
                {t("common.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.speech.speaker")}
          </span>
        </div>
        <div className="settings-screen__select-wrapper">
          <select
            className="settings-screen__select"
            value={state.ttsSpeakerId ?? ""}
            onChange={(e) => void setTtsSpeakerId(e.target.value || null)}
          >
            <option value="">{t("settings.speech.notSelected")}</option>
            {speakers.map((speaker) => (
              <option key={speaker.speaker_uuid} value={speaker.speaker_uuid}>
                {speaker.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.speech.style")}
          </span>
        </div>
        <div className="settings-screen__select-wrapper">
          <select
            className="settings-screen__select"
            value={state.ttsStyleId ?? ""}
            onChange={(e) => void setTtsStyleId(e.target.value || null)}
          >
            <option value="">{t("settings.speech.notSelected")}</option>
            {(selectedSpeaker?.styles ?? []).map((style) => (
              <option key={style.id} value={String(style.id)}>
                {style.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.speech.outputFormat")}
          </span>
        </div>
        <div className="settings-screen__select-wrapper">
          <select
            className="settings-screen__select"
            value={state.ttsOutputFormat}
            onChange={(e) => void setTtsOutputFormat(e.target.value as "wav")}
          >
            <option value="wav">WAV</option>
          </select>
        </div>
      </div>

      <p className="speech-settings__status">{statusText}</p>
    </div>
  );
}
