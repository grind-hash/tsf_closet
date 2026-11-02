/**
 * サロン経営の開店画面で見せる数値(backend/gateway/consts/salon.py と揃える)。
 * 開店後の数値はサロンの応答(initial_cash・weekly_fixed_cost など)を使う。
 */

import type { SalonDifficulty } from "../apis/salon";

export const SALON_DIFFICULTIES: readonly SalonDifficulty[] = [
  "easy",
  "normal",
  "hard",
];

export const SALON_DEFAULT_DIFFICULTY: SalonDifficulty = "normal";

/** 経営の難易度ごとの開業資金 */
export const SALON_DIFFICULTY_INITIAL_CASH: Record<SalonDifficulty, number> = {
  easy: 3_000_000,
  normal: 2_000_000,
  hard: 1_500_000,
};

export const SALON_TOTAL_WEEKS = 12;

/** 毎週の赤字(固定費 − 本業の収入) */
export const SALON_WEEKLY_NET_COST = 200_000;

/** 予約を断ったときの評判の下がり幅 */
export const SALON_DECLINE_PENALTY = 3;

export const SALON_NAME_MAX_LENGTH = 40;
