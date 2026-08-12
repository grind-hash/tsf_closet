import { API_BASE } from "../utils/api";

export type AdventurePreset =
  | "infiltration"
  | "escape"
  | "negotiation"
  | "disguise"
  | "romance";
export type AdventureStatus = "active" | "success" | "partial" | "failure";
/** gift / work / confess は romance プリセット専用の行動 */
export type AdventureInputKind =
  | "choice"
  | "free_text"
  | "reality_alter"
  | "gift"
  | "work"
  | "confess";
/** 物語の語りの人称。second_person が従来どおりの既定 */
export type AdventureNarrationVoice =
  | "second_person"
  | "third_person"
  | "first_person";

export interface AdventureChoice {
  id: string;
  label: string;
}

export interface AdventureMilestone {
  id: string;
  label: string;
}

export interface AdventureVisualCharacter {
  name: string;
  description: string;
  clothing: string;
  action: string;
}

export interface AdventureVisualState {
  location: string;
  appearance: string;
  clothing: string;
  surroundings: string;
  main_characters: AdventureVisualCharacter[];
}

export interface AdventureImagePrompt {
  scene_tags: string;
  player_tags: string;
  npc_tags: string[];
}

export type AdventureGiftTier = "budget" | "standard" | "luxury";

export interface AdventureGift {
  id: string;
  name: string;
  price: number;
  tier: AdventureGiftTier;
}

/** romance の公開状態。隠し好みはサーバ側で除外済み */
export interface AdventureSim {
  total_days: number;
  /** 次に行動する日。1始まり */
  day: number;
  slot: "day" | "night";
  affection: number;
  stage: "stranger" | "friend" | "aware" | "mutual";
  money: number;
  partner_name: string;
  /** 主人公(自分)。導入前の旧 run では未定義 */
  player_name?: string;
  player_character_id?: string;
  job: { name: string; wage: number };
  gift_catalog: AdventureGift[];
  given_gift_ids: string[];
  confession_available: boolean;
}

export interface AdventureImageRegenerateOptions extends AdventureImagePrompt {
  redraw_from_reference: boolean;
}

export interface AdventureTurn {
  id: string;
  turn_number: number;
  client_turn_id: string;
  user_input: string;
  input_kind: AdventureInputKind;
  narrative: string;
  /** このターン時点の現在地。旧ターンでは null */
  location: string | null;
  choices: AdventureChoice[];
  image_url: string | null;
  image_status: string;
  /** 中央の立ち絵のこのターン時点の画像 */
  portrait_image_url: string | null;
  portrait_status: string;
  created_at: string | null;
  run_status?: AdventureStatus;
  remaining_turns?: number;
  clues?: string[];
  completed_milestones?: string[];
  visual_state?: AdventureVisualState | null;
  ending_title?: string | null;
  ending_summary?: string | null;
  /** romance のみ。ターン確定時点の公開シミュ状態 */
  sim?: AdventureSim | null;
  /** romance のみ。ターン確定時点の攻略対象の様子。無ければ null */
  partner_note?: string | null;
  /** romance のみ。ターン確定時点の攻略対象の立ち絵 */
  partner_portrait_url?: string | null;
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
  /** プレイ中に「現実改変：〜」で宣言された世界ルール。旧runでは未定義 */
  reality_rules?: string[];
  milestones: AdventureMilestone[];
  completed_milestones: string[];
  /** 現在地・登場人物などの最新ビジュアル状態。開始直後は null のことがある */
  visual_state: AdventureVisualState | null;
  opening_narrative: string;
  opening_image_url: string;
  choices: AdventureChoice[];
  current_image_url: string;
  current_image_prompt: AdventureImagePrompt | null;
  /** NovelAI精密参照。既定false。trueのとき参照1枚あたりAnlas追加消費 */
  use_precise_reference: boolean;
  /** 既定false。trueのときのみポートレート更新後に合成シーンも直列で再生成する */
  enable_composite_scene: boolean;
  /** 衣装レイヤー考慮。trueのとき外衣に覆われた下着を画像タグから外す */
  respect_clothing_layers: boolean;
  /** 物語の語りの人称。旧runは second_person 扱い */
  narration_voice: AdventureNarrationVoice;
  /** first_person のときに使う一人称語 */
  narration_pronoun: string;
  /** 開始時に一度だけ生成される背景。非合成モードの固定背景として使用 */
  background_image_url: string | null;
  /** 現在の中央の立ち絵（最新ターン分） */
  portrait_image_url: string | null;
  /** 開始時ポートレート（ターンストリップの先頭用） */
  opening_portrait_url: string | null;
  /** romance のみ。非合成モードで並置表示する攻略対象の立ち絵(最新) */
  partner_portrait_url?: string | null;
  /** romance のみ。開幕(手番0)時点の攻略対象の立ち絵 */
  opening_partner_portrait_url?: string | null;
  /** romance のみ。他プリセットでは未定義 */
  sim?: AdventureSim | null;
  /** romance のみ。開幕(手番0)時点の公開シミュ状態 */
  opening_sim?: AdventureSim | null;
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
  /** 自動生成タイプのターン数。未指定なら15。作品シナリオ・リプレイでは無視される */
  scenario_max_turns?: number;
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
  /** 既定false。ON時のみ開始画像を精密参照に使う */
  use_precise_reference?: boolean;
  /** 既定false。ON時のみ合成シーンも生成する */
  enable_composite_scene?: boolean;
  /** 設定画面の「服の重なりを考慮」をそのまま引き継ぐ */
  respect_clothing_layers?: boolean;
  /** 未指定なら second_person（従来どおりの語り口） */
  narration_voice?: AdventureNarrationVoice;
  /** first_person のときだけ使う。未指定なら「僕」 */
  narration_pronoun?: string;
  /** romance の主人公テンプレートキャラクター。未指定なら既定(char1) */
  romance_player_character_id?: string;
  /** romance の主人公を特定セッション時点の変身状態にする場合に指定 */
  romance_player_session_id?: string;
  romance_player_history_id?: string;
}

export interface AdventureSettingsUpdateRequest {
  use_precise_reference: boolean;
  enable_composite_scene: boolean;
  /** 未指定なら run 側の既存値を維持する */
  respect_clothing_layers?: boolean;
}

export interface AdventureStreamEvent {
  type:
    | "status"
    | "narrative_chunk"
    | "narrative_done"
    | "turn"
    | "image"
    | "portrait_image"
    | "partner_image"
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
    use_precise_reference: Boolean(run.use_precise_reference),
    enable_composite_scene: Boolean(run.enable_composite_scene),
    respect_clothing_layers: Boolean(run.respect_clothing_layers),
    // 旧runやモック応答にキーが無くても表示側が undefined を掴まないようにする
    narration_voice: run.narration_voice ?? "second_person",
    narration_pronoun: run.narration_pronoun || "僕",
    sim: run.sim ?? null,
    opening_sim: run.opening_sim ?? null,
    partner_portrait_url: withApiBase(run.partner_portrait_url ?? null),
    opening_partner_portrait_url: withApiBase(
      run.opening_partner_portrait_url ?? null,
    ),
    current_image_url: withApiBase(run.current_image_url) ?? "",
    opening_image_url:
      withApiBase(run.opening_image_url) ??
      withApiBase(run.current_image_url) ??
      "",
    background_image_url: withApiBase(run.background_image_url),
    portrait_image_url: withApiBase(run.portrait_image_url),
    opening_portrait_url:
      withApiBase(run.opening_portrait_url) ??
      withApiBase(run.portrait_image_url),
    turns: (run.turns ?? []).map((turn) => ({
      ...turn,
      image_url: withApiBase(turn.image_url),
      portrait_image_url: withApiBase(turn.portrait_image_url),
      partner_portrait_url: withApiBase(turn.partner_portrait_url ?? null),
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
    input_kind: AdventureInputKind;
    /** romance のプレゼント贈呈時のみ指定する */
    gift_id?: string;
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

export async function regenerateAdventureChoices(
  runId: string,
): Promise<AdventureChoice[]> {
  const payload = await requestJson<{ choices: AdventureChoice[] }>(
    `${API_BASE}/adventure/runs/${runId}/choices/regenerate`,
    { method: "POST" },
  );
  return payload.choices;
}

export async function updateAdventureRunSettings(
  runId: string,
  request: AdventureSettingsUpdateRequest,
): Promise<AdventureRun> {
  return normalizeRun(
    await requestJson<AdventureRun>(
      `${API_BASE}/adventure/runs/${runId}/settings`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      },
    ),
  );
}

export function normalizeAdventureImageUrl(url: unknown): string | null {
  return typeof url === "string" ? withApiBase(url) : null;
}
