/**
 * Multi-character persistence API client (spec 005).
 *
 * Targets the /api/game/* endpoints exposed by `character_router.py`.
 * All field names follow the snake_case convention from the backend per
 * AGENTS.md (frontend types may use snake_case when mirroring the API).
 */

import {
  CHARACTER_PRESET,
  CHARACTER_PRESETS,
  CHARACTERS_FROM_PRESET,
  SESSION_CHARACTER,
  SESSION_CHARACTERS,
  SESSION_CHARACTERS_ENSURE_PROTAGONIST,
} from "../constants/apiEndpoint";
import type {
  CharacterPosition,
  CharacterPreset,
  SessionCharacter,
} from "../types";
import { requestJson } from "../utils/http";

/** JSON ヘッダーを既定で付ける薄いラッパー（エラー解釈は utils/http に委ねる） */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  return requestJson<T>(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

// ---------------------------------------------------------------------------
// Session-scoped characters
// ---------------------------------------------------------------------------

export interface SessionCharacterListResponse {
  characters: SessionCharacter[];
}

export async function listSessionCharacters(
  sessionId: string,
): Promise<SessionCharacter[]> {
  const data = await request<SessionCharacterListResponse>(
    SESSION_CHARACTERS(sessionId),
  );
  return data.characters;
}

export async function ensureProtagonistCharacter(
  sessionId: string,
): Promise<SessionCharacter[]> {
  const data = await request<SessionCharacterListResponse>(
    SESSION_CHARACTERS_ENSURE_PROTAGONIST(sessionId),
    { method: "POST" },
  );
  return data.characters;
}

export interface CreateSessionCharacterPayload {
  name: string;
  appearance_natural?: string;
  appearance_tags?: string;
  position?: CharacterPosition;
  slot_index?: number;
  source_preset_id?: string | null;
  appearance_lock?: boolean;
  exclude_from_effects?: boolean;
}

export async function createSessionCharacter(
  sessionId: string,
  payload: CreateSessionCharacterPayload,
): Promise<SessionCharacter> {
  return request<SessionCharacter>(SESSION_CHARACTERS(sessionId), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface UpdateSessionCharacterPayload {
  name?: string;
  appearance_natural?: string;
  appearance_tags?: string;
  position?: CharacterPosition;
  slot_index?: number;
  appearance_lock?: boolean;
  exclude_from_effects?: boolean;
}

export async function updateSessionCharacter(
  sessionId: string,
  characterId: string,
  payload: UpdateSessionCharacterPayload,
): Promise<SessionCharacter> {
  return request<SessionCharacter>(SESSION_CHARACTER(sessionId, characterId), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteSessionCharacter(
  sessionId: string,
  characterId: string,
): Promise<void> {
  await request<void>(SESSION_CHARACTER(sessionId, characterId), {
    method: "DELETE",
  });
}

export async function applyPresetToSession(
  sessionId: string,
  presetId: string,
): Promise<SessionCharacter> {
  return request<SessionCharacter>(
    CHARACTERS_FROM_PRESET(sessionId, presetId),
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// Character presets
// ---------------------------------------------------------------------------

export interface CharacterPresetListResponse {
  presets: CharacterPreset[];
}

export async function listCharacterPresets(): Promise<CharacterPreset[]> {
  const data = await request<CharacterPresetListResponse>(CHARACTER_PRESETS);
  return data.presets;
}

export interface CreatePresetFromCharacterPayload {
  from_character_id: string;
  name: string;
}

export interface CreatePresetRawPayload {
  name: string;
  appearance_natural?: string;
  appearance_tags?: string;
  default_position?: CharacterPosition;
}

export async function createCharacterPreset(
  payload: CreatePresetFromCharacterPayload | CreatePresetRawPayload,
): Promise<CharacterPreset> {
  return request<CharacterPreset>(CHARACTER_PRESETS, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface UpdateCharacterPresetPayload {
  name?: string;
  appearance_natural?: string;
  appearance_tags?: string;
  default_position?: CharacterPosition;
}

export async function updateCharacterPreset(
  presetId: string,
  payload: UpdateCharacterPresetPayload,
): Promise<CharacterPreset> {
  return request<CharacterPreset>(CHARACTER_PRESET(presetId), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteCharacterPreset(presetId: string): Promise<void> {
  await request<void>(CHARACTER_PRESET(presetId), {
    method: "DELETE",
  });
}
