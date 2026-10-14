/**
 * テキスト欄のキャレット位置へ文字列を差し込む（お気に入りプロンプトの挿入用）。
 *
 * 前後の文字とくっつく場合だけ separator を補う。タグ欄では ", "、文章欄では " " を使う。
 */

export interface InsertPromptTextResult {
  text: string;
  /** 挿入後にキャレットを置く位置 */
  caret: number;
}

function isBoundary(ch: string, separator: string): boolean {
  if (/\s/.test(ch)) return true;
  const mark = separator.trim();
  return mark !== "" && ch === mark;
}

export function insertPromptText(
  current: string,
  insert: string,
  selectionStart: number,
  selectionEnd: number,
  separator = ", ",
): InsertPromptTextResult {
  const clamp = (n: number) => Math.min(Math.max(n, 0), current.length);
  const start = clamp(Math.min(selectionStart, selectionEnd));
  const end = clamp(Math.max(selectionStart, selectionEnd));
  const before = current.slice(0, start);
  const after = current.slice(end);
  if (!insert) return { text: current, caret: start };

  let lead = "";
  const lastBefore = before.slice(-1);
  if (lastBefore && !/\s/.test(lastBefore)) {
    const mark = separator.trim();
    // 直前が区切り記号（","）なら空白だけ補う
    lead =
      mark !== "" && lastBefore === mark
        ? separator.slice(separator.indexOf(mark) + mark.length)
        : separator;
  }

  let trail = "";
  const firstAfter = after.charAt(0);
  const lastInsert = insert.slice(-1);
  if (
    firstAfter &&
    !isBoundary(firstAfter, separator) &&
    !isBoundary(lastInsert, separator)
  ) {
    trail = separator;
  }

  const piece = `${lead}${insert}${trail}`;
  return {
    text: `${before}${piece}${after}`,
    caret: before.length + piece.length,
  };
}
