/**
 * AI箱庭モード API
 *
 * 世界(住民・掟・年代記)の作成と、1日進める・掟の切り替え・住民の一言・その場で変身・
 * アバターの生成を扱う。項目名はバックエンドに合わせてスネークケースのまま扱う。
 */

import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

export type HakoniwaGender = "female" | "male";
export type HakoniwaResidentSource = "preset" | "character" | "custom";
export type HakoniwaLookKind = "transform" | "dress" | "base";

export interface HakoniwaLine {
  /** 話す住民の id */
  speaker: string;
  text: string;
}

export interface HakoniwaEvent {
  id: string;
  day: number;
  title: string;
  narration: string;
  lines: HakoniwaLine[];
  participants: string[];
  mood_delta: Record<string, number>;
  affinity_delta: number;
  /** llm / template / player */
  source: string;
  /** transform(変身の出来事)など */
  kind?: string | null;
  change_text?: string | null;
  favorite: boolean;
}

export interface HakoniwaTransformation {
  description: string;
  tags: string;
  image: string;
  image_url: string | null;
  day: number;
}

export interface HakoniwaResident {
  id: string;
  source: HakoniwaResidentSource;
  preset_id: string | null;
  character_preset_id: string | null;
  name: string;
  gender: HakoniwaGender;
  /** いま見えている体の性別(入れ替わり・変身を反映) */
  body_gender: HakoniwaGender;
  age: string;
  job: string;
  personality: string;
  pronoun: string;
  /** プレイヤーが書いた外見の説明(画像タグとは別に持つ) */
  appearance_text: string;
  /** 通常の姿の画像タグ(外見の説明から作る) */
  base_tags: string;
  dress_text: string;
  dress_tags: string;
  mood: number;
  affinities: Record<string, number>;
  transformation: HakoniwaTransformation | null;
  transformation_history: HakoniwaTransformation[];
  swapped_with: string | null;
  /** いま表示する姿(入れ替わり中は相手の姿) */
  display_avatar_url: string | null;
  display_kind: HakoniwaLookKind;
  display_owner_id: string;
  own_avatar_url: string | null;
  avatar_url: string | null;
  dress_avatar_url: string | null;
}

export interface HakoniwaRuleCard {
  id: string;
  name: string;
  description: string;
  custom: boolean;
  active: boolean;
}

export interface HakoniwaWorld {
  id: string;
  name: string;
  day: number;
  created_at: string | null;
  updated_at: string | null;
  background_url: string;
  /** default はユーザー設定の画像モデルに従う */
  image_model: string;
  image_model_effective: string;
  /** ユーザー設定の画像モデル(default を選んだときに使う) */
  image_model_default: string;
  image_model_options: string[];
  /** native(V5 の透過生成)/ removal(白背景を表示側で抜く) */
  transparency: "native" | "removal";
  active_rules: string[];
  swap_pair: string[] | null;
  rule_cards: HakoniwaRuleCard[];
  residents: HakoniwaResident[];
  events: HakoniwaEvent[];
}

export interface HakoniwaWorldSummary {
  id: string;
  name: string;
  day: number;
  resident_count: number;
  event_count: number;
  created_at: string | null;
  updated_at: string | null;
  residents: { id: string; name: string; avatar_url: string | null }[];
}

export interface HakoniwaPreset {
  id: string;
  gender: HakoniwaGender;
  name: string;
  age: string;
  job: string;
  personality: string;
  avatar_url: string;
  dress_avatar_url: string;
}

export interface HakoniwaCatalog {
  presets: HakoniwaPreset[];
  rule_cards: { id: string; name: string; description: string }[];
  background_url: string;
  image_model_options: string[];
}

export interface HakoniwaDayResult {
  world: HakoniwaWorld;
  new_events: HakoniwaEvent[];
  cost_usd: number | null;
}

export interface HakoniwaResidentChange {
  world: HakoniwaWorld;
  resident_id: string;
  tag_expansion_failed: boolean;
  cost_usd: number | null;
}

export interface HakoniwaGreeting {
  resident_id: string;
  text: string;
  source: string;
  cost_usd: number | null;
}

export interface HakoniwaImageResult {
  world: HakoniwaWorld;
  cost_usd: number | null;
}

export interface HakoniwaResidentInput {
  name: string;
  personality: string;
  gender: HakoniwaGender;
  appearance_text: string;
  dress_text: string;
}

export interface HakoniwaCharacterEntry {
  character_preset_id: string;
  gender?: HakoniwaGender | null;
}

const BASE = `${API_BASE}/hakoniwa`;
const WORLDS = `${BASE}/worlds`;

function query(language: string): string {
  return `?language=${encodeURIComponent(language)}`;
}

/** 同梱素材(/hakoniwa-assets/)はそのまま、API の画像は API_BASE を付けた URL にする */
export function hakoniwaMediaUrl(
  url: string | null | undefined,
): string | null {
  if (!url) return null;
  if (
    /^(https?:|data:|blob:)/.test(url) ||
    url.startsWith("/hakoniwa-assets/")
  ) {
    return url;
  }
  return `${API_BASE}${url}`;
}

export function fetchHakoniwaCatalog(
  language: string,
): Promise<HakoniwaCatalog> {
  return requestJson<HakoniwaCatalog>(`${BASE}/catalog${query(language)}`);
}

export async function fetchHakoniwaWorlds(
  language: string,
): Promise<HakoniwaWorldSummary[]> {
  const data = await requestJson<{ worlds?: HakoniwaWorldSummary[] }>(
    `${WORLDS}${query(language)}`,
  );
  return data.worlds ?? [];
}

export function createHakoniwaWorld(body: {
  name: string;
  preset_ids: string[];
  characters: HakoniwaCharacterEntry[];
  language: string;
}): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(WORLDS, jsonInit("POST", body));
}

export function fetchHakoniwaWorld(
  worldId: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(`${WORLDS}/${worldId}${query(language)}`);
}

export async function deleteHakoniwaWorld(worldId: string): Promise<void> {
  await requestJson<void>(`${WORLDS}/${worldId}`, jsonInit("DELETE"));
}

export function updateHakoniwaSettings(
  worldId: string,
  imageModel: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/settings`,
    jsonInit("PATCH", { image_model: imageModel, language }),
  );
}

export function advanceHakoniwaDay(
  worldId: string,
  language: string,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/day`,
    jsonInit("POST", { language }),
  );
}

export function toggleHakoniwaRule(
  worldId: string,
  cardId: string,
  active: boolean,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/rules/${encodeURIComponent(cardId)}`,
    jsonInit("PUT", { active, language }),
  );
}

export function addHakoniwaCustomRule(
  worldId: string,
  rule: { name: string; text: string },
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/custom-rules`,
    jsonInit("POST", { ...rule, language }),
  );
}

export function updateHakoniwaCustomRule(
  worldId: string,
  ruleId: string,
  rule: { name: string; text: string },
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/custom-rules/${encodeURIComponent(ruleId)}`,
    jsonInit("PATCH", { ...rule, language }),
  );
}

export function deleteHakoniwaCustomRule(
  worldId: string,
  ruleId: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/custom-rules/${encodeURIComponent(ruleId)}${query(language)}`,
    jsonInit("DELETE"),
  );
}

export function addHakoniwaResident(
  worldId: string,
  input: HakoniwaResidentInput,
  language: string,
): Promise<HakoniwaResidentChange> {
  return requestJson<HakoniwaResidentChange>(
    `${WORLDS}/${worldId}/residents`,
    jsonInit("POST", { ...input, language }),
  );
}

export function addHakoniwaCharacterResident(
  worldId: string,
  entry: HakoniwaCharacterEntry,
  language: string,
): Promise<HakoniwaResidentChange> {
  return requestJson<HakoniwaResidentChange>(
    `${WORLDS}/${worldId}/residents/from-character`,
    jsonInit("POST", { ...entry, language }),
  );
}

export function updateHakoniwaResident(
  worldId: string,
  residentId: string,
  input: HakoniwaResidentInput,
  language: string,
): Promise<HakoniwaResidentChange> {
  return requestJson<HakoniwaResidentChange>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}`,
    jsonInit("PATCH", { ...input, language }),
  );
}

export function removeHakoniwaResident(
  worldId: string,
  residentId: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}${query(language)}`,
    jsonInit("DELETE"),
  );
}

export function greetHakoniwaResident(
  worldId: string,
  residentId: string,
  language: string,
): Promise<HakoniwaGreeting> {
  return requestJson<HakoniwaGreeting>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/greet`,
    jsonInit("POST", { language }),
  );
}

export function generateHakoniwaAvatar(
  worldId: string,
  residentId: string,
  variant: "base" | "dress",
  language: string,
): Promise<HakoniwaImageResult> {
  return requestJson<HakoniwaImageResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/avatar`,
    jsonInit("POST", { variant, language }),
  );
}

export function transformHakoniwaResident(
  worldId: string,
  residentId: string,
  instruction: string,
  language: string,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/transform`,
    jsonInit("POST", { instruction, language }),
  );
}

export function clearHakoniwaTransform(
  worldId: string,
  residentId: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/transform/clear`,
    jsonInit("POST", { language }),
  );
}

export function reapplyHakoniwaTransform(
  worldId: string,
  residentId: string,
  image: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/transform/reapply`,
    jsonInit("POST", { image, language }),
  );
}

export function setHakoniwaFavorite(
  worldId: string,
  eventId: string,
  favorite: boolean,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/events/${encodeURIComponent(eventId)}/favorite`,
    jsonInit("PUT", { favorite, language }),
  );
}
