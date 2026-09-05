import type { AnlasBalance, NovelAIUsage } from "../types";
import { API_BASE } from "../utils/api";
import { requestJson } from "../utils/http";

interface AnlasUsageResponse {
  percent: number;
  is_negative?: boolean;
  time_until_next_percent?: number;
}

interface AnlasBalanceResponse {
  fixed_anlas: number | null;
  purchased_anlas: number | null;
  total_anlas: number | null;
  usage?: AnlasUsageResponse | null;
}

/**
 * Parse the snake_case usage payload into camelCase.
 * Returns null when the payload is absent or malformed.
 */
export function parseAnlasUsage(
  usage: AnlasUsageResponse | null | undefined,
): NovelAIUsage | null {
  if (!usage || typeof usage.percent !== "number") {
    return null;
  }
  return {
    percent: usage.percent,
    isNegative: Boolean(usage.is_negative),
    timeUntilNextPercent: usage.time_until_next_percent ?? 0,
  };
}

/**
 * Fetch Anlas balance from the backend API.
 * Returns null if the request fails (e.g., non-NovelAI provider).
 */
export async function fetchAnlasBalance(): Promise<AnlasBalance | null> {
  try {
    const data = await requestJson<AnlasBalanceResponse>(
      `${API_BASE}/game/anlas`,
    );
    if (
      data.fixed_anlas === null ||
      data.purchased_anlas === null ||
      data.total_anlas === null
    ) {
      return null;
    }
    return {
      fixedAnlas: data.fixed_anlas,
      purchasedAnlas: data.purchased_anlas,
      totalAnlas: data.total_anlas,
      usage: parseAnlasUsage(data.usage),
    };
  } catch {
    return null;
  }
}
