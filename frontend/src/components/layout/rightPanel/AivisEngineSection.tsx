import { useTranslation } from "react-i18next";
import { useAivisEngine } from "../../../hooks/useAivisEngine";

/** 音声合成エンジンの起動・停止(TTS 有効時のみ表示) */
export default function AivisEngineSection() {
  const { t } = useTranslation();
  const { status, ready, busy, toggle } = useAivisEngine();
  return (
    <section className="right-panel__section right-panel__aivis-engine">
      <h4 className="right-panel__section-title">
        {t("rightPanel.aivisEngineTitle")}
      </h4>
      <div className="right-panel__aivis-engine-row">
        <span
          className={`right-panel__aivis-engine-status right-panel__aivis-engine-status--${
            ready ? "running" : "stopped"
          }`}
        >
          {ready
            ? t("rightPanel.aivisEngineRunning")
            : t("rightPanel.aivisEngineStopped")}
        </span>
        {status?.platform === "linux" ? (
          <span className="right-panel__aivis-engine-hint">
            {t("rightPanel.aivisEngineDockerManaged", {
              command: status.docker_hint ?? "docker compose up -d aivis",
            })}
          </span>
        ) : (
          <button
            type="button"
            className="right-panel__aivis-engine-btn"
            disabled={busy}
            onClick={() => void toggle()}
          >
            {ready
              ? t("rightPanel.aivisEngineStop")
              : t("rightPanel.aivisEngineStart")}
          </button>
        )}
      </div>
    </section>
  );
}
