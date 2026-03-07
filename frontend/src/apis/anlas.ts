import { API_BASE } from "../utils/api";
import type { AnlasBalance } from "../types";

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
    const data = await response.json();
    return {
      fixedAnlas: data.fixed_anlas ?? 0,
      purchasedAnlas: data.purchased_anlas ?? 0,
      totalAnlas: data.total_anlas ?? 0,
    };
  } catch {
    return null;
  }
}
