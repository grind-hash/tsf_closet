/**
 * PlaySummaryModal - Play summary and title visualization
 *
 * Displays a play session's timeline using @xyflow/react
 * with LLM-generated title and summary.
 */

import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  type Node,
  Position,
  ReactFlow,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import "@xyflow/react/dist/style.css";
import {
  generateSessionSummary,
  getSessionSummary,
  type PlaySummaryResponse,
} from "../../apis/gallery";
import SharePreviewCard from "./SharePreviewCard";
import "./PlaySummaryModal.css";

interface PlaySummaryModalProps {
  sessionId: string;
  isOpen: boolean;
  onClose: () => void;
  onSummaryGenerated?: (sessionId: string) => void;
}

const TYPE_COLORS: Record<string, string> = {
  dress_up: "#6366f1",
  reality_alter: "#ec4899",
  action: "#f59e0b",
  conversation: "#10b981",
};

const TYPE_LABELS: Record<string, string> = {
  dress_up: "Dress Up",
  reality_alter: "Reality",
  action: "Action",
  conversation: "Chat",
};

function buildFlowElements(timeline: Array<{ label: string; type: string }>): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  if (timeline.length === 0) return { nodes, edges };

  const nodeWidth = 200;
  const nodeHeight = 50;
  const gapX = 60;
  const gapY = 80;
  const nodesPerRow = 4;

  for (let i = 0; i < timeline.length; i++) {
    const item = timeline[i];
    const row = Math.floor(i / nodesPerRow);
    const col =
      row % 2 === 0 ? i % nodesPerRow : nodesPerRow - 1 - (i % nodesPerRow);

    const x = col * (nodeWidth + gapX);
    const y = row * (nodeHeight + gapY);

    const color = TYPE_COLORS[item.type] || "#6b7280";

    nodes.push({
      id: `node-${i}`,
      position: { x, y },
      data: {
        label: (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
            }}
          >
            <span
              style={{
                fontSize: "0.65rem",
                color: color,
                fontWeight: 600,
                textTransform: "uppercase",
              }}
            >
              {TYPE_LABELS[item.type] || item.type}
            </span>
            <span style={{ fontSize: "0.8rem", lineHeight: 1.2 }}>
              {item.label}
            </span>
          </div>
        ),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: nodeWidth,
        padding: "8px 12px",
        borderRadius: 8,
        border: `2px solid ${color}`,
        background: `${color}15`,
        fontSize: "0.8rem",
      },
    });

    if (i > 0) {
      edges.push({
        id: `edge-${i - 1}-${i}`,
        source: `node-${i - 1}`,
        target: `node-${i}`,
        animated: false,
        style: { stroke: "#555", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12 },
      });
    }
  }

  return { nodes, edges };
}

export default function PlaySummaryModal({
  sessionId,
  isOpen,
  onClose,
  onSummaryGenerated,
}: PlaySummaryModalProps) {
  const { t, i18n } = useTranslation();
  const [summaryData, setSummaryData] = useState<PlaySummaryResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSharePreview, setShowSharePreview] = useState(false);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);

  // Fetch existing summary when modal opens
  useEffect(() => {
    if (!isOpen || !sessionId) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    getSessionSummary(sessionId)
      .then((data) => {
        if (!cancelled) {
          setSummaryData(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, sessionId]);

  const handleGenerate = useCallback(async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const data = await generateSessionSummary(
        sessionId,
        i18n.language === "en" ? "en" : "ja",
      );
      setSummaryData(data);
      onSummaryGenerated?.(sessionId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to generate summary",
      );
    } finally {
      setIsGenerating(false);
    }
  }, [sessionId, i18n.language, onSummaryGenerated]);

  const { nodes, edges } = useMemo(
    () => buildFlowElements(summaryData?.timeline ?? []),
    [summaryData?.timeline],
  );

  if (!isOpen) return null;

  return (
    <div
      className="play-summary-modal__overlay"
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="play-summary-title"
    >
      <div
        className="play-summary-modal"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={() => {}}
        role="document"
      >
        {/* Header */}
        <div className="play-summary-modal__header">
          <h2 id="play-summary-title">
            {summaryData?.title || t("gallery.summaryModalTitle")}
          </h2>
          <button
            type="button"
            className="play-summary-modal__close"
            onClick={onClose}
            aria-label={t("gallery.close")}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="play-summary-modal__body">
          {/* Generating overlay */}
          {isGenerating && (
            <div className="play-summary-modal__generating-overlay">
              <div className="play-summary-modal__spinner" />
              <p>{t("gallery.generatingSummary")}</p>
            </div>
          )}

          {isLoading && (
            <div className="play-summary-modal__loading">
              {t("gallery.loadingSummary")}
            </div>
          )}

          {error && <div className="play-summary-modal__error">{error}</div>}

          {!isLoading && !summaryData && !error && (
            <div className="play-summary-modal__empty">
              <p>{t("gallery.noSummaryYet")}</p>
              <button
                type="button"
                className="play-summary-modal__generate-btn"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                {isGenerating
                  ? t("gallery.generatingSummary")
                  : t("gallery.generateSummary")}
              </button>
            </div>
          )}

          {summaryData && (
            <>
              {/* Summary text */}
              <div className="play-summary-modal__summary">
                <p>{summaryData.summary}</p>
              </div>

              {/* Action buttons */}
              <div className="play-summary-modal__actions">
                <button
                  type="button"
                  className="play-summary-modal__regenerate-btn"
                  onClick={() => setShowRegenerateConfirm(true)}
                  disabled={isGenerating}
                >
                  {isGenerating
                    ? t("gallery.generatingSummary")
                    : t("gallery.regenerateSummary")}
                </button>
                <button
                  type="button"
                  className="play-summary-modal__share-btn"
                  onClick={() => setShowSharePreview(true)}
                >
                  {t("gallery.sharePreview")}
                </button>
              </div>

              {/* Timeline Flow */}
              {summaryData.timeline.length > 0 && (
                <div className="play-summary-modal__timeline">
                  <h3>{t("gallery.timelineTitle")}</h3>
                  <div className="play-summary-modal__flow-container">
                    <ReactFlow
                      nodes={nodes}
                      edges={edges}
                      fitView
                      fitViewOptions={{ padding: 0.3 }}
                      nodesDraggable={false}
                      nodesConnectable={false}
                      elementsSelectable={false}
                      panOnDrag
                      zoomOnScroll
                      minZoom={0.3}
                      maxZoom={2}
                      proOptions={{ hideAttribution: true }}
                    >
                      <Background />
                      <Controls showInteractive={false} />
                    </ReactFlow>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Share preview overlay */}
        {summaryData && (
          <SharePreviewCard
            summaryData={summaryData}
            isOpen={showSharePreview}
            onClose={() => setShowSharePreview(false)}
          />
        )}

        {/* Regenerate confirmation dialog */}
        {showRegenerateConfirm && (
          <div
            className="play-summary-modal__confirm-overlay"
            onClick={() => setShowRegenerateConfirm(false)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setShowRegenerateConfirm(false);
            }}
            role="dialog"
            aria-modal="true"
          >
            <div
              className="play-summary-modal__confirm"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={() => {}}
              role="document"
            >
              <h3>{t("gallery.regenerateConfirmTitle")}</h3>
              <p>{t("gallery.regenerateConfirmMessage")}</p>
              <div className="play-summary-modal__confirm-actions">
                <button
                  type="button"
                  className="play-summary-modal__confirm-ok"
                  onClick={() => {
                    setShowRegenerateConfirm(false);
                    handleGenerate();
                  }}
                >
                  {t("gallery.regenerateConfirmOk")}
                </button>
                <button
                  type="button"
                  className="play-summary-modal__confirm-cancel"
                  onClick={() => setShowRegenerateConfirm(false)}
                >
                  {t("gallery.cancel")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
