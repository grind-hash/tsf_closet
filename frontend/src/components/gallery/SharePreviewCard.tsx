/**
 * SharePreviewCard - SNS share image generator
 *
 * Renders a visually appealing card image on Canvas (1200x630, Twitter OGP size)
 * with the play title, summary, timeline badges, and "TSF Closet" watermark.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PlaySummaryResponse } from "../../apis/gallery";
import "./SharePreviewCard.css";

interface SharePreviewCardProps {
  summaryData: PlaySummaryResponse;
  isOpen: boolean;
  onClose: () => void;
}

const CARD_W = 1200;
const CARD_H = 630;

const TYPE_COLORS: Record<string, string> = {
  dress_up: "#818cf8",
  reality_alter: "#f472b6",
  action: "#fbbf24",
  conversation: "#34d399",
};

const TYPE_LABELS: Record<string, string> = {
  dress_up: "DRESS UP",
  reality_alter: "REALITY",
  action: "ACTION",
  conversation: "CHAT",
};

/**
 * Draw rounded rectangle path
 */
function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

/**
 * Wrap text to fit within maxWidth, returning array of lines
 */
function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
): string[] {
  const lines: string[] = [];
  let currentLine = "";

  for (const char of text) {
    const testLine = currentLine + char;
    if (ctx.measureText(testLine).width > maxWidth && currentLine.length > 0) {
      lines.push(currentLine);
      currentLine = char;
    } else {
      currentLine = testLine;
    }
  }
  if (currentLine) lines.push(currentLine);
  return lines;
}

function drawShareCard(
  canvas: HTMLCanvasElement,
  data: PlaySummaryResponse,
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  canvas.width = CARD_W;
  canvas.height = CARD_H;

  // --- Background gradient ---
  const bgGrad = ctx.createLinearGradient(0, 0, CARD_W, CARD_H);
  bgGrad.addColorStop(0, "#0f0c29");
  bgGrad.addColorStop(0.5, "#302b63");
  bgGrad.addColorStop(1, "#24243e");
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, CARD_W, CARD_H);

  // --- Subtle decorative circles ---
  ctx.globalAlpha = 0.06;
  ctx.fillStyle = "#818cf8";
  ctx.beginPath();
  ctx.arc(200, 100, 260, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f472b6";
  ctx.beginPath();
  ctx.arc(1000, 500, 300, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;

  // --- Top accent line ---
  const accentGrad = ctx.createLinearGradient(60, 0, CARD_W - 60, 0);
  accentGrad.addColorStop(0, "#6366f1");
  accentGrad.addColorStop(0.5, "#ec4899");
  accentGrad.addColorStop(1, "#f59e0b");
  ctx.fillStyle = accentGrad;
  ctx.fillRect(60, 30, CARD_W - 120, 3);

  // --- Title ---
  ctx.fillStyle = "#ffffff";
  ctx.font =
    "bold 48px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
  ctx.textBaseline = "top";

  const titleText = data.title || "Untitled";
  const titleLines = wrapText(ctx, titleText, CARD_W - 160);
  let titleY = 56;
  for (const line of titleLines.slice(0, 2)) {
    ctx.fillText(line, 80, titleY);
    titleY += 58;
  }

  // --- Divider ---
  const divY = titleY + 8;
  ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
  ctx.fillRect(80, divY, 200, 2);

  // --- Summary ---
  ctx.fillStyle = "rgba(255, 255, 255, 0.82)";
  ctx.font = "22px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";

  const summaryText = data.summary || "";
  const summaryLines = wrapText(ctx, summaryText, CARD_W - 160);
  let sumY = divY + 20;
  for (const line of summaryLines.slice(0, 4)) {
    ctx.fillText(line, 80, sumY);
    sumY += 32;
  }

  // --- Timeline badges ---
  const timeline = data.timeline || [];
  if (timeline.length > 0) {
    const badgeStartY = Math.max(sumY + 24, 320);
    const badgeH = 36;
    const badgeGap = 10;
    const badgePadX = 16;
    const maxBadges = 12;
    const displayTimeline = timeline.slice(0, maxBadges);

    let curX = 80;
    let curY = badgeStartY;

    ctx.font =
      "bold 13px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";

    for (let i = 0; i < displayTimeline.length; i++) {
      const item = displayTimeline[i];
      const typeLabel = TYPE_LABELS[item.type] || item.type.toUpperCase();
      const color = TYPE_COLORS[item.type] || "#6b7280";

      // Measure badge width
      ctx.font =
        "bold 10px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
      const typeLabelW = ctx.measureText(typeLabel).width;
      ctx.font = "14px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
      const labelW = ctx.measureText(item.label).width;
      const badgeW = Math.max(typeLabelW, labelW) + badgePadX * 2;

      // Line break if overflows
      if (curX + badgeW > CARD_W - 80) {
        curX = 80;
        curY += badgeH + badgeGap;
      }

      // Clamp vertically
      if (curY + badgeH > CARD_H - 80) break;

      // Badge background
      roundRect(ctx, curX, curY, badgeW, badgeH, 6);
      ctx.fillStyle = `${color}22`;
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Type label (small, colored)
      ctx.fillStyle = color;
      ctx.font =
        "bold 9px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
      ctx.textBaseline = "top";
      ctx.fillText(typeLabel, curX + badgePadX, curY + 4);

      // Label text
      ctx.fillStyle = "#e0e0e0";
      ctx.font = "13px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
      ctx.fillText(item.label, curX + badgePadX, curY + 17);

      // Arrow connector
      if (i < displayTimeline.length - 1) {
        const arrowX = curX + badgeW + 2;
        const arrowY = curY + badgeH / 2;
        ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
        ctx.beginPath();
        ctx.moveTo(arrowX, arrowY - 4);
        ctx.lineTo(arrowX + 6, arrowY);
        ctx.lineTo(arrowX, arrowY + 4);
        ctx.closePath();
        ctx.fill();
      }

      curX += badgeW + badgeGap + 10;
    }

    // "..." if truncated
    if (timeline.length > maxBadges) {
      ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
      ctx.font = "18px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
      ctx.fillText(`… +${timeline.length - maxBadges}`, curX, curY + 8);
    }
  }

  // --- Bottom accent line ---
  ctx.fillStyle = accentGrad;
  ctx.fillRect(60, CARD_H - 33, CARD_W - 120, 3);

  // --- Watermark: "TSF Closet" ---
  ctx.globalAlpha = 0.5;
  ctx.fillStyle = "#ffffff";
  ctx.font =
    "bold 22px 'Segoe UI', 'Noto Sans JP', 'Hiragino Sans', sans-serif";
  ctx.textBaseline = "bottom";
  ctx.textAlign = "right";
  ctx.fillText("TSF Closet", CARD_W - 70, CARD_H - 48);
  ctx.globalAlpha = 1;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
}

export default function SharePreviewCard({
  summaryData,
  isOpen,
  onClose,
}: SharePreviewCardProps) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);

  // Draw card whenever data or open state changes
  useEffect(() => {
    if (!isOpen || !canvasRef.current) return;
    drawShareCard(canvasRef.current, summaryData);
  }, [isOpen, summaryData]);

  const handleDownload = useCallback(() => {
    if (!canvasRef.current) return;
    const link = document.createElement("a");
    link.download = `tsf-closet-${summaryData.title || "summary"}.png`;
    link.href = canvasRef.current.toDataURL("image/png");
    link.click();
  }, [summaryData.title]);

  const handleCopyToClipboard = useCallback(async () => {
    if (!canvasRef.current) return;
    try {
      const blob = await new Promise<Blob | null>((resolve) =>
        canvasRef.current!.toBlob(resolve, "image/png"),
      );
      if (blob) {
        await navigator.clipboard.write([
          new ClipboardItem({ "image/png": blob }),
        ]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Fallback: download instead
      handleDownload();
    }
  }, [handleDownload]);

  if (!isOpen) return null;

  return (
    <div
      className="share-preview__overlay"
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="share-preview"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={() => {}}
        role="document"
      >
        <div className="share-preview__header">
          <h3>{t("gallery.sharePreviewTitle")}</h3>
          <button
            type="button"
            className="share-preview__close"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="share-preview__canvas-wrapper">
          <canvas ref={canvasRef} />
        </div>

        <div className="share-preview__actions">
          <button
            type="button"
            className="share-preview__btn share-preview__btn--copy"
            onClick={handleCopyToClipboard}
          >
            {copied
              ? t("gallery.shareImageCopied")
              : t("gallery.shareImageCopy")}
          </button>
          <button
            type="button"
            className="share-preview__btn share-preview__btn--download"
            onClick={handleDownload}
          >
            {t("gallery.shareImageDownload")}
          </button>
        </div>
      </div>
    </div>
  );
}
