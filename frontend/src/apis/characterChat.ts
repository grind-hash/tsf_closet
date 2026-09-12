/**
 * キャラチャット(TSF シナリオを経由しないキャラクターとの会話)の API クライアント。
 *
 * REST はスレッドの CRUD と姿の差し替え、発言と立ち絵の描き直しは POST + SSE。
 * SSE の解析は utils/sse.ts の readSseEvents を使い、通常ゲームの useSSE には流さない。
 */

import type { InstructionType } from "../types";
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

/** 返答時に実行した調べ物 1 件(引用表示用)。旧データは種類の文字列だけ */
export interface CharacterChatLookupCitation {
  kind: string;
  query?: string | null;
  session_id?: string | null;
  /** キャラが実際に読んだ整形済み本文 */
  text?: string | null;
  /** 本文に含まれるセッションの ID(「[先頭8桁]」からギャラリーへ飛ぶ対応表) */
  session_ids?: string[] | null;
  /** web_search の出典。表示前に http(s) の URL だけへ絞る */
  sources?: Array<{ title?: string | null; url?: string | null }> | null;
  /** web_search を送らなかった理由(search_policy = 検索サービスの利用規約)。送った場合は無い */
  refused?: string | null;
}

/** 提案の最初の指示に使える指示タイプ(画像のみは提案しない) */
export type CharacterChatProposalInstructionType = Exclude<
  InstructionType,
  "image_only"
>;

/**
 * 案内役の返答に添える通常プレイの提案(meta.play_proposal)。
 * サーバーの値は components/characterChat/playProposal.ts の toPlayProposal で確かめてから使う
 */
export interface CharacterChatPlayProposal {
  kind: "play";
  /** 40 文字以内 */
  title: string;
  /** 160 文字以内 */
  reason: string;
  character: { source: "template" | "custom"; id: string; name: string };
  self_mode: boolean;
  first_instruction: {
    instruction_type: CharacterChatProposalInstructionType;
    /** 200 文字以内。開始時にプレイ画面の入力欄へ入れる(送信はしない) */
    text: string;
  };
}

export interface CharacterChatMessageMeta {
  lookups?: Array<string | CharacterChatLookupCitation>;
  appearance_request?: string | null;
  portrait_filename?: string | null;
  /** adventure 種: この発言が交わされた時点の手番(次の手番の文脈になる) */
  after_turn?: number | null;
  /** 3D モデル表示中の返答: 表情・身振り(種類を問わない) */
  expression?: string | null;
  gesture?: string | null;
  imported?: boolean;
  /** 案内役の返答: おすすめの通常プレイ。形が不正なものや未知の種類は表示しない */
  play_proposal?: CharacterChatPlayProposal | null;
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
  stage?: string | null;
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

export type CharacterChatAvatarMode = "auto" | "none" | "model" | "live2d";
export type CharacterChatAvatarSource = "bundled" | "registered" | "run";

/** アバターの解決結果。live2d の URL はフロント配信、それ以外は API 配信 */
export interface CharacterChatAvatarInfo {
  /** 保存している指定。auto = 自動、none = 2D 立ち絵、model = 登録済みモデルを明示 */
  mode: CharacterChatAvatarMode;
  id: string | null;
  /** API_BASE 適用済み(/avatars/{id}/file または /character-chat/avatar/base) */
  url: string | null;
  source: CharacterChatAvatarSource | null;
  name: string | null;
  character_name: string | null;
  variant_label: string | null;
  /** 同じキャラクターの衣装差分(2 件以上あるときだけ) */
  variants: Array<{ id: string; label: string; current: boolean }>;
  /** 明示的に選んだモデルが削除されていて自動に倒したとき true */
  missing: boolean;
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
  /** 3D モデル(VRM)の解決結果。一覧では省略(null) */
  avatar?: CharacterChatAvatarInfo | null;
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

/**
 * search = 天気・Web 検索の実行中(plan と reply の間。案内役で有効なときだけ)。
 * propose = おすすめのプレイの生成中(reply の前。案内役に提案を求めたときだけ)
 */
export type CharacterChatPhase =
  | "plan"
  | "search"
  | "propose"
  | "reply"
  | "portrait"
  | "memory";

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
  | {
      /** 3D モデル表示中の着替え: 立ち絵は描かず外見タグだけ更新した */
      type: "appearance_updated";
      data: {
        appearance: CharacterChatAppearance;
        portrait_url: string | null;
      };
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
  const avatar = thread.avatar
    ? {
        ...thread.avatar,
        url:
          thread.avatar.mode === "live2d"
            ? thread.avatar.url
            : characterChatImageUrl(thread.avatar.url),
      }
    : (thread.avatar ?? null);
  return {
    ...thread,
    portrait_url: characterChatImageUrl(thread.portrait_url),
    adventure,
    avatar,
  };
}

/** スレッド一覧と、環境変数由来のグローバル設定 */
export interface CharacterChatThreadList {
  threads: CharacterChatThread[];
  /** ENABLE_PROMPT_PREVIEW。開発者向けの案内を出し分ける */
  enablePromptPreview: boolean;
}

export async function fetchCharacterChatThreads(): Promise<CharacterChatThreadList> {
  const data = await requestJson<{
    threads: CharacterChatThread[];
    enable_prompt_preview?: boolean;
  }>(`${BASE}/threads`);
  return {
    threads: (data.threads ?? []).map(normalizeThread),
    enablePromptPreview: data.enable_prompt_preview ?? false,
  };
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

/** 3D モデル(VRM)の表示を切り替える(auto / none / model) */
export async function setCharacterChatAvatar(
  threadId: string,
  request: { mode: CharacterChatAvatarMode; avatar_id?: string | null },
): Promise<CharacterChatThread> {
  const thread = await requestJson<CharacterChatThread>(
    `${BASE}/threads/${encodeURIComponent(threadId)}/avatar`,
    jsonInit("PUT", request),
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
    if (event === "appearance_updated") {
      const payload = parsed as {
        appearance: CharacterChatAppearance;
        portrait_url: string | null;
      };
      onEvent({
        type: "appearance_updated",
        data: {
          appearance: payload.appearance,
          portrait_url: characterChatImageUrl(payload.portrait_url),
        },
      });
      continue;
    }
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

/**
 * 発言の送信内容。調べ物の可否は設定画面の値を毎回載せる
 * (案内役以外のスレッドとサーバー側の設定が無いときはサーバーが無視する)
 */
export interface CharacterChatMessageRequest {
  content: string;
  /** Web 検索(Tavily)を許可する */
  use_web_search?: boolean;
  /** 天気(Open-Meteo)の取得を許可する */
  use_weather?: boolean;
  /** 案内役のスレッドで true のとき、返答におすすめの通常プレイの提案を必ず添えさせる */
  request_play_proposal?: boolean;
}

/** 発言を送り、判定 → (調べ物) → 返答チャンク → 確定 → (立ち絵) → (要約) → cost → complete を受ける */
export async function streamCharacterChatMessage(
  threadId: string,
  body: CharacterChatMessageRequest,
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
