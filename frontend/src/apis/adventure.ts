import { API_BASE } from "../utils/api";

export type AdventurePreset =
  | "infiltration"
  | "escape"
  | "negotiation"
  | "disguise";
export type AdventureStatus = "active" | "success" | "partial" | "failure";

export interface AdventureChoice {
  id: string;
  label: string;
}

export interface AdventureMilestone {
  id: string;
  label: string;
}

export interface AdventureImagePrompt {
  scene_tags: string;
  player_tags: string;
  npc_tags: string[];
}

export interface AdventureImageRegenerateOptions extends AdventureImagePrompt {
  redraw_from_reference: boolean;
}

export interface AdventureTurn {
  id: string;
  turn_number: number;
  client_turn_id: string;
  user_input: string;
  input_kind: "choice" | "free_text";
  narrative: string;
  choices: AdventureChoice[];
  image_url: string | null;
  image_status: string;
  created_at: string | null;
  run_status?: AdventureStatus;
  remaining_turns?: number;
  clues?: string[];
  ending_title?: string | null;
  ending_summary?: string | null;
}

export interface AdventureRun {
  id: string;
  source_session_id: string | null;
  source_history_id: string | null;
  preset: AdventurePreset;
  scenario_template_id: string | null;
  title: string;
  objective: string;
  setting: string;
  constraints: string[];
  status: AdventureStatus;
  turn_count: number;
  max_turns: number;
  remaining_turns: number;
  ending_title: string | null;
  ending_summary: string | null;
  clues: string[];
  milestones: AdventureMilestone[];
  completed_milestones: string[];
  opening_narrative: string;
  opening_image_url: string;
  choices: AdventureChoice[];
  current_image_url: string;
  current_image_prompt: AdventureImagePrompt | null;
  turns: AdventureTurn[];
  created_at: string | null;
  updated_at: string | null;
}

export interface AdventureTemplate {
  id: string;
  preset: AdventurePreset;
  title: string;
  synopsis: string;
  setting: string;
  objective: string;
  constraints: string[];
  max_turns: number;
  content_rating: "mature";
}

export interface AdventureSetupRequest {
  source_session_id: string;
  source_history_id?: string;
  preset: AdventurePreset;
}

export interface AdventureSetup {
  setting: string;
  objective: string;
  constraints: string[];
}

export interface AdventureCreateRequest extends AdventureSetupRequest {
  custom_setup: string;
  scenario_setting: string;
  scenario_objective: string;
  scenario_constraints: string[];
  scenario_template_id?: string;
  replay_run_id?: string;
}

export interface AdventureStreamEvent {
  type:
    | "status"
    | "narrative_chunk"
    | "narrative_done"
    | "turn"
    | "image"
    | "complete"
    | "error";
  data: Record<string, unknown>;
}

function withApiBase(url: string | null): string | null {
  if (!url) return null;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

function normalizeRun(run: AdventureRun): AdventureRun {
  return {
    ...run,
    current_image_url: withApiBase(run.current_image_url) ?? "",
    opening_image_url:
      withApiBase(run.opening_image_url) ??
      withApiBase(run.current_image_url) ??
      "",
    turns: (run.turns ?? []).map((turn) => ({
      ...turn,
      image_url: withApiBase(turn.image_url),
    })),
  };
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.detail?.message ?? payload?.detail ?? response.statusText,
    );
  }
  return response.json() as Promise<T>;
}

export async function fetchAdventureTemplates(): Promise<AdventureTemplate[]> {
  const payload = await requestJson<{ templates: AdventureTemplate[] }>(
    `${API_BASE}/adventure/templates`,
  );
  return payload.templates;
}

export async function fetchAdventureRuns(): Promise<AdventureRun[]> {
  const payload = await requestJson<{ runs: AdventureRun[] }>(
    `${API_BASE}/adventure/runs`,
  );
  return payload.runs.map(normalizeRun);
}

export async function fetchAdventureRun(runId: string): Promise<AdventureRun> {
  return normalizeRun(
    await requestJson<AdventureRun>(`${API_BASE}/adventure/runs/${runId}`),
  );
}

export async function generateAdventureSetup(
  request: AdventureSetupRequest,
): Promise<AdventureSetup> {
  return requestJson<AdventureSetup>(`${API_BASE}/adventure/setup/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function createAdventureRun(
  request: AdventureCreateRequest,
): Promise<AdventureRun> {
  return normalizeRun(
    await requestJson<AdventureRun>(`${API_BASE}/adventure/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }),
  );
}

export async function deleteAdventureRun(runId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/adventure/runs/${runId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(response.statusText);
}

async function readSse(
  response: Response,
  onEvent: (event: AdventureStreamEvent) => void,
): Promise<void> {
  if (!response.ok || !response.body) {
    throw new Error(response.statusText || "Streaming request failed");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let eventType = "message";
      const dataLines: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (eventType !== "message" && dataLines.length > 0) {
        const data = JSON.parse(dataLines.join("\n")) as Record<
          string,
          unknown
        >;
        onEvent({ type: eventType as AdventureStreamEvent["type"], data });
      }
    }
    if (done) break;
  }
}

export async function streamAdventureTurn(
  runId: string,
  body: {
    client_turn_id: string;
    user_input: string;
    input_kind: "choice" | "free_text";
  },
  onEvent: (event: AdventureStreamEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/adventure/runs/${runId}/turns/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  await readSse(response, onEvent);
}

export async function streamAdventureImage(
  runId: string,
  options: AdventureImageRegenerateOptions | null,
  onEvent: (event: AdventureStreamEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/adventure/runs/${runId}/image/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options ?? { redraw_from_reference: true }),
    },
  );
  await readSse(response, onEvent);
}

export function normalizeAdventureImageUrl(url: unknown): string | null {
  return typeof url === "string" ? withApiBase(url) : null;
}
