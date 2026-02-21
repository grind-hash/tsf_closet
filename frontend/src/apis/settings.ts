/**
 * Self-profile API functions
 * US6 - Self-mode personality profile management
 */

import { API_BASE } from "../utils/api";

export interface SelfProfile {
  personality: string;
  reaction_style: string;
  pronoun: string;
  interests: string[];
  tsf_attitude: string;
  raw_input: string;
}

/**
 * Generate a self-profile from free-form text via LLM
 */
export async function generateSelfProfile(
  inputText: string,
): Promise<SelfProfile> {
  const response = await fetch(
    `${API_BASE}/settings/self-profile/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_text: inputText }),
    },
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to generate profile: ${detail}`);
  }
  return response.json();
}

/**
 * Save the user's self-profile
 */
export async function saveSelfProfile(
  profile: SelfProfile,
): Promise<SelfProfile> {
  const response = await fetch(`${API_BASE}/settings/self-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to save profile: ${detail}`);
  }
  return response.json();
}

/**
 * Retrieve the user's self-profile
 */
export async function getSelfProfile(): Promise<SelfProfile | null> {
  const response = await fetch(`${API_BASE}/settings/self-profile`);
  if (!response.ok) {
    throw new Error("Failed to fetch self-profile");
  }
  const data = await response.json();
  // Empty object means no profile set
  if (!data || Object.keys(data).length === 0) {
    return null;
  }
  return data;
}
