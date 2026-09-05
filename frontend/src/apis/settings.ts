/**
 * Self-profile API functions
 * US6 - Self-mode personality profile management
 */

import type { UiLanguage } from "../constants/language";
import { API_BASE } from "../utils/api";
import { jsonInit, requestJson } from "../utils/http";

/**
 * spec 004 (US4): Session-level settings persisted via /api/settings.
 * Mirrors backend `SettingsModel` (subset relevant to the frontend).
 */
export interface Settings {
  /** プロンプト生成時の履歴遡及件数 (5..20, default 10) */
  history_lookback_count: number;
}

export interface SelfProfile {
  display_name: string;
  personality: string;
  reaction_style: string;
  pronoun: string;
  gender: string;
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
  return requestJson<SelfProfile>(
    `${API_BASE}/settings/self-profile/generate`,
    jsonInit("POST", { input_text: inputText }),
    { fallbackMessage: "Failed to generate profile" },
  );
}

/**
 * Save the user's self-profile
 */
export async function saveSelfProfile(
  profile: SelfProfile,
): Promise<SelfProfile> {
  return requestJson<SelfProfile>(
    `${API_BASE}/settings/self-profile`,
    jsonInit("PUT", profile),
    { fallbackMessage: "Failed to save profile" },
  );
}

/**
 * Retrieve the user's self-profile
 */
export async function getSelfProfile(): Promise<SelfProfile | null> {
  const data = await requestJson<SelfProfile | Record<string, never> | null>(
    `${API_BASE}/settings/self-profile`,
    undefined,
    { fallbackMessage: "Failed to fetch self-profile" },
  );
  // Empty object means no profile set
  if (!data || Object.keys(data).length === 0) {
    return null;
  }
  return data as SelfProfile;
}

// ----------------------------------------------------------------
// ユーザー設定 / アプリ設定（SettingsContext から使う）
// ----------------------------------------------------------------

/** GET /api/settings/user の応答（バックエンドの UserSettingsResponse） */
export interface UserSettingsResponse {
  nsfw_mode: boolean;
  difficulty: "easy" | "normal" | "hard";
  bloom_calc_method?: "legacy" | "new";
  feeling_mode?: string;
  gender_congruence_llm_enabled?: boolean;
  language?: UiLanguage;
  novelai_text_model?: string;
  novelai_image_model?: string;
  novelai_curated_image_model?: string;
  tts_enabled?: boolean;
  tts_use_gpu?: boolean;
  tts_engine_dir?: string | null;
  tts_engine_port?: number | null;
  tts_model_dir?: string | null;
  tts_speaker_id?: string | null;
  tts_style_id?: string | null;
  tts_output_format?: "wav";
}

/** PUT /api/settings/user に送る差分（未指定の項目は据え置き） */
export type UserSettingsUpdate = Partial<UserSettingsResponse>;

export async function fetchUserSettings(): Promise<UserSettingsResponse> {
  return requestJson<UserSettingsResponse>(`${API_BASE}/settings/user`);
}

export async function updateUserSettings(
  update: UserSettingsUpdate,
): Promise<void> {
  await requestJson<unknown>(
    `${API_BASE}/settings/user`,
    jsonInit("PUT", update),
  );
}

/** GET /api/settings は `{ settings: {...} }` か設定そのものを返す（旧形式互換） */
export async function fetchAppSettings(): Promise<Partial<Settings>> {
  const data = await requestJson<
    { settings?: Partial<Settings> } | Partial<Settings> | null
  >(`${API_BASE}/settings`);
  const settings =
    data && typeof data === "object" && "settings" in data && data.settings
      ? data.settings
      : data;
  return (settings ?? {}) as Partial<Settings>;
}

export async function updateAppSettings(
  update: Partial<Settings>,
): Promise<void> {
  await requestJson<unknown>(`${API_BASE}/settings`, jsonInit("PUT", update));
}
