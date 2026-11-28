import type { PromptExpanderEntry } from "../apis/promptExpander";

/**
 * エントリの instruction がネームの欄で書かれたか。
 * 記録前の古いエントリ（instruction_source が無い）は、ネームから作ったときだけ入る
 * synopsis の有無で見分ける（あらすじを空のまま手書きしたネームは見分けられない）
 */
export function isEntryFromScript(entry: PromptExpanderEntry): boolean {
  if (entry.instruction_source) return entry.instruction_source === "script";
  return Boolean(entry.synopsis?.trim());
}
