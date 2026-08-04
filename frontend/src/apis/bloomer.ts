import { API_BASE } from "../utils/api";

export type RunOrigin = "session" | "preset";
export type RunStatus = "active" | "ended";
export type EventKind =
  | "action"
  | "refusal"
  | "milestone"
  | "stage_up"
  | "ending";

export interface BloomerAxes {
  allure: number;
  technique: number;
  depravity: number;
  sensitivity: number;
  endurance: number;
  composure: number;
}

export interface BloomerEvent {
  id: string;
  run_id: string;
  day: number;
  kind: EventKind;
  action_key: string | null;
  payload: Record<string, unknown>;
  narration: string | null;
  image_path: string | null;
  created_at: string | null;
}

export interface BloomerRun {
  id: string;
  origin: RunOrigin;
  source_session_id: string | null;
  character_id: string | null;
  name: string;
  day: number;
  max_days: number;
  actions_left: number;
  stage: number;
  nsfw_stage: number;
  mood: number;
  stamina: number;
  trust: number;
  axes: BloomerAxes;
  growth: BloomerAxes;
  wardrobe: string[];
  equipped_outfit: string | null;
  decisions: Record<string, string>;
  status: RunStatus;
  ending_key: string | null;
  initial_image_path: string | null;
  current_image_path: string | null;
  events?: BloomerEvent[];
  created_at: string | null;
  updated_at: string | null;
}

export interface BloomerActionDef {
  kind: string;
  stamina: number;
  mood: number;
  trust: number;
  axes: Record<string, number>;
  req_mood: number;
  req_trust: number;
  req_nsfw_stage: number;
  narrate: boolean;
  once_per_day: boolean;
}

export interface BloomerOutfitDef {
  required_stage: number;
  axis_bonus: Record<string, number>;
  fit_axis: string;
  tags: string;
  required_nsfw_stage?: number;
}

export interface BloomerMilestoneChoice {
  axes: Record<string, number>;
  mood: number;
  trust: number;
  flag: string;
}

export interface BloomerMilestoneDef {
  id: string;
  choices: Record<string, BloomerMilestoneChoice>;
}

export interface BloomerCatalog {
  actions: Record<string, BloomerActionDef>;
  outfits: Record<string, BloomerOutfitDef>;
  milestones: Record<string, BloomerMilestoneDef>;
}

export interface CreateRunRequest {
  origin: RunOrigin;
  name: string;
  source_session_id?: string;
  character_id?: string;
}

export interface ActionRequest {
  action_key: string;
  language?: string;
  user_text?: string;
}

export interface StatSnapshot {
  mood: number;
  stamina: number;
  trust: number;
}

export interface ActionResult {
  refused: boolean;
  narration: string | null;
  event_id: string;
  run: BloomerRun;
  stat_before?: StatSnapshot | null;
  stat_after?: StatSnapshot | null;
}

export interface AdvanceDayResult {
  nightly_narration: string | null;
  stage_up: number | null;
  stage_narration: string | null;
  ended: boolean;
  ending_key: string | null;
  ending_narration: string | null;
  milestone_pending: boolean;
  run: BloomerRun;
}

export interface MilestoneResult {
  flag: string;
  event_id: string;
  run: BloomerRun;
}

// --- API 関数 ---

export interface BloomerCharacter {
  id: string;
  name: string;
  image_path: string;
  description: string;
  personality: string;
}

export async function fetchBloomerCharacters(): Promise<BloomerCharacter[]> {
  const res = await fetch(`${API_BASE}/bloomer/characters`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchBloomerRuns(): Promise<BloomerRun[]> {
  const res = await fetch(`${API_BASE}/bloomer/runs`);
  if (!res.ok) throw new Error(`Failed to fetch bloomer runs: ${res.status}`);
  return res.json();
}

export async function fetchBloomerRun(runId: string): Promise<BloomerRun> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}`);
  if (!res.ok) throw new Error(`Failed to fetch bloomer run: ${res.status}`);
  return res.json();
}

export async function createBloomerRun(
  body: CreateRunRequest,
): Promise<BloomerRun> {
  const res = await fetch(`${API_BASE}/bloomer/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Failed to create run: ${res.status}`);
  }
  return res.json();
}

export async function deleteBloomerRun(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete run: ${res.status}`);
}

export async function performAction(
  runId: string,
  body: ActionRequest,
): Promise<ActionResult> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Action failed: ${res.status}`);
  }
  return res.json();
}

export async function advanceDay(
  runId: string,
  language = "ja",
): Promise<AdvanceDayResult> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}/advance-day`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Advance day failed: ${res.status}`);
  }
  return res.json();
}

export async function resolveMilestone(
  runId: string,
  choice_key: string,
  language = "ja",
): Promise<MilestoneResult> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}/milestone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice_key, language }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Milestone failed: ${res.status}`);
  }
  return res.json();
}

export async function equipOutfit(
  runId: string,
  outfit_key: string,
): Promise<BloomerRun> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}/outfit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outfit_key }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Equip outfit failed: ${res.status}`);
  }
  const data = await res.json();
  return data.run;
}

export async function fetchBloomerCatalog(): Promise<BloomerCatalog> {
  const res = await fetch(`${API_BASE}/bloomer/catalog`);
  if (!res.ok) throw new Error(`Failed to fetch catalog: ${res.status}`);
  return res.json();
}

/**
 * bloomer の current_image_path / initial_image_path を配信 URL に変換する。
 *
 * 対応パス:
 * - bloomer_images/{runId}/{file}  → /api/bloomer/images/{runId}/{file}
 * - history_images/{historyId}.png → /api/history/images/{historyId}
 * - images/characters/{file}       → /api/bloomer/character-images/{file}
 */
export function getBloomerImageUrl(imagePath: string): string {
  const normalized = imagePath.replace(/\\/g, "/").replace(/^\/+/, "");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0) return "";

  // Bloomer 生成画像
  if (parts[0] === "bloomer_images" && parts.length >= 3) {
    const runId = encodeURIComponent(parts[1]);
    const filename = parts
      .slice(2)
      .map((p) => encodeURIComponent(p))
      .join("/");
    return `${API_BASE}/bloomer/images/${runId}/${filename}`;
  }

  // セッション履歴画像 (history_images/{uuid}.png または uuid のみ)
  if (parts[0] === "history_images" || parts.length === 1) {
    const file = parts[parts.length - 1];
    const historyId = file.replace(/\.[^.]+$/, "");
    return `${API_BASE}/history/images/${encodeURIComponent(historyId)}`;
  }

  // キャラクタープリセット画像
  if (parts[0] === "images" && parts[1] === "characters") {
    const filename = parts
      .slice(2)
      .map((p) => encodeURIComponent(p))
      .join("/");
    return `${API_BASE}/bloomer/character-images/${filename}`;
  }

  // フォールバック: 履歴 ID として扱う
  const fallbackId = parts[parts.length - 1].replace(/\.[^.]+$/, "");
  return `${API_BASE}/history/images/${encodeURIComponent(fallbackId)}`;
}

export async function streamBloomerImage(
  runId: string,
  language: string,
  onImage: (base64: string, imagePath: string) => void,
  onError: (msg: string) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/bloomer/runs/${runId}/image/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
  if (!res.ok || !res.body) {
    onError(`Image stream failed: ${res.status}`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    let event = "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (event === "image") {
          try {
            const parsed = JSON.parse(data);
            onImage(parsed.image_base64, parsed.image_path);
          } catch {
            /* ignore parse errors */
          }
        } else if (event === "error") {
          try {
            const parsed = JSON.parse(data);
            onError(parsed.message ?? "Unknown error");
          } catch {
            onError(data);
          }
        }
        event = "";
      }
    }
  }
}
