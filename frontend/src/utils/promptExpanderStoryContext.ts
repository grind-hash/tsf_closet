import type { PromptExpanderEntry } from "../apis/promptExpander";

/** これまでの話のチップに出すラベルの最大文字数（全文はカードで読める） */
export const STORY_CONTEXT_LABEL_MAX_LENGTH = 16;

/**
 * これまでの話に使える文をエントリが持っているか。
 * 文を持たないアップロード画像は前のページとして渡せる内容が無いので選ばせない
 */
export function entryHasStoryText(entry: PromptExpanderEntry): boolean {
  return Boolean(
    entry.synopsis?.trim() ||
      entry.instruction?.trim() ||
      entry.final_prompt?.trim() ||
      entry.character_prompts.some((prompt) => prompt.trim()),
  );
}

/** チップのラベル。あらすじ → ネーム（指示） → プロンプトの順に、最初に書いてある文の先頭 */
export function storyContextEntryLabel(
  entry: PromptExpanderEntry,
  maxLength = STORY_CONTEXT_LABEL_MAX_LENGTH,
): string {
  const text = [entry.synopsis, entry.instruction, entry.final_prompt]
    .map((value) => (value ?? "").replace(/\s+/g, " ").trim())
    .find((value) => value.length > 0);
  if (!text) return "";
  const chars = Array.from(text);
  return chars.length > maxLength
    ? `${chars.slice(0, maxLength).join("")}…`
    : text;
}

/** 生成した順（古い順）に並べる比較関数。話の順として使う */
export function compareEntriesByCreation(
  a: PromptExpanderEntry,
  b: PromptExpanderEntry,
): number {
  const diff = Date.parse(a.created_at) - Date.parse(b.created_at);
  if (diff !== 0 && !Number.isNaN(diff)) return diff;
  return a.id.localeCompare(b.id);
}

/**
 * 「生成履歴から選ぶ」で移る先のカード。
 * まだ選んでいないページのうち一番新しいもの（続きを作る直前のページ）を選ぶ。
 * 上限まで選んでいるときは「入れる」が押せないので、「外す」が押せる選択中の一番新しいページにする。
 * 選べるページが無ければ null
 */
export function findStoryPickTarget(
  entries: readonly PromptExpanderEntry[],
  selectedIds: readonly string[],
  max: number,
): PromptExpanderEntry | null {
  const selected = new Set(selectedIds);
  const full = selected.size >= max;
  const candidates = entries.filter(entryHasStoryText);
  const preferred = candidates.filter(
    (entry) => selected.has(entry.id) === full,
  );
  const pool = preferred.length > 0 ? preferred : candidates;
  let newest: PromptExpanderEntry | null = null;
  for (const entry of pool) {
    if (newest === null || compareEntriesByCreation(entry, newest) > 0) {
      newest = entry;
    }
  }
  return newest;
}
