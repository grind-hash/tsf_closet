/**
 * Memory Generation Progress Modal Component
 *
 * メモリ生成バッチジョブの進捗をポーリングして可視化するモーダル。
 * 完了/失敗/キャンセル完了時に onFinished を呼び出す。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  cancelMemoryGeneration,
  downloadMemoryAnalysis,
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
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  // jobId 変更時のみポーリングを張り直す（t の参照変化では再実行しない）
  // biome-ignore lint/correctness/useExhaustiveDependencies: ポーリングは jobId 単位
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
  }, [jobId]);

  const handleCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      await cancelMemoryGeneration(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [jobId]);

  const handleDownload = useCallback(async () => {
    setIsDownloading(true);
    setError(null);
    try {
      await downloadMemoryAnalysis(jobId);
    } catch {
      setError(t("settings.memory.downloadAnalysisError"));
    } finally {
      setIsDownloading(false);
    }
  }, [jobId, t]);

  const total = status?.total ?? 0;
  const processed = status?.processed ?? 0;
  const phase = status?.phase ?? "summarizing";
  const isTerminal = status ? TERMINAL_STATUSES.has(status.status) : false;
  const isAnalyzing = !isTerminal && phase === "analyzing";
  const isMerging = !isTerminal && phase === "merging";

  const chunkTotal = status?.memory_chunk_total ?? 0;
  const chunkProcessed = status?.memory_chunk_processed ?? 0;
  const canDownload = chunkTotal > 0;

  const percent = isAnalyzing
    ? chunkTotal > 0
      ? Math.min(100, Math.round((chunkProcessed / chunkTotal) * 100))
      : 0
    : total > 0
      ? Math.min(100, Math.round((processed / total) * 100))
      : 0;

  const phaseLabel = isMerging
    ? t("settings.memory.phaseMerging")
    : isAnalyzing
      ? t("settings.memory.phaseAnalyzing")
      : t("settings.memory.phaseSummarizing");

  return (
    <div className="memory-progress-overlay">
      <div className="memory-progress-modal">
        <div className="memory-progress-header">
          <h2>{t("settings.memory.progressTitle")}</h2>
          <button
            type="button"
            className="memory-progress-download"
            onClick={handleDownload}
            disabled={!canDownload || isDownloading}
            title={t(
              canDownload
                ? "settings.memory.downloadAnalysisHint"
                : "settings.memory.downloadAnalysisPreparingHint",
            )}
          >
            <span aria-hidden="true">⇩</span>
            {isDownloading
              ? t("settings.memory.downloadAnalysisDownloading")
              : canDownload
                ? t("settings.memory.downloadAnalysis")
                : t("settings.memory.downloadAnalysisPreparing")}
          </button>
        </div>

        {!isTerminal && <p className="memory-progress-phase">{phaseLabel}</p>}

        <div className="memory-progress-bar-track">
          <div
            className={
              isMerging
                ? "memory-progress-bar-fill memory-progress-bar-fill--indeterminate"
                : "memory-progress-bar-fill"
            }
            style={isMerging ? undefined : { width: `${percent}%` }}
          />
        </div>

        {isAnalyzing ? (
          <p className="memory-progress-status">
            {t("settings.memory.progressAnalyzing", {
              processed: chunkProcessed,
              total: chunkTotal,
            })}
          </p>
        ) : isMerging ? (
          <p className="memory-progress-status">
            {t("settings.memory.progressMerging")}
          </p>
        ) : (
          <p className="memory-progress-status">
            {t("settings.memory.progressStatus", { processed, total })}
          </p>
        )}

        {status?.current_session_id &&
          !isTerminal &&
          phase === "summarizing" && (
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
