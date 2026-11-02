/**
 * サロン経営モード API
 *
 * 接客の手番は通常の /game/play/stream と依頼の API で進め、ここでは開店・予約・
 * 接客の開始・会計・週の締めを扱う。数値はすべてバックエンドが決める。
 */

import type { SessionRequestView } from "../types";
import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

export type SalonDifficulty = "easy" | "normal" | "hard";
export type SalonRunStatus = "active" | "completed" | "bankrupt";
export type SalonVisitStatus = "booked" | "serving" | "done" | "declined";

export interface SalonCustomer {
  /** template(同梱) / custom(保存済みカスタム) / preset(キャラクター画面のキャラ) */
  source: "template" | "custom" | "preset";
  id: string;
  name: string;
}

export interface SalonVisit {
  id: string;
  week: number;
  slot: number;
  customer: SalonCustomer;
  session_id: string | null;
  status: SalonVisitStatus;
  satisfaction: number | null;
  fulfilled: boolean;
  payment: number;
  reputation_delta: number;
  review: string | null;
  /** このお客様の何回目の来店か */
  visit_number: number;
  previous_review: string | null;
  /** 願いを叶え、施術した姿のまま帰った(翌週もこの姿で来る) */
  kept_look: boolean;
  /** 前回持ち帰った姿のまま来店する予約 */
  returning_look: boolean;
  /** 過激施術のお披露目で体験まで描けたときの満足度への加点(satisfaction に含む) */
  experience_bonus: number;
  /** 資金で足した施術の代金(購入時に現金から引いている) */
  extra_cost: number;
}

/** 締めた週の収支 */
export interface SalonWeek {
  week: number;
  revenue: number;
  /** 追加施術の代金の合計(古い週には無い) */
  extra_cost?: number;
  salary: number;
  fixed_cost: number;
  served: number;
  declined: number;
  cash_end: number;
  reputation_end: number;
}

export interface SalonResult {
  outcome: "success" | "partial" | "bankrupt";
  cash: number;
  profit?: number | null;
}

export interface SalonRun {
  id: string;
  name: string;
  status: SalonRunStatus;
  week: number;
  total_weeks: number;
  cash: number;
  reputation: number;
  difficulty: SalonDifficulty;
  initial_cash: number;
  /** 過激施術(成人向けの依頼)。NSFW モードが OFF の間は効かない */
  sensitive: boolean;
  weekly_fixed_cost: number;
  weekly_salary: number;
  base_price: number;
  turn_limit: number;
  question_limit: number;
  /** 資金で足す施術1手の値段と、来店1回につき足せる手数 */
  extra_turn_price: number;
  extra_turns_max: number;
  visits: SalonVisit[];
  weeks: SalonWeek[];
  result: SalonResult | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SalonVisitStart {
  session_id: string;
  request: SessionRequestView | null;
  run: SalonRun;
  cost_usd: number | null;
}

export interface SalonExtraTurn {
  run: SalonRun;
  request: SessionRequestView | null;
}

export interface SalonCheckout {
  run: SalonRun;
  visit: SalonVisit;
  cost_usd: number | null;
}

/** 決算で解除された実績(手番の achievement イベントと同じ形) */
export interface SalonAchievementUnlocked {
  achievement_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
}

export interface SalonCloseWeek {
  run: SalonRun;
  achievements: SalonAchievementUnlocked[];
}

const BASE = `${API_BASE}/salon/runs`;

export async function fetchSalonRuns(): Promise<SalonRun[]> {
  const data = await requestJson<{ runs?: SalonRun[] }>(BASE, undefined, {
    fallbackMessage: "サロンの一覧を取得できませんでした",
  });
  return data.runs ?? [];
}

export function createSalonRun(
  name: string,
  difficulty: SalonDifficulty,
  sensitive: boolean,
): Promise<SalonRun> {
  return requestJson<SalonRun>(
    BASE,
    jsonInit("POST", { name, difficulty, sensitive }),
    { fallbackMessage: "開店できませんでした" },
  );
}

export function fetchSalonRun(runId: string): Promise<SalonRun> {
  return requestJson<SalonRun>(`${BASE}/${runId}`, undefined, {
    fallbackMessage: "サロンを取得できませんでした",
  });
}

/** オーナー室の設定を変える。依頼は接客の開始時に作るので、次の接客から効く */
export function updateSalonRunSettings(
  runId: string,
  settings: { sensitive: boolean },
): Promise<SalonRun> {
  return requestJson<SalonRun>(
    `${BASE}/${runId}/settings`,
    jsonInit("PATCH", settings),
    { fallbackMessage: "設定を変更できませんでした" },
  );
}

export async function deleteSalonRun(runId: string): Promise<void> {
  await requestJson<void>(`${BASE}/${runId}`, jsonInit("DELETE"), {
    fallbackMessage: "サロンを削除できませんでした",
  });
}

/** 資金を払って施術を1手足す(手数を使い切った接客中の来店だけ) */
export function buySalonExtraTurn(
  runId: string,
  visitId: string,
): Promise<SalonExtraTurn> {
  return requestJson<SalonExtraTurn>(
    `${BASE}/${runId}/visits/${visitId}/extra-turn`,
    jsonInit("POST"),
    { fallbackMessage: "追加の施術を始められませんでした" },
  );
}

export function startSalonVisit(
  runId: string,
  visitId: string,
  language: string,
): Promise<SalonVisitStart> {
  return requestJson<SalonVisitStart>(
    `${BASE}/${runId}/visits/${visitId}/start`,
    jsonInit("POST", { language }),
    { fallbackMessage: "接客を始められませんでした" },
  );
}

export function checkoutSalonVisit(
  runId: string,
  visitId: string,
  language: string,
): Promise<SalonCheckout> {
  return requestJson<SalonCheckout>(
    `${BASE}/${runId}/visits/${visitId}/checkout`,
    jsonInit("POST", { language }),
    { fallbackMessage: "会計できませんでした" },
  );
}

export function declineSalonVisit(
  runId: string,
  visitId: string,
): Promise<SalonRun> {
  return requestJson<SalonRun>(
    `${BASE}/${runId}/visits/${visitId}/decline`,
    jsonInit("POST"),
    { fallbackMessage: "予約を断れませんでした" },
  );
}

export function closeSalonWeek(runId: string): Promise<SalonCloseWeek> {
  return requestJson<SalonCloseWeek>(
    `${BASE}/${runId}/close-week`,
    jsonInit("POST"),
    { fallbackMessage: "週を締められませんでした" },
  );
}
