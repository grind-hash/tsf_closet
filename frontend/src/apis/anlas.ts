import type { AnlasBalance } from "../types";
import { API_BASE } from "../utils/api";

interface AnlasBalanceResponse {
  fixed_anlas: number | null;
  purchased_anlas: number | null;
  total_anlas: number | null;
}

/**
 * Fetch Anlas balance from the backend API.
 * Returns null if the request fails (e.g., non-NovelAI provider).
 */
export async function fetchAnlasBalance(): Promise<AnlasBalance | null> {
  try {
    const response = await fetch(`${API_BASE}/game/anlas`);
    if (!response.ok) {
      return null;
    }
    const data = (await response.json()) as AnlasBalanceResponse;
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
    };
  } catch {
    return null;
  }
}
