/**
 * Memory Generation Progress Modal Component
 *
 * メモリ生成バッチジョブの進捗をポーリングして可視化するモーダル。
 * 完了/失敗/キャンセル完了時に onFinished を呼び出す。
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  cancelMemoryGeneration,
  getMemoryGenerationStatus,
  type MemoryJobStatus,
} from "../apis/memory";
import "./MemoryGenerationProgressModal.css";

const POLL_INTERVAL_MS = 2000;

interface MemoryGenerationProgressModalProps {
  jobId: string;
  onFinished: (status: MemoryJobStatus) => void;
  onClose: () => void;
}

const TERMINAL_STATUSES = new Set([
  "completed",
  "completed_with_errors",
  "failed",
  "cancelled",
]);

export default function MemoryGenerationProgressModal({
  jobId,
  onFinished,
  onClose,
}: MemoryGenerationProgressModalProps) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<MemoryJobStatus | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const result = await getMemoryGenerationStatus(jobId);
        if (cancelled) return;
        setStatus(result);
        if (TERMINAL_STATUSES.has(result.status)) {
          onFinishedRef.current(result);
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
          }
        }
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : t("settings.memory.statusFetchError"),
        );
      }
    };

    void poll();
    intervalId = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      await cancelMemoryGeneration(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [jobId]);

  const total = status?.total ?? 0;
  const processed = status?.processed ?? 0;
  const percent =
    total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  const isTerminal = status ? TERMINAL_STATUSES.has(status.status) : false;

  return (
    <div className="memory-progress-overlay">
      <div className="memory-progress-modal">
        <h2>{t("settings.memory.progressTitle")}</h2>

        <div className="memory-progress-bar-track">
          <div
            className="memory-progress-bar-fill"
            style={{ width: `${percent}%` }}
          />
        </div>

        <p className="memory-progress-status">
          {t("settings.memory.progressStatus", { processed, total })}
        </p>

        {status?.current_session_id && !isTerminal && (
          <p className="memory-progress-current">
            {t("settings.memory.progressCurrent", {
              sessionId: status.current_session_id,
            })}
          </p>
        )}

        {isTerminal && status && (
          <p
            className={`memory-progress-final memory-progress-final--${status.status}`}
          >
            {status.status === "completed" &&
              t("settings.memory.statusCompleted")}
            {status.status === "completed_with_errors" &&
              t("settings.memory.statusCompletedWithErrors")}
            {status.status === "failed" && t("settings.memory.statusFailed")}
            {status.status === "cancelled" &&
              t("settings.memory.statusCancelled")}
          </p>
        )}

        {error && <p className="memory-progress-error">{error}</p>}

        {!isTerminal && (
          <button
            type="button"
            className="memory-progress-cancel"
            onClick={handleCancel}
            disabled={isCancelling}
          >
            {isCancelling
              ? t("settings.memory.progressCancelling")
              : t("settings.memory.progressCancel")}
          </button>
        )}

        {isTerminal && (
          <button
            type="button"
            className="memory-progress-close"
            onClick={onClose}
          >
            {t("common.close")}
          </button>
        )}
      </div>
    </div>
  );
}
