/**
 * AI箱庭モード API
 *
 * 世界(住民・掟・年代記)の作成と、1日進める・掟の切り替え・住民の一言・その場で変身・
 * アバターの生成を扱う。項目名はバックエンドに合わせてスネークケースのまま扱う。
 * 記憶・名残の文はバックエンドが言語ごとに組み立て、段階や物語の名前は表示側で組み立てる。
 */

import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

export type HakoniwaGender = "female" | "male";
export type HakoniwaResidentSource = "preset" | "character" | "custom";
/** 表示中の姿の種類(優先順位は 変身 → 複合の姿 → 掟の姿 → 世界のメモの姿 → ドレス → 通常) */
export type HakoniwaLookKind =
  | "transform"
  | "combo"
  | "rule"
  | "memo"
  | "dress"
  | "base";

export interface HakoniwaLine {
  /** 話す住民の id */
  speaker: string;
  text: string;
}

export interface HakoniwaWebSearch {
  query: string;
  retrieved_at: string;
  status: "used" | "unused" | "no_results" | "failed" | "blocked";
  sources: { title: string; url: string }[];
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
  web_search?: HakoniwaWebSearch | null;
  /** transform(変身の出来事)・directed(指示した出来事)など */
  kind?: string | null;
  change_text?: string | null;
  /** 指示した出来事(directed)の指示文 */
  instruction?: string | null;
  /** エリアの外で起きた出来事の場所(浴室・商店街など)。無ければ area で起きた */
  location?: string | null;
  /** 続きとして起こした出来事の、元になった出来事の id */
  continues?: string | null;
  favorite: boolean;
  /** 出来事の起きた場所(エリア id) */
  area: string;
  scene_image?: string | null;
  scene_image_url?: string | null;
  /** 場面絵をすすめる理由(生成済みなら null) */
  scene_suggestion?: HakoniwaSceneSuggestion | null;
  /** 続きを描いた物語の弧 */
  arc_id?: string | null;
  arc_climax?: boolean | null;
  /** 出来事を見せる間の BGM のキー(LLM が選んだときだけ。無ければふだんの曲) */
  bgm?: string | null;
}

export type HakoniwaAdaptationKind = "swap" | "transform";

/** 変身・入れ替わりへの適応(本人は 0 戸惑い〜3 受容、世界の側は 0 驚き〜3 定着) */
export interface HakoniwaAdaptation {
  kind: HakoniwaAdaptationKind;
  stage: number;
}

export interface HakoniwaRemnant {
  kind: HakoniwaAdaptationKind;
  text: string;
  days_left: number;
}

export interface HakoniwaMemory {
  day: number;
  kind: string;
  text: string;
}

export type HakoniwaDissonanceStage =
  | "stillness"
  | "stirring"
  | "probing"
  | "confrontation";

export interface HakoniwaDissonance {
  enabled: boolean;
  value: number;
  stage: HakoniwaDissonanceStage;
  /** 対面を経て、住民が書き手の存在を知っている */
  acknowledged: boolean;
  next_stage: HakoniwaDissonanceStage | null;
  remaining: number | null;
}

export type HakoniwaArcKind = "investigation" | "swap" | "transform" | "bond";

export interface HakoniwaStoryArc {
  id: string;
  kind: HakoniwaArcKind;
  resident_ids: string[];
  progress: number;
  beats_to_climax: number;
  status: "active" | "closed";
  started_day: number;
  closed_day: number | null;
  close_reason: "climax" | "resolved" | "faded" | null;
}

export interface HakoniwaSceneSuggestion {
  level: "normal" | "strong";
  reason: string;
}

export interface HakoniwaSlot {
  x: number;
  y: number;
  furniture_id: string | null;
}

export interface HakoniwaArea {
  id: string;
  name: string;
  background_url: string;
  slots: HakoniwaSlot[];
}

export interface HakoniwaFurniture {
  id: string;
  name: string;
  url: string;
}

export type HakoniwaThemePreset =
  | "swap"
  | "dress"
  | "dissonance"
  | "transform"
  | "free";

/** 実験テーマ。自由文(text)があれば自由文、無ければプリセット */
export interface HakoniwaTheme {
  preset_id: HakoniwaThemePreset | null;
  text: string;
}

/** 実験テーマの進み具合(数値だけ。文は表示側で組み立てる) */
export interface HakoniwaThemeProgress {
  preset_id: HakoniwaThemePreset | null;
  text: string;
  day: number;
  events: number;
  swap_days?: number;
  swapping?: boolean;
  dress_days?: number;
  dress_target?: number;
  dissonance?: number;
  dissonance_stage?: HakoniwaDissonanceStage;
  acknowledged?: boolean;
  remaining?: number;
  dissonance_enabled?: boolean;
  transform_count?: number;
  transformed_now?: number;
}

export interface HakoniwaAchievementUnlocked {
  achievement_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
}

/** おまかせの住民(作成画面で組む住民の定義) */
/**
 * 住民がほかの住民を呼ぶときのくせ(話す側に付く)。相手の名前・性別・年の差から
 * 呼び方を作る(かなり年上の相手には さん を付ける)
 */
export const HAKONIWA_ADDRESS_STYLES = [
  "given_chan",
  "given_san",
  "given",
  "family_san",
  "family",
] as const;
export type HakoniwaAddressStyle = (typeof HAKONIWA_ADDRESS_STYLES)[number];

export interface HakoniwaRandomResident {
  name: string;
  gender: "female" | "male";
  age: string;
  job: string;
  personality: string;
  pronoun: string;
  address_style: HakoniwaAddressStyle;
  appearance_text: string;
  base_tags: string;
}

export interface HakoniwaRandomResidentsResult {
  residents: HakoniwaRandomResident[];
  /** llm: テキストモデルで作った / template: 語彙の組み合わせ */
  source: "llm" | "template";
  cost_usd: number | null;
}

/** 1日のまとめ。文は表示側で言語ごとに組み立てる */
export interface HakoniwaDigest {
  day: number;
  highlight: {
    event_id: string;
    title: string;
    reason:
      | "confrontation"
      | "arc_climax"
      | "transform"
      | "movement"
      | "trio"
      | "center";
    participants: string[];
  } | null;
  changes: HakoniwaDigestChange[];
  hint: HakoniwaDigestHint;
  /** 本人の適応が進んだ住民(stage は進んだ先) */
  adaptations?: { id: string; kind: HakoniwaAdaptationKind; stage: number }[];
  /** 周囲の適応が進んだ姿 */
  world_adaptations?: {
    ids: string[];
    kind: HakoniwaAdaptationKind;
    stage: number;
  }[];
  arcs?: HakoniwaDigestArc[];
  /** その日に効かせた介入 */
  intervention?: HakoniwaInterventionChoice | null;
  /** 実験テーマの進み具合(テーマ無しは null) */
  theme?: HakoniwaThemeProgress | null;
  /** 世界の違和感の変化(違和感を使わない世界では null) */
  dissonance?: {
    from: number;
    to: number;
    from_stage: HakoniwaDissonanceStage;
    to_stage: HakoniwaDissonanceStage;
    acknowledged: boolean;
    next_stage: HakoniwaDissonanceStage | null;
    remaining: number | null;
  } | null;
}

export interface HakoniwaDigestArc {
  id: string;
  kind: HakoniwaArcKind;
  ids: string[];
  progress: number;
  beats: number;
  status: "started" | "active" | "climax" | "faded" | "resolved";
}

export type HakoniwaDigestChange =
  | { type: "affinity"; ids: string[]; delta: number; value: number }
  | { type: "mood"; id: string; delta: number; mood: number };

export type HakoniwaDigestHint =
  | { type: "acknowledged" }
  | {
      type: "dissonance_near";
      stage: HakoniwaDissonanceStage;
      remaining: number;
    }
  | {
      type: "arc_near_climax";
      arc_id: string;
      kind: HakoniwaArcKind;
      ids: string[];
    }
  | { type: "swap"; ids: string[] }
  | { type: "near_close"; ids: string[]; value: number; remaining: number }
  | { type: "no_rules" }
  | { type: "more_rules"; remaining: number }
  | { type: "generic"; index: number };

export interface HakoniwaTransformation {
  description: string;
  tags: string;
  image: string;
  image_url: string | null;
  day: number;
  /** "reality" は住民の改変で変えた姿(本人も周りも昔からそうだと受け止める) */
  kind?: string | null;
}

/** 住民の改変: その住民についての世界の常識 */
export interface HakoniwaReality {
  id: string;
  text: string;
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
  address_style: HakoniwaAddressStyle;
  /** ほかの住民(id)をふだん何と呼ぶか(台詞で使う呼び方) */
  addresses: Record<string, string>;
  /** プレイヤーが書いた外見の説明(画像タグとは別に持つ) */
  appearance_text: string;
  /** 通常の姿の画像タグ(そのまま姿の生成に使う) */
  base_tags: string;
  dress_text: string;
  /** ドレス姿の画像タグ。空ならドレス姿を生成するときにいつもの姿から考える */
  dress_tags: string;
  mood: number;
  affinities: Record<string, number>;
  transformation: HakoniwaTransformation | null;
  transformation_history: HakoniwaTransformation[];
  /** 住民の改変(古い順) */
  realities?: HakoniwaReality[];
  swapped_with: string | null;
  /** いま表示する姿(入れ替わり中は相手の姿) */
  display_avatar_url: string | null;
  display_kind: HakoniwaLookKind;
  display_owner_id: string;
  own_avatar_url: string | null;
  avatar_url: string | null;
  dress_avatar_url: string | null;
  /** いまいる場所(エリア id) */
  current_area: string;
  adaptation: HakoniwaAdaptation | null;
  /** いまの姿への周囲(世界)の適応 */
  world_adaptation: HakoniwaAdaptation | null;
  remnant: HakoniwaRemnant | null;
  /** 覚えている大きな出来事(古い順) */
  memories: HakoniwaMemory[];
}

/** 掟の姿・複合の姿の生成状況 */
export interface HakoniwaLookStatus {
  /** 今の見た目で生成済みの住民の数 */
  ready: number;
  /** 見た目を変える前に生成した姿の住民の数 */
  stale: number;
  total: number;
  /** まだ生成していないか、見た目を変える前の姿の住民の id(住民の並び順) */
  pending: string[];
}

export interface HakoniwaRuleCard {
  id: string;
  name: string;
  description: string;
  custom: boolean;
  active: boolean;
  /** 自作の掟の見た目の説明(プレイヤーが書いた文。タグを作るときの元) */
  appearance_text?: string | null;
  /** 自作の掟の見た目のタグ(そのまま姿の生成に使う)。空なら見た目を変えない */
  appearance_tags?: string | null;
  /** 掟の姿で住民の体をこの性別にする(自作の掟)。null は住民それぞれのまま */
  body_gender?: HakoniwaGender | null;
  look?: HakoniwaLookStatus | null;
  /** 既定の掟どうしの相性 */
  synergies?: HakoniwaSynergy[] | null;
}

export interface HakoniwaSynergy {
  /** 組み合わせる相手の掟 */
  with_id: string;
  label: string;
  hint: string;
  /** 両方とも有効で、相性が発動している */
  active: boolean;
}

export type HakoniwaInterventionChoice =
  | "watch"
  | "nudge"
  | "rewrite"
  | "arc_boost"
  | "adaptation_care"
  | "dissonance_push";

export interface HakoniwaTouchResult {
  world: HakoniwaWorld;
  resident_id: string;
  part: HakoniwaTouchPart;
  text: string;
  source: string;
  mood_delta: number;
  cost_usd: number | null;
}

export type HakoniwaTouchPart = "head" | "chest" | "lower";

export interface HakoniwaChatEntry {
  role: "player" | "resident" | "system";
  text: string;
  kind?: string | null;
  source?: string | null;
  web_search?: HakoniwaWebSearch | null;
}

export interface HakoniwaChatResult {
  /** 確認待ちで何も変えていないときは null */
  world: HakoniwaWorld | null;
  reply: HakoniwaChatEntry | null;
  history: HakoniwaChatEntry[];
  alteration: {
    action: "transform" | "clear" | "none";
    instruction: string;
    executed: boolean;
    /** 画像の生成の前に確認が要るので、まだ実行していない */
    needs_confirmation: boolean;
  };
  /** 会話からの変身で年代記に積んだ出来事 */
  new_events: HakoniwaEvent[];
  cost_usd: number | null;
}

/** 見た目の掟が2つ以上重なっているときの複合の姿 */
export interface HakoniwaComboLook extends HakoniwaLookStatus {
  rule_ids: string[];
  names: string[];
  includes_dress: boolean;
}

/** 世界のメモが住民全員に与える姿と、その生成状況 */
export interface HakoniwaMemoLook extends HakoniwaLookStatus {
  tags: string;
  /** メモが定める体の性別(null は住民それぞれのまま) */
  body_gender: HakoniwaGender | null;
}

export interface HakoniwaMemoLookPlanResult {
  world: HakoniwaWorld;
  /** 世界のメモが住民全員の姿を変えるか */
  changes_look: boolean;
  cost_usd: number | null;
}

export interface HakoniwaLookResult {
  world: HakoniwaWorld;
  generated: number;
  failed: number;
  cost_usd: number | null;
}

export interface HakoniwaCustomRuleInput {
  name: string;
  text: string;
  appearance_text: string;
  /** 見た目のタグ(そのまま保存する)。空なら見た目を変えない */
  appearance_tags: string;
  /** 掟の姿の体の性別。null は住民それぞれのまま(保存のたびに送る) */
  body_gender: HakoniwaGender | null;
}

export interface HakoniwaWorld {
  /** この世界でWeb検索を使うか。未設定はOFF */
  web_search_enabled?: boolean;
  /** サーバー側のTavilyのAPIキー設定状況 */
  web_search_configured?: boolean;
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
  areas: HakoniwaArea[];
  /** 出来事の場所(場面の絵の背景)。エリアとエリアの外の場所 */
  locations: HakoniwaLocation[];
  furniture_catalog: HakoniwaFurniture[];
  last_digest: HakoniwaDigest | null;
  dissonance: HakoniwaDissonance;
  /** 進行中と、最近閉じた物語の弧 */
  story_arcs: HakoniwaStoryArc[];
  combo_look: HakoniwaComboLook | null;
  /** 世界のメモが住民全員に与える姿(メモが姿を変えていなければ null) */
  memo_look?: HakoniwaMemoLook | null;
  /** いまの世界のメモが姿に関わるかを、もう確かめたか */
  memo_look_planned?: boolean;
  /** 世界のメモ(全生成に最優先の指示として載せる) */
  world_memo: string;
  /** 住民がプレイヤーを呼ぶときの名前(空なら名前で呼ばない) */
  player_name?: string;
  /** この応答で新しく達成した観察記録(実績)。通知に使う */
  new_achievements?: HakoniwaAchievementUnlocked[];
  /** 実験テーマ(テーマ無しは null) */
  experiment_theme?: HakoniwaTheme | null;
  intervention: {
    /** 次の「1日進める」で効かせる介入 */
    selected: HakoniwaInterventionChoice;
    /** いま選べる介入(見守る・後押し・書き換え) */
    choices: HakoniwaInterventionChoice[];
  };
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

/** 掟を切り替えた直後の住民の反応(定型文。年代記には残らない) */
export interface HakoniwaRuleReaction {
  card_id: string;
  active: boolean;
  /** 反応を見せる場所(話し手のいる場所) */
  area: string | null;
  lines: { resident_id: string; text: string }[];
}

export interface HakoniwaDayResult {
  world: HakoniwaWorld;
  new_events: HakoniwaEvent[];
  digest?: HakoniwaDigest | null;
  /** 掟の切り替えのときだけ */
  reaction?: HakoniwaRuleReaction | null;
  cost_usd: number | null;
}

export interface HakoniwaResidentChange {
  world: HakoniwaWorld;
  resident_id: string;
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
  address_style: HakoniwaAddressStyle;
  /** いつもの姿の画像タグ(必須。そのまま保存する) */
  base_tags: string;
  /** ドレス姿の画像タグ。空ならドレス姿を生成するときにいつもの姿から考える */
  dress_tags: string;
}

/** 掟の見た目のタグを作る元。本文か見た目の説明のどちらかが要る */
export interface HakoniwaRuleLookTagsInput {
  name: string;
  text: string;
  appearance_text: string;
}

/** 住民の姿のタグを作る元(dress ならドレス姿) */
export interface HakoniwaResidentTagsInput {
  appearance_text: string;
  gender: HakoniwaGender;
  dress: boolean;
}

export interface HakoniwaTagsResult {
  tags: string;
  cost_usd: number | null;
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
  dissonance_enabled: boolean;
  custom_residents?: HakoniwaRandomResident[];
  experiment_theme?: HakoniwaTheme | null;
}): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(WORLDS, jsonInit("POST", body));
}

/** おまかせの住民を組む(世界は変えない)。1人の入れ替えは count=1 */
export function generateHakoniwaRandomResidents(
  count: number,
  excludeNames: string[],
  language: string,
): Promise<HakoniwaRandomResidentsResult> {
  return requestJson<HakoniwaRandomResidentsResult>(
    `${BASE}/random-residents`,
    jsonInit("POST", { count, exclude_names: excludeNames, language }),
  );
}

/** 掟の見た目のタグを作る(保存はしない) */
export function makeHakoniwaRuleLookTags(
  input: HakoniwaRuleLookTagsInput,
  language: string,
): Promise<HakoniwaTagsResult> {
  return requestJson<HakoniwaTagsResult>(
    `${BASE}/tags/rule-look`,
    jsonInit("POST", { ...input, language }),
  );
}

/** 住民の姿のタグを作る(保存はしない) */
export function makeHakoniwaResidentTags(
  input: HakoniwaResidentTagsInput,
  language: string,
): Promise<HakoniwaTagsResult> {
  return requestJson<HakoniwaTagsResult>(
    `${BASE}/tags/resident`,
    jsonInit("POST", { ...input, language }),
  );
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

/** 世界の設定。指定しなかった項目は変えない */
export function updateHakoniwaSettings(
  worldId: string,
  changes: {
    web_search_enabled?: boolean;
    image_model?: string;
    dissonance_enabled?: boolean;
    world_memo?: string;
    /** 両方空でテーマ無し */
    experiment_theme?: HakoniwaTheme;
    /** 空なら名前で呼ばない */
    player_name?: string;
  },
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/settings`,
    jsonInit("PATCH", { ...changes, language }),
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

/** 掟の切り替え。違和感が到達点に達すると、対面の出来事が new_events に入る */
/** areaId はいま見ている場所(切り替え直後の反応の話し手をそこから選ぶ) */
export function toggleHakoniwaRule(
  worldId: string,
  cardId: string,
  active: boolean,
  language: string,
  areaId: string | null = null,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/rules/${encodeURIComponent(cardId)}`,
    jsonInit("PUT", { active, language, area_id: areaId }),
  );
}

export function addHakoniwaCustomRule(
  worldId: string,
  rule: HakoniwaCustomRuleInput,
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
  rule: HakoniwaCustomRuleInput,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/custom-rules/${encodeURIComponent(ruleId)}`,
    jsonInit("PATCH", { ...rule, language }),
  );
}

/** 掟の姿を住民の人数分生成する(regenerate でなければ、まだの住民だけ) */
export function generateHakoniwaRuleLook(
  worldId: string,
  ruleId: string,
  regenerate: boolean,
  language: string,
  residentId?: string,
): Promise<HakoniwaLookResult> {
  return requestJson<HakoniwaLookResult>(
    `${WORLDS}/${worldId}/custom-rules/${encodeURIComponent(ruleId)}/look`,
    jsonInit("POST", {
      regenerate,
      language,
      resident_id: residentId ?? null,
    }),
  );
}

/** いま重なっている見た目の掟を合わせた、複合の姿を住民の人数分生成する */
export function generateHakoniwaComboLook(
  worldId: string,
  regenerate: boolean,
  language: string,
  residentId?: string,
): Promise<HakoniwaLookResult> {
  return requestJson<HakoniwaLookResult>(
    `${WORLDS}/${worldId}/combo-look`,
    jsonInit("POST", {
      regenerate,
      language,
      resident_id: residentId ?? null,
    }),
  );
}

/** 世界のメモが住民全員の姿を変えるかを確かめる(同じメモで確かめ済みなら LLM を呼ばない) */
export function planHakoniwaMemoLook(
  worldId: string,
  language: string,
): Promise<HakoniwaMemoLookPlanResult> {
  return requestJson<HakoniwaMemoLookPlanResult>(
    `${WORLDS}/${worldId}/memo-look/plan`,
    jsonInit("POST", { language }),
  );
}

/** 世界のメモの姿を生成する(residentId ならその1人) */
export function generateHakoniwaMemoLook(
  worldId: string,
  regenerate: boolean,
  language: string,
  residentId?: string,
): Promise<HakoniwaLookResult> {
  return requestJson<HakoniwaLookResult>(
    `${WORLDS}/${worldId}/memo-look`,
    jsonInit("POST", {
      regenerate,
      language,
      resident_id: residentId ?? null,
    }),
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

/** 住民の改変(その住民についての世界の常識の書き換え)。changeLook なら姿も生成する */
export function alterHakoniwaReality(
  worldId: string,
  residentId: string,
  instruction: string,
  changeLook: boolean,
  language: string,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/realities`,
    jsonInit("POST", { instruction, change_look: changeLook, language }),
  );
}

/** 住民の改変を1件消す(その改変で変えた姿がいまの姿なら、元の姿に戻る) */
export function removeHakoniwaReality(
  worldId: string,
  residentId: string,
  realityId: string,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/realities/${encodeURIComponent(realityId)}${query(language)}`,
    jsonInit("DELETE"),
  );
}

export interface HakoniwaLocation {
  id: string;
  name: string;
  /** ADV の背景にする同梱の画像(場面の絵が無いとき) */
  background_url?: string | null;
}

/** 指示した出来事の巻き込み方: 本人だけ / 選んだ住民と / 同じ部屋の住民と */
export type HakoniwaEventScope = "solo" | "selected" | "room";

export interface HakoniwaDirectedEventInput {
  instruction: string;
  scope: HakoniwaEventScope;
  /** scope が selected のときに一緒に出る住民の id(最大2人) */
  partnerIds: string[];
  /** 出来事の場所の id(null ならおまかせ) */
  location: string | null;
}

export function createHakoniwaDirectedEvent(
  worldId: string,
  residentId: string,
  input: HakoniwaDirectedEventInput,
  language: string,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/event`,
    jsonInit("POST", {
      instruction: input.instruction,
      scope: input.scope,
      partner_ids: input.scope === "selected" ? input.partnerIds : [],
      location: input.location,
      language,
    }),
  );
}

/** 今日の出来事の続きを指示して起こす(参加者と場所は元の場面のまま) */
export function continueHakoniwaEvent(
  worldId: string,
  eventId: string,
  instruction: string,
  language: string,
): Promise<HakoniwaDayResult> {
  return requestJson<HakoniwaDayResult>(
    `${WORLDS}/${worldId}/events/${encodeURIComponent(eventId)}/continue`,
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

export function placeHakoniwaFurniture(
  worldId: string,
  areaId: string,
  slot: number,
  furnitureId: string | null,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/furniture`,
    jsonInit("PUT", {
      area_id: areaId,
      slot,
      furniture_id: furnitureId,
      language,
    }),
  );
}

export function generateHakoniwaSceneImage(
  worldId: string,
  eventId: string,
  language: string,
): Promise<HakoniwaImageResult> {
  return requestJson<HakoniwaImageResult>(
    `${WORLDS}/${worldId}/events/${encodeURIComponent(eventId)}/scene-image`,
    jsonInit("POST", { language }),
  );
}

export interface HakoniwaEventLookPlan {
  world: HakoniwaWorld;
  /** 出来事の結果として姿が変わる住民(誰も変わらなければ空) */
  changes: { resident_id: string; description: string }[];
  cost_usd: number | null;
}

/** 出来事の結果として姿が変わった住民と、変化後の姿を決める(画像は作らない) */
export function planHakoniwaEventLooks(
  worldId: string,
  eventId: string,
  language: string,
): Promise<HakoniwaEventLookPlan> {
  return requestJson<HakoniwaEventLookPlan>(
    `${WORLDS}/${worldId}/events/${encodeURIComponent(eventId)}/looks/plan`,
    jsonInit("POST", { language }),
  );
}

/** 出来事で決めた変化後の姿を、1人ぶん生成して変身として付ける */
export function applyHakoniwaEventLook(
  worldId: string,
  eventId: string,
  residentId: string,
  language: string,
): Promise<HakoniwaImageResult> {
  return requestJson<HakoniwaImageResult>(
    `${WORLDS}/${worldId}/events/${encodeURIComponent(eventId)}/looks/${encodeURIComponent(residentId)}`,
    jsonInit("POST", { language }),
  );
}

/** 次の「1日進める」で効かせる介入を選ぶ(進めるまでは選び直せる) */
export function setHakoniwaIntervention(
  worldId: string,
  choice: HakoniwaInterventionChoice,
  language: string,
): Promise<HakoniwaWorld> {
  return requestJson<HakoniwaWorld>(
    `${WORLDS}/${worldId}/intervention`,
    jsonInit("PUT", { choice, language }),
  );
}

/** 住民の立ち絵に触れる(年代記には残らない) */
export function touchHakoniwaResident(
  worldId: string,
  residentId: string,
  part: HakoniwaTouchPart,
  language: string,
): Promise<HakoniwaTouchResult> {
  return requestJson<HakoniwaTouchResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/touch`,
    jsonInit("POST", { part, language }),
  );
}

export async function fetchHakoniwaChat(
  worldId: string,
  residentId: string,
): Promise<HakoniwaChatEntry[]> {
  const data = await requestJson<{ history: HakoniwaChatEntry[] }>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/chat`,
  );
  return data.history ?? [];
}

/**
 * 住民と会話する。変身の指示で allowImage が偽なら実行せず needs_confirmation を返すので、
 * 確認のあと confirmedInstruction を付けて送り直す。
 */
export function chatHakoniwaResident(
  worldId: string,
  residentId: string,
  body: {
    message: string;
    allow_image: boolean;
    confirmed_instruction?: string;
  },
  language: string,
): Promise<HakoniwaChatResult> {
  return requestJson<HakoniwaChatResult>(
    `${WORLDS}/${worldId}/residents/${encodeURIComponent(residentId)}/chat`,
    jsonInit("POST", { ...body, language }),
  );
}
