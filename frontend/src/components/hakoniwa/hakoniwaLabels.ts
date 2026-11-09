/** 気分(0〜100)と好感度(-50〜50)を言葉の段階にする */

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

export function affinityLevel(value: number): HakoniwaAffinityLevel {
  if (value <= -25) return "hostile";
  if (value < -5) return "awkward";
  if (value <= 10) return "neutral";
  if (value < 30) return "friendly";
  return "close";
}
