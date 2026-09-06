/**
 * キャラチャット(TSF シナリオを経由しないキャラクターとの会話)の API クライアント。
 *
 * REST はスレッドの CRUD と姿の差し替え、発言と立ち絵の描き直しは POST + SSE。
 * SSE の解析は utils/sse.ts の readSseEvents を使い、通常ゲームの useSSE には流さない。
 */

import { API_BASE } from "../utils/api";
import { apiErrorFromResponse, jsonInit, requestJson } from "../utils/http";
import { readSseEvents } from "../utils/sse";

export type CharacterChatKind = "base" | "session" | "adventure";

export type CharacterChatAdventureAppearanceMode =
  | "default"
  | "partner_portrait"
  | "scene"
  | "custom";

/** adventure 種が紐づく TSF シナリオ(run)の状況。run が無ければ available=false で控えの値 */
export interface CharacterChatAdventureInfo {
  run_id: string | null;
  available: boolean;
  title: string;
  status: string;
  turn_count?: number;
  max_turns?: number;
  partner_name: string;
  player_name: string;
  companion_mode: boolean;
  companion_avatar_id: string | null;
  /** API 相対 URL(/avatars/{id}/file)。表示時に API_BASE を付ける */
  companion_avatar_url: string | null;
  composite: boolean;
  affection: number | null;
  stage: string | null;
  day: number | null;
  slot: string | null;
  dating: boolean;
  partner_portrait_url: string | null;
  scene_image_url: string | null;
  use_precise_reference: boolean;
  appearance_mode: CharacterChatAdventureAppearanceMode;
}

export interface CharacterChatAppearanceSource {
  type?: "base" | "session" | "prompt_expander";
  session_id?: string | null;
  history_id?: string | null;
  entry_id?: string | null;
}

export interface CharacterChatAppearance {
  identity_tags: string;
  clothing_tags: string;
  description: string;
  /** scene = 素材からコピーした場面画像(素通し)、standing = 生成した立ち絵(白抜き対象) */
  portrait_kind: "scene" | "standing";
  source: CharacterChatAppearanceSource;
}

export interface CharacterChatMessageMeta {
  lookups?: string[];
  appearance_request?: string | null;
  portrait_filename?: string | null;
  /** adventure 種: この発言が交わされた時点の手番(次の手番の文脈になる) */
  after_turn?: number | null;
  /** adventure 種で 3D モデル表示中: 返答の表情・身振り */
  expression?: string | null;
  gesture?: string | null;
  imported?: boolean;
}

export interface CharacterChatMessage {
  id: string;
  role: "user" | "character";
  content: string;
  meta: CharacterChatMessageMeta;
  created_at: string | null;
}

export interface CharacterChatPersonaTimelineItem {
  type: string;
  text: string;
}

/** セッション由来キャラの人物設定(作成時点のスナップショット。右パネルの表示用) */
export interface CharacterChatPersona {
  character_name?: string;
  session_updated_at?: string | null;
  summary_title?: string;
  summary_text?: string;
  stage?: string;
  stage_label?: string;
  transformation_count?: number;
  stats?: { bloom: number; shame: number; adaptation: number };
  attributes?: string[];
  timeline?: CharacterChatPersonaTimelineItem[];
  outfit_description?: string;
  play_memory_context?: string;
  self_mode?: boolean;
  /** adventure 種: 関係性(控え)。ライブ値は thread.adventure が持つ */
  affection?: number | null;
  day?: number | null;
  slot?: string | null;
  total_days?: number | null;
  dating?: boolean;
  given_gifts?: string[];
  completed_milestones?: string[];
  speech_style?: string;
}

export interface CharacterChatThread {
  id: string;
  kind: CharacterChatKind;
  name: string;
  pronoun: string;
  /** API_BASE 付きの絶対 URL。無ければ null(portrait_missing が true) */
  portrait_url: string | null;
  portrait_missing: boolean;
  appearance: CharacterChatAppearance;
  /** 案内役キャラは空オブジェクト */
  persona?: CharacterChatPersona;
  /** 作成時点の姿と違うとき true(「最初の姿に戻す」の有効条件) */
  can_reset_appearance?: boolean;
  /** adventure 種: 紐づく run の ID と状況 */
  source_run_id?: string | null;
  adventure?: CharacterChatAdventureInfo | null;
  summary_text: string | null;
  message_count: number;
  last_message: {
    role: "user" | "character";
    content: string;
    created_at: string | null;
  } | null;
  language: string;
  nsfw_mode: boolean;
  created_at: string | null;
  updated_at: string | null;
  messages?: CharacterChatMessage[];
}

export interface CharacterChatSourceRequest {
  source_session_id?: string;
  source_history_id?: string;
  source_prompt_expander_entry_id?: string;
}

export type CharacterChatPhase = "plan" | "reply" | "portrait" | "memory";

export type CharacterChatStreamEvent =
  | { type: "status"; data: { phase: CharacterChatPhase } }
  | { type: "chat_chunk"; data: { chunk: string } }
  | {
      type: "chat_done";
      data: {
        user_message: CharacterChatMessage;
        character_message: CharacterChatMessage;
        thread: {
          id: string;
          message_count: number;
          updated_at: string | null;
        };
      };
    }
  | {
      type: "portrait_image";
      data: { image_url: string; appearance: CharacterChatAppearance };
    }
  | { type: "portrait_error"; data: { code: string; message: string } }
  | { type: "cost"; data: { cost_usd: number } }
  | { type: "complete"; data: Record<string, never> }
  | {
      type: "error";
      data: {
        code: string;
        message: string;
        phase: string;
        retryable: boolean;
      };
    };

const BASE = `${API_BASE}/character-chat`;

/** API 相対 URL(/character-chat/images/...)を API_BASE 付きにする */
export function characterChatImageUrl(
  url: string | null | undefined,
): string | null {
  if (!url) return null;
  if (/^(?:https?:|data:|blob:)/.test(url)) return url;
  return url.startsWith(API_BASE) ? url : `${API_BASE}${url}`;
}

function normalizeThread(thread: CharacterChatThread): CharacterChatThread {
  const adventure = thread.adventure
    ? {
        ...thread.adventure,
        companion_avatar_url: characterChatImageUrl(
          thread.adventure.companion_avatar_url,
        ),
        partner_portrait_url: characterChatImageUrl(
          thread.adventure.partner_portrait_url,
        ),
        scene_image_url: characterChatImageUrl(
          thread.adventure.scene_image_url,
        ),
      }
    : (thread.adventure ?? null);
  return {
    ...thread,
    portrait_url: characterChatImageUrl(thread.portrait_url),
    adventure,
  };
}

export async function fetchCharacterChatThreads(): Promise<
  CharacterChatThread[]
> {
  const data = await requestJson<{ threads: CharacterChatThread[] }>(
    `${BASE}/threads`,
  );
  return (data.threads ?? []).map(normalizeThread);
}

/** 案内役キャラ(セレナ)のスレッドを開く。無ければ作られる(冪等) */
export async function openBaseCharacterChatThread(): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/base`,
    {
      method: "POST",
    },
  );
  return normalizeThread(thread);
}

export async function createCharacterChatThread(
  body: CharacterChatSourceRequest,
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads`,
    jsonInit("POST", body),
  );
  return normalizeThread(thread);
}

export async function fetchCharacterChatThread(
  threadId: string,
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/${encodeURIComponent(threadId)}`,
  );
  return normalizeThread(thread);
}

export async function deleteCharacterChatThread(
  threadId: string,
): Promise<void> {
  await requestJson<undefined>(
    `${BASE}/threads/${encodeURIComponent(threadId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function setCharacterChatAppearance(
  threadId: string,
  body: CharacterChatSourceRequest,
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/${encodeURIComponent(threadId)}/appearance`,
    jsonInit("PUT", body),
  );
  return normalizeThread(thread);
}

/** TSF シナリオ(恋愛シミュレーション)の攻略対象と話すスレッドを開く。無ければ作られる(冪等) */
export async function openAdventureCharacterChatThread(
  runId: string,
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/adventure/${encodeURIComponent(runId)}`,
    { method: "POST" },
  );
  return normalizeThread(thread);
}

/** adventure 種の姿を run の画像に切り替える(既定 / 攻略対象の立ち絵 / 場面の画像) */
export async function setCharacterChatAdventureAppearance(
  threadId: string,
  mode: "default" | "partner_portrait" | "scene",
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/${encodeURIComponent(threadId)}/appearance/adventure`,
    jsonInit("POST", { mode }),
  );
  return normalizeThread(thread);
}

/** 姿を作成時点(同梱の立ち絵 / 選んだ画像とタグ)へ戻す。画像生成はしない */
export async function resetCharacterChatAppearance(
  threadId: string,
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/${encodeURIComponent(threadId)}/appearance/reset`,
    { method: "POST" },
  );
  return normalizeThread(thread);
}

async function readSse(
  response: Response,
  onEvent: (event: CharacterChatStreamEvent) => void,
): Promise<void> {
  if (!response.ok || !response.body) {
    throw await apiErrorFromResponse(response);
  }
  for await (const { event, data } of readSseEvents(response.body)) {
    if (event === "message") continue;
    const parsed = JSON.parse(data) as Record<string, unknown>;
    if (event === "portrait_image") {
      const payload = parsed as { image_url: string };
      onEvent({
        type: "portrait_image",
        data: {
          ...(parsed as { appearance: CharacterChatAppearance }),
          image_url:
            characterChatImageUrl(payload.image_url) ?? payload.image_url,
        },
      });
      continue;
    }
    onEvent({
      type: event as CharacterChatStreamEvent["type"],
      data: parsed,
    } as CharacterChatStreamEvent);
  }
}

/** 発言を送り、判定 → 返答チャンク → 確定 → (立ち絵) → (要約) → cost → complete を受ける */
export async function streamCharacterChatMessage(
  threadId: string,
  body: { content: string },
  onEvent: (event: CharacterChatStreamEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${BASE}/threads/${encodeURIComponent(threadId)}/messages/stream`,
    jsonInit("POST", body),
  );
  await readSse(response, onEvent);
}

/** いまの外見タグから立ち絵を描き直す(セレナの同梱画像が無いときの初回生成も兼ねる) */
export interface CharacterChatPortraitOptions {
  /** 参照画像。scene / partner は adventure 種の run が持つ画像 */
  reference?: "current" | "scene" | "partner";
  /** NovelAI の精密参照(Anlas 消費)。呼び出し側が確認済みのときだけ true */
  use_precise_reference?: boolean;
}

export async function streamCharacterChatPortrait(
  threadId: string,
  onEvent: (event: CharacterChatStreamEvent) => void,
  options?: CharacterChatPortraitOptions,
): Promise<void> {
  const response = await fetch(
    `${BASE}/threads/${encodeURIComponent(threadId)}/portrait/stream`,
    options ? jsonInit("POST", options) : { method: "POST" },
  );
  await readSse(response, onEvent);
}
