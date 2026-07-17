/**
 * チャット履歴をMarkdown / CSV / JSON形式でエクスポートする
 */

import type { ChatMessage } from "../types";

export interface ExportSessionInfo {
  sessionId: string;
  characterName?: string;
}

// ----------------------------------------------------------------
// Markdown
// ----------------------------------------------------------------

export function exportAsMarkdown(
  messages: ChatMessage[],
  info: ExportSessionInfo,
): string {
  const lines: string[] = [];
  lines.push(`# Chat History`);
  lines.push("");
  lines.push(`- **Session ID**: ${info.sessionId}`);
  if (info.characterName) {
    lines.push(`- **Character**: ${info.characterName}`);
  }
  lines.push(
    `- **Exported at**: ${new Date().toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}`,
  );
  lines.push(`- **Messages**: ${messages.length}`);
  lines.push("");
  lines.push("---");
  lines.push("");

  for (const msg of messages) {
    const role = msg.role === "user" ? "You" : "Character";
    const time = formatTimestamp(msg.createdAt);
    const typeLabel = msg.instructionType ? ` [${msg.instructionType}]` : "";
    lines.push(`### ${role}${typeLabel} — ${time}`);
    lines.push("");
    lines.push(msg.content);
    lines.push("");
  }

  return lines.join("\n");
}

// ----------------------------------------------------------------
// CSV
// ----------------------------------------------------------------

export function exportAsCsv(
  messages: ChatMessage[],
  info: ExportSessionInfo,
): string {
  const BOM = "\uFEFF";
  const header = [
    "session_id",
    "timestamp",
    "role",
    "instruction_type",
    "content",
  ];
  const rows = messages.map((msg) => [
    info.sessionId,
    msg.createdAt,
    msg.role,
    msg.instructionType ?? "",
    msg.content,
  ]);

  const escape = (v: string) => {
    if (v.includes('"') || v.includes(",") || v.includes("\n")) {
      return `"${v.replace(/"/g, '""')}"`;
    }
    return v;
  };

  const csvLines = [header, ...rows].map((r) => r.map(escape).join(","));
  return BOM + csvLines.join("\n");
}

// ----------------------------------------------------------------
// JSON
// ----------------------------------------------------------------

export function exportAsJson(
  messages: ChatMessage[],
  info: ExportSessionInfo,
): string {
  const data = {
    sessionId: info.sessionId,
    characterName: info.characterName ?? null,
    exportedAt: new Date().toISOString(),
    messageCount: messages.length,
    messages: messages.map((msg) => ({
      role: msg.role,
      content: msg.content,
      instructionType: msg.instructionType ?? null,
      createdAt: msg.createdAt,
    })),
  };
  return JSON.stringify(data, null, 2);
}

// ----------------------------------------------------------------
// Plain text (for clipboard)
// ----------------------------------------------------------------

export function exportAsPlainText(
  messages: ChatMessage[],
  info: ExportSessionInfo,
): string {
  const lines: string[] = [];
  lines.push(`Session: ${info.sessionId}`);
  if (info.characterName) {
    lines.push(`Character: ${info.characterName}`);
  }
  lines.push("");

  for (const msg of messages) {
    const role = msg.role === "user" ? "You" : "Character";
    const time = formatTimestamp(msg.createdAt);
    const typeLabel = msg.instructionType ? ` [${msg.instructionType}]` : "";
    lines.push(`${role}${typeLabel} (${time}):`);
    lines.push(msg.content);
    lines.push("");
  }

  return lines.join("\n");
}

// ----------------------------------------------------------------
// Novel (content only, .txt)
// ----------------------------------------------------------------

export function exportAsNovel(messages: ChatMessage[]): string {
  return messages
    .filter((msg) => msg.role !== "user" && msg.content.trim())
    .map((msg) => {
      let text = msg.content.trim();
      // Strip feelingText emoji prefix
      if (msg.isFeelingText && text.startsWith("\u{1F4AD}")) {
        text = text.replace(/^\u{1F4AD}\s*/u, "").trim();
      }
      return text;
    })
    .filter((text) => text.length > 0)
    .join("\n\n");
}

// ----------------------------------------------------------------
// Download helper
// ----------------------------------------------------------------

export function downloadFile(
  content: string,
  filename: string,
  mimeType: string,
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Download a pre-built Blob (e.g. server-generated zip or markdown).
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * バイト数を人が読みやすい形式（KB / MB）に変換する。
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
  } catch {
    return iso;
  }
}
