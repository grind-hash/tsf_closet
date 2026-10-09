/**
 * Multi-character persistence API client (spec 005).
 *
 * Targets the /api/game/* endpoints exposed by `character_router.py`.
 * All field names follow the snake_case convention from the backend per
 * AGENTS.md (frontend types may use snake_case when mirroring the API).
 */

import {
  CHARACTER_GROUP_PRESET,
  CHARACTER_GROUP_PRESETS,
  CHARACTER_PRESET,
  CHARACTER_PRESETS,
  CHARACTERS_FROM_GROUP,
  CHARACTERS_FROM_PRESET,
  CHARACTERS_GENERATE_PROFILE,
  CHARACTERS_GENERATE_TAGS,
  CHARACTERS_RESOLVE_SOURCE,
  SESSION_CHARACTER,
  SESSION_CHARACTERS,
  SESSION_CHARACTERS_ENSURE_PROTAGONIST,
} from "../constants/apiEndpoint";
import type {
  CharacterGroupPreset,
  CharacterPosition,
  CharacterPreset,
  CharacterProfile,
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
  negative_tags?: string;
  profile?: CharacterProfile | null;
  on_stage?: boolean;
  thumbnail_url?: string | null;
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
  negative_tags?: string;
  profile?: CharacterProfile;
  on_stage?: boolean;
  thumbnail_url?: string;
  /** true: 次の手番は直前の姿を引き継がず、設定の姿で描く */
  reset_look?: boolean;
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
  options: { onStage?: boolean } = {},
): Promise<SessionCharacter> {
  const query =
    options.onStage === undefined ? "" : `?on_stage=${options.onStage}`;
  return request<SessionCharacter>(
    `${CHARACTERS_FROM_PRESET(sessionId, presetId)}${query}`,
    { method: "POST" },
  );
}

/** 主人公以外の登場人物を、組み合わせプリセットのメンバーで置き換える */
export async function applyGroupPresetToSession(
  sessionId: string,
  groupId: string,
): Promise<SessionCharacter[]> {
  const data = await request<SessionCharacterListResponse>(
    CHARACTERS_FROM_GROUP(sessionId, groupId),
    { method: "POST" },
  );
  return data.characters;
}

export interface GenerateCharacterProfilePayload {
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  memo: string;
}

/** 名前・外見・メモから性格プロフィールを LLM で生成する（保存はしない） */
export async function generateCharacterProfile(
  payload: GenerateCharacterProfilePayload,
): Promise<CharacterProfile> {
  return request<CharacterProfile>(CHARACTERS_GENERATE_PROFILE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface GenerateCharacterTagsItem {
  id: string;
  name: string;
  natural: string;
}

/** 自然文の外見から NovelAI 形式のタグを作る（保存はしない） */
export async function generateCharacterTags(
  items: GenerateCharacterTagsItem[],
): Promise<Array<{ id: string; tags: string }>> {
  const data = await request<{ results: Array<{ id: string; tags: string }> }>(
    CHARACTERS_GENERATE_TAGS,
    { method: "POST", body: JSON.stringify({ items }) },
  );
  return data.results;
}

export interface ResolveCharacterSourcePayload {
  session_id?: string;
  history_id?: string;
  prompt_expander_entry_id?: string;
}

export interface ResolvedCharacterSource {
  name: string | null;
  appearance_natural: string;
  appearance_tags: string;
}

/** セッション・お気に入り・Prompt Expander の選択から名前と外見を取り出す */
export async function resolveCharacterSource(
  payload: ResolveCharacterSourcePayload,
): Promise<ResolvedCharacterSource> {
  return request<ResolvedCharacterSource>(CHARACTERS_RESOLVE_SOURCE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  negative_tags?: string;
  profile?: CharacterProfile | null;
  thumbnail_url?: string | null;
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
  negative_tags?: string;
  profile?: CharacterProfile;
  thumbnail_url?: string;
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

// ---------------------------------------------------------------------------
// Group presets (cast combinations)
// ---------------------------------------------------------------------------

export interface CharacterGroupPresetListResponse {
  groups: CharacterGroupPreset[];
}

export async function listCharacterGroupPresets(): Promise<
  CharacterGroupPreset[]
> {
  const data = await request<CharacterGroupPresetListResponse>(
    CHARACTER_GROUP_PRESETS,
  );
  return data.groups;
}

/** セッションの登場人物（主人公以外）を組み合わせとして保存する */
export async function createCharacterGroupPreset(payload: {
  name: string;
  from_session_id: string;
}): Promise<CharacterGroupPreset> {
  return request<CharacterGroupPreset>(CHARACTER_GROUP_PRESETS, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 名前の変更、またはセッションの登場人物での上書き */
export async function updateCharacterGroupPreset(
  groupId: string,
  payload: { name?: string; from_session_id?: string },
): Promise<CharacterGroupPreset> {
  return request<CharacterGroupPreset>(CHARACTER_GROUP_PRESET(groupId), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteCharacterGroupPreset(
  groupId: string,
): Promise<void> {
  await request<void>(CHARACTER_GROUP_PRESET(groupId), { method: "DELETE" });
}
