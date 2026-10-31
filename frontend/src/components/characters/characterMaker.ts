import type { CharacterPreset, CharacterProfile } from "../../types";

/** 未設定の項目を空で埋めたプロフィール(キャラクターメイクの項目を含む) */
export type FullCharacterProfile = Required<CharacterProfile>;

export const EMPTY_CHARACTER_PROFILE: FullCharacterProfile = {
  personality: "",
  reaction_style: "default",
  pronoun: "",
  gender: "",
  interests: [],
  tsf_attitude: "",
  memo: "",
  speech_style: "",
  sample_lines: "",
  knowledge: "",
  greeting: "",
};

export function fullProfile(preset: CharacterPreset): FullCharacterProfile {
  return { ...EMPTY_CHARACTER_PROFILE, ...(preset.profile ?? {}) };
}

/** 外見タグから描いた立ち絵か(白抜きして立たせる)。素材の画像は false */
export function isGeneratedPortrait(url: string | null | undefined): boolean {
  if (!url) return false;
  const name = url.split("/").pop() ?? "";
  return name.startsWith("portrait-");
}
