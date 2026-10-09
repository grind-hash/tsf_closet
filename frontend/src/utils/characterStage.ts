/**
 * 複数人表示の登場人物（登場順・人数上限）に関する純粋関数。
 *
 * 並び順と数え方はバックエンドの build_stage_roster と揃える:
 * 主人公を先頭に slot 順、主人公は常に登場扱い。
 */

import {
  MAX_CHARACTER_PROMPTS_V5,
  MAX_CHARACTER_PROMPTS_V45,
} from "../constants/promptExpander";
import type { SessionCharacter } from "../types";

/** 1 セッションに登録できる人数（主人公を含む） */
export const MAX_REGISTERED_CHARACTERS = 22;

/** 主人公を先頭に、残りを slot 順に並べる */
export function sortRoster(characters: SessionCharacter[]): SessionCharacter[] {
  return [...characters].sort((a, b) => {
    if (a.is_protagonist && !b.is_protagonist) return -1;
    if (!a.is_protagonist && b.is_protagonist) return 1;
    return a.slot_index - b.slot_index;
  });
}

/**
 * 画像・テキストに反映される人数。生成時は主人公が必ず先頭に入るため、
 * 主人公の行がまだ無くても 1 人として数える。
 */
export function countOnStage(characters: SessionCharacter[]): number {
  return 1 + characters.filter((c) => !c.is_protagonist && c.on_stage).length;
}

/** 1 枚の画像に載せられる人数（NovelAI V5 は 22、それ以外は 6） */
export function getStageLimit(isNovelaiV5Active: boolean): number {
  return isNovelaiV5Active
    ? MAX_CHARACTER_PROMPTS_V5
    : MAX_CHARACTER_PROMPTS_V45;
}

/** 上限を超えて生成に使われない人物の id（登場 ON のうち並び順の後ろから外れる） */
export function overflowCharacterIds(
  characters: SessionCharacter[],
  limit: number,
): Set<string> {
  const others = sortRoster(characters).filter(
    (c) => !c.is_protagonist && c.on_stage,
  );
  return new Set(others.slice(Math.max(0, limit - 1)).map((c) => c.id));
}

function normalizeTags(tags: string): string {
  return tags
    .split(",")
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)
    .join(",");
}

/** 次の手番で使う姿が、直前の手番の結果（設定から変化した姿）か */
export function hasLookChanged(character: SessionCharacter): boolean {
  if (character.look_source !== "history" || !character.current_tags) {
    return false;
  }
  return (
    normalizeTags(character.current_tags) !==
    normalizeTags(character.appearance_tags ?? "")
  );
}
