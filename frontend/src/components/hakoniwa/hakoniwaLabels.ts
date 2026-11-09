import type { TFunction } from "i18next";
import type { HakoniwaArcKind } from "../../apis/hakoniwa";

/** 気分(0〜100)と好感度(-50〜50)、適応の段階、物語の題名を言葉にする */

export type HakoniwaMoodLevel = "great" | "good" | "normal" | "down" | "low";
export type HakoniwaAffinityLevel =
  | "hostile"
  | "awkward"
  | "neutral"
  | "friendly"
  | "close";

export function moodLevel(mood: number): HakoniwaMoodLevel {
  if (mood >= 80) return "great";
  if (mood >= 60) return "good";
  if (mood >= 40) return "normal";
  if (mood >= 20) return "down";
  return "low";
}

/** 本人の適応の段階(0〜3)の i18n キー */
export const ADAPTATION_STAGE_KEYS = [
  "bewildered",
  "trial",
  "used",
  "accepted",
] as const;
/** 周囲(世界)の適応の段階(0〜3)の i18n キー */
export const WORLD_STAGE_KEYS = [
  "surprise",
  "used",
  "normal",
  "settled",
] as const;

export function adaptationStageKey(stage: number) {
  return ADAPTATION_STAGE_KEYS[Math.max(0, Math.min(3, stage))] ?? "bewildered";
}

export function worldStageKey(stage: number) {
  return WORLD_STAGE_KEYS[Math.max(0, Math.min(3, stage))] ?? "surprise";
}

/** 物語の弧の題名(担い手の名前を入れる) */
export function arcTitle(
  t: TFunction,
  kind: HakoniwaArcKind,
  ids: string[],
  nameOf: (id: string) => string,
): string {
  return t(`hakoniwa.story.arcTitle.${kind}`, {
    a: nameOf(ids[0] ?? ""),
    b: nameOf(ids[1] ?? ""),
  });
}

export function affinityLevel(value: number): HakoniwaAffinityLevel {
  if (value <= -25) return "hostile";
  if (value < -5) return "awkward";
  if (value <= 10) return "neutral";
  if (value < 30) return "friendly";
  return "close";
}
