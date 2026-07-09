/**
 * MemorySettings - Memory feature settings panel section
 *
 * 直近セッションの要約・称号を一括生成し、その結果からユーザーの
 * 好み・性的嗜好をテキスト化して保持するメモリ機能の設定UI。
 */

import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../contexts/SettingsContext";
import {
  getSessionTotalCount,
  saveMemoryText,
  startMemoryGeneration,
} from "../../apis/memory";
import MemoryGenerateConfirmModal from "../MemoryGenerateConfirmModal";
import MemoryGenerationProgressModal from "../MemoryGenerationProgressModal";
import "./MemorySettings.css";

const SESSION_COUNT_OPTIONS = [10, 20, 30, 50, 100] as const;

export default function MemorySettings() {
  const { t } = useTranslation();
  const { memoryText, setMemoryText, loadMemoryText } = useSettings();

  const [sessionCountOption, setSessionCountOption] = useState<string>("30");
  const [regenerateExisting, setRegenerateExisting] = useState(false);
  const [totalSessionCount, setTotalSessionCount] = useState(0);
  const [showConfirm, setShowConfirm] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const [draftText, setDraftText] = useState(memoryText ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    setDraftText(memoryText ?? "");
  }, [memoryText]);

  useEffect(() => {
    getSessionTotalCount()
      .then(setTotalSessionCount)
      .catch(() => setTotalSessionCount(0));
  }, []);

  const sessionLimit =
    sessionCountOption === "all" ? null : Number(sessionCountOption);
  const targetSessionCount =
    sessionLimit === null
      ? totalSessionCount
      : Math.min(sessionLimit, totalSessionCount);

  const handleGenerateClick = useCallback(() => {
    setStartError(null);
    setShowConfirm(true);
  }, []);

  const handleConfirmStart = useCallback(async () => {
    setShowConfirm(false);
    try {
      const { job_id } = await startMemoryGeneration(
        sessionLimit,
        regenerateExisting,
      );
      setJobId(job_id);
    } catch (err) {
      setStartError(
        err instanceof Error ? err.message : t("settings.memory.startError"),
      );
    }
  }, [sessionLimit, regenerateExisting, t]);

  const handleJobFinished = useCallback(() => {
    void loadMemoryText();
  }, [loadMemoryText]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setSaveError(null);
    setSuccessMessage(null);
    try {
      const saved = await saveMemoryText(draftText);
      setMemoryText(saved);
      setSuccessMessage(t("settings.memory.saved"));
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : t("settings.memory.saveError"),
      );
    } finally {
      setIsSaving(false);
    }
  }, [draftText, setMemoryText, t]);

  return (
    <div className="memory-settings">
      <p className="memory-settings__description">
        {t("settings.memory.description")}
      </p>

      <div className="memory-settings__field">
        <label className="memory-settings__label">
          {t("settings.memory.sessionCountLabel")}
        </label>
        <select
          className="memory-settings__select"
          value={sessionCountOption}
          onChange={(e) => setSessionCountOption(e.target.value)}
        >
          {SESSION_COUNT_OPTIONS.map((count) => (
            <option key={count} value={count}>
              {count}
            </option>
          ))}
          <option value="all">{t("settings.memory.sessionCountAll")}</option>
        </select>
      </div>

      <label className="memory-settings__checkbox">
        <input
          type="checkbox"
          checked={regenerateExisting}
          onChange={(e) => setRegenerateExisting(e.target.checked)}
        />
        {t("settings.memory.regenerateLabel")}
      </label>

      <button
        type="button"
        className="memory-settings__generate-btn"
        onClick={handleGenerateClick}
        disabled={jobId !== null}
      >
        {t("settings.memory.generateButton")}
      </button>

      {startError && <p className="memory-settings__error">{startError}</p>}

      <div className="memory-settings__field">
        <label className="memory-settings__label">
          {t("settings.memory.textAreaLabel")}
        </label>
        <textarea
          className="memory-settings__textarea"
          value={draftText}
          onChange={(e) => setDraftText(e.target.value)}
          placeholder={t("settings.memory.textAreaPlaceholder")}
          rows={6}
        />
        <button
          type="button"
          className="memory-settings__save-btn"
          onClick={handleSave}
          disabled={isSaving}
        >
          {isSaving
            ? t("settings.memory.saving")
            : t("settings.memory.saveButton")}
        </button>
        {successMessage && (
          <p className="memory-settings__success">{successMessage}</p>
        )}
        {saveError && <p className="memory-settings__error">{saveError}</p>}
      </div>

      {showConfirm && (
        <MemoryGenerateConfirmModal
          sessionCount={targetSessionCount}
          regenerateExisting={regenerateExisting}
          onConfirm={handleConfirmStart}
          onCancel={() => setShowConfirm(false)}
        />
      )}

      {jobId && (
        <MemoryGenerationProgressModal
          jobId={jobId}
          onFinished={handleJobFinished}
          onClose={() => setJobId(null)}
        />
      )}
    </div>
  );
}
