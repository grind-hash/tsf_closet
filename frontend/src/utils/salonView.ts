/**
 * サロン経営の画面で使う表示用の計算(金額の書式・今週の予約・口コミ・接客の幕・グラフ)。
 * 数値そのものはバックエンドが決め、ここでは並べ方と書式だけを扱う。
 */

import type {
  SalonAchievementUnlocked,
  SalonCloseWeek,
  SalonResult,
  SalonRun,
  SalonVisit,
  SalonWeek,
} from "../apis/salon";
import type { HistoryItem, SessionRequestView } from "../types";

/** 金額。日本語は「300万円」「7.5万円」、英語は「¥3,000,000」 */
export function formatYen(value: number, language: string): string {
  if (language === "ja") {
    const man = value / 10_000;
    return `${man.toLocaleString("ja-JP", { maximumFractionDigits: 1 })}万円`;
  }
  return `¥${value.toLocaleString("en-US")}`;
}

/** 増減を符号付きで書く(+7.5万円 / −10万円 / ±0) */
export function formatSignedYen(value: number, language: string): string {
  if (value === 0) return language === "ja" ? "±0円" : "±¥0";
  const body = formatYen(Math.abs(value), language);
  return value > 0 ? `+${body}` : `−${body}`;
}

/** 評判などの増減(+8 / −3 / ±0) */
export function formatSignedNumber(value: number): string {
  if (value === 0) return "±0";
  return value > 0 ? `+${value}` : `−${Math.abs(value)}`;
}

export function thisWeekVisits(run: SalonRun): SalonVisit[] {
  return run.visits
    .filter((visit) => visit.week === run.week)
    .sort((a, b) => a.slot - b.slot);
}

/** 口コミ(会計済みの来店)。新しい週から並べる */
export function salonReviews(run: SalonRun): SalonVisit[] {
  return run.visits
    .filter((visit) => visit.status === "done" && visit.review)
    .sort((a, b) => b.week - a.week || b.slot - a.slot);
}

export type SalonAct = "counsel" | "styling" | "reveal" | "checkout";

/** 接客画面を開いたときの幕。施術を始めていれば施術から再開する */
export function initialSalonAct(request: SessionRequestView | null): SalonAct {
  return request && request.turns_used > 0 ? "styling" : "counsel";
}

/** お披露目の体験の場面(成人向けの依頼で、施術の後に走らせる行動の手番)か */
export function isExperienceTurn(item: HistoryItem | undefined): boolean {
  return item?.instructionType === "action";
}

/** 最後の施術の手番(体験の場面より前の、仕上がった姿) */
export function lastStyledHistory(
  history: readonly HistoryItem[],
): HistoryItem | undefined {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (!isExperienceTurn(history[index])) return history[index];
  }
  return undefined;
}

export interface SalonCashPoint {
  /** 0 は開店時(開業資金) */
  week: number;
  cash: number;
}

/** 週末の現金の推移。開店時の開業資金を先頭に置く */
export function salonCashSeries(run: SalonRun): SalonCashPoint[] {
  return [
    { week: 0, cash: run.initial_cash },
    ...run.weeks.map((week) => ({ week: week.week, cash: week.cash_end })),
  ];
}

/** グラフの縦軸の目盛り。0 と開業資金を含む範囲を、きりのよい刻みで区切る */
export function salonCashTicks(points: SalonCashPoint[]): number[] {
  const values = points.map((point) => point.cash);
  const min = Math.min(0, ...values);
  const max = Math.max(...values, 1);
  const span = max - min;
  const rough = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step =
    [1, 2, 2.5, 5, 10]
      .map((unit) => unit * magnitude)
      .find((unit) => unit >= rough) ?? 10 * magnitude;
  const ticks: number[] = [];
  for (
    let value = Math.floor(min / step) * step;
    value <= Math.ceil(max / step) * step + step / 2;
    value += step
  ) {
    ticks.push(Math.round(value));
  }
  return ticks;
}

/** 週の締めの演出。full = 閉店から開店まで / short = 数字だけの1枚 / none = 出さない */
export type SalonCutsceneMode = "full" | "short" | "none";

export const SALON_CUTSCENE_MODES: readonly SalonCutsceneMode[] = [
  "full",
  "short",
  "none",
];

/** 週の締めのカットシーンに見せる内容 */
export interface SalonWeekCutscene {
  kind: "week";
  /** 締めた週の帳簿 */
  week: SalonWeek;
  /** 週初めの現金(前週末。第1週は開業資金) */
  cashStart: number;
  /** 週の純収支(売上 − 追加施術 + 本業 − 固定費) */
  cashDelta: number;
  reputationStart: number;
  /** 営業を続けるときの翌週。決算・倒産なら null */
  nextWeek: number | null;
  /** 翌週の予約数 */
  bookings: number;
  /** 前回の姿のまま翌週に来るお客様 */
  regulars: string[];
  result: SalonResult | null;
  achievements: SalonAchievementUnlocked[];
}

/** 締める前の run と、週を締めた応答からカットシーンの内容を組む */
export function buildWeekCutscene(
  before: SalonRun,
  closed: SalonCloseWeek,
): SalonWeekCutscene | null {
  const after = closed.run;
  const week = after.weeks.at(-1);
  if (!week) return null;
  const previous = after.weeks.at(-2);
  const cashStart = previous?.cash_end ?? after.initial_cash;
  // 第1週は開店時の評判が応答に無いので、締める前の評判から今週の接客・お断りの分を戻す
  const reputationStart =
    previous?.reputation_end ??
    Math.min(
      100,
      Math.max(
        0,
        before.reputation -
          before.visits
            .filter(
              (visit) =>
                visit.week === week.week &&
                (visit.status === "done" || visit.status === "declined"),
            )
            .reduce((sum, visit) => sum + visit.reputation_delta, 0),
      ),
    );
  const continuing = after.status === "active";
  const nextVisits = continuing ? thisWeekVisits(after) : [];
  return {
    kind: "week",
    week,
    cashStart,
    cashDelta: week.cash_end - cashStart,
    reputationStart,
    nextWeek: continuing ? after.week : null,
    bookings: nextVisits.filter((visit) => visit.status === "booked").length,
    regulars: nextVisits
      .filter((visit) => visit.returning_look)
      .map((visit) => visit.customer.name),
    result: after.result,
    achievements: closed.achievements,
  };
}

/** 開業(サロンを作った直後)のカットシーンに見せる内容 */
export interface SalonOpeningCutscene {
  kind: "opening";
  name: string;
  /** 開業してすぐの営業週(通常は第1週) */
  week: number;
  totalWeeks: number;
  initialCash: number;
  reputation: number;
  weeklySalary: number;
  weeklyFixedCost: number;
  /** 開業した週の予約数 */
  bookings: number;
}

export type SalonCutsceneScene = SalonWeekCutscene | SalonOpeningCutscene;

/** 作ったばかりの run から開業のカットシーンの内容を組む */
export function buildOpeningCutscene(run: SalonRun): SalonOpeningCutscene {
  return {
    kind: "opening",
    name: run.name,
    week: run.week,
    totalWeeks: run.total_weeks,
    initialCash: run.initial_cash,
    reputation: run.reputation,
    weeklySalary: run.weekly_salary,
    weeklyFixedCost: run.weekly_fixed_cost,
    bookings: thisWeekVisits(run).filter((visit) => visit.status === "booked")
      .length,
  };
}
