/**
 * サロン経営の開店画面で見せる数値(backend/gateway/consts/salon.py と揃える)。
 * 開店後の数値はサロンの応答(initial_cash・weekly_fixed_cost など)を使う。
 */

import type {
  SalonCustomerGender,
  SalonCustomerType,
  SalonDesiredBody,
  SalonDifficulty,
  SalonSeasonLength,
} from "../apis/salon";

/** 来客の種類: お客様の性別と願う体の選択肢 */
export const SALON_CUSTOMER_GENDERS: readonly SalonCustomerGender[] = [
  "any",
  "man",
  "woman",
];
export const SALON_DESIRED_BODIES: readonly SalonDesiredBody[] = [
  "any",
  "female",
  "male",
];
export const SALON_DEFAULT_CUSTOMER_TYPE: SalonCustomerType = {
  customer_gender: "any",
  desired_body: "any",
};

export const SALON_DIFFICULTIES: readonly SalonDifficulty[] = [
  "easy",
  "normal",
  "hard",
];

export const SALON_DEFAULT_DIFFICULTY: SalonDifficulty = "normal";

export const SALON_SEASON_LENGTHS: readonly SalonSeasonLength[] = [
  "short",
  "standard",
];

export const SALON_DEFAULT_SEASON_LENGTH: SalonSeasonLength = "standard";

/** 1 期の週数 */
export const SALON_SEASON_WEEKS: Record<SalonSeasonLength, number> = {
  short: 4,
  standard: 12,
};

/** 期の長さと経営の難易度ごとの開業資金 */
export const SALON_INITIAL_CASH: Record<
  SalonSeasonLength,
  Record<SalonDifficulty, number>
> = {
  standard: { easy: 3_000_000, normal: 2_000_000, hard: 1_500_000 },
  short: { easy: 1_000_000, normal: 600_000, hard: 300_000 },
};

/** 毎週の赤字(固定費 − 本業の収入) */
export const SALON_WEEKLY_NET_COST = 200_000;

/** 予約を断ったときの評判の下がり幅 */
export const SALON_DECLINE_PENALTY = 3;

export const SALON_NAME_MAX_LENGTH = 40;
