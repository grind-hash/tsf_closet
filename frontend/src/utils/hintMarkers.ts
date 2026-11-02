/**
 * 心境の中のヒントの目印。依頼の emphasize_hints が有効なとき、まだ満たされていない
 * 好みをほのめかす一文を LLM がこの記号で囲む(バックエンドの REQUEST_HINT_MARK_* と同じ)。
 * サロンの接客画面は強調表示し、ほかの画面では取り除いて表示する。
 */
export const HINT_MARK_OPEN = "〔";
export const HINT_MARK_CLOSE = "〕";

export interface HintSegment {
  text: string;
  hint: boolean;
}

/**
 * 目印で囲まれた部分を hint として分ける。閉じていない目印(ストリーミング途中)は
 * 末尾までを hint とする。
 */
export function splitHintMarkers(text: string): HintSegment[] {
  const segments: HintSegment[] = [];
  let rest = text;
  while (rest) {
    const open = rest.indexOf(HINT_MARK_OPEN);
    if (open < 0) {
      segments.push({ text: rest, hint: false });
      break;
    }
    if (open > 0) segments.push({ text: rest.slice(0, open), hint: false });
    const inner = rest.slice(open + HINT_MARK_OPEN.length);
    const close = inner.indexOf(HINT_MARK_CLOSE);
    if (close < 0) {
      if (inner) segments.push({ text: inner, hint: true });
      break;
    }
    if (close > 0) segments.push({ text: inner.slice(0, close), hint: true });
    rest = inner.slice(close + HINT_MARK_CLOSE.length);
  }
  return segments;
}

/** 目印だけを取り除く(囲まれていた文はそのまま残す) */
export function stripHintMarkers(text: string): string {
  return text.replaceAll(HINT_MARK_OPEN, "").replaceAll(HINT_MARK_CLOSE, "");
}
