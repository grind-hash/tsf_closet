/**
 * 集約された API エンドポイント定数 (Constitution Principle IV)
 *
 * コンポーネントから直接 fetch/axios を呼ばず、これらの定数経由で
 * API 関数を構築する。
 */

import { API_BASE } from "../utils/api";

// =============================================================================
// Multi-character persistence (spec 005)
// =============================================================================

export const SESSION_CHARACTERS = (sessionId: string): string =>
  `${API_BASE}/game/session/${encodeURIComponent(sessionId)}/characters`;

export const SESSION_CHARACTERS_ENSURE_PROTAGONIST = (
  sessionId: string,
): string =>
  `${API_BASE}/game/session/${encodeURIComponent(sessionId)}/characters/ensure-protagonist`;

export const SESSION_CHARACTER = (
  sessionId: string,
  characterId: string,
): string =>
  `${API_BASE}/game/session/${encodeURIComponent(sessionId)}/characters/${encodeURIComponent(characterId)}`;

export const CHARACTERS_FROM_PRESET = (
  sessionId: string,
  presetId: string,
): string =>
  `${API_BASE}/game/session/${encodeURIComponent(sessionId)}/characters/from-preset/${encodeURIComponent(presetId)}`;

export const CHARACTERS_GENERATE_TAGS = `${API_BASE}/game/characters/generate-tags`;

export const CHARACTER_PRESETS = `${API_BASE}/game/character-presets`;

export const CHARACTER_PRESET = (presetId: string): string =>
  `${API_BASE}/game/character-presets/${encodeURIComponent(presetId)}`;
