/**
 * Adventure(romance)の台本形式テキストを扱うユーティリティ。
 *
 * 対面会話モードでは本文を `名前「セリフ」` の独立行で書かせる。ここでは
 * その行を話者付きのセグメントへ分解し、読み上げ対象(攻略対象のセリフだけ)を
 * 取り出す。地の文は括弧なしの行としてそのまま残す。
 */

import {
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "../constants/companionAvatar";

export interface DialogueSegment {
  kind: "narration" | "dialogue";
  /** dialogue のときの話者名 */
  speaker?: string;
  text: string;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 行頭の `名前「…」` / `名前：「…」` / `名前: …` を話者付きの行として認識する。
 * 名前だけで始まる地の文(「美咲は笑った。」)を誤検出しないよう、
 * コロンか開き括弧のどちらかを必須にする。ストリーミング途中の閉じ括弧が
 * 無い行も受け付ける。
 */
function buildSpeakerPattern(speakerNames: string[]): RegExp | null {
  const names = [...new Set(speakerNames.map((name) => name.trim()))]
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp);
  if (names.length === 0) return null;
  return new RegExp(
    `^\\s*(${names.join("|")})\\s*(?:[:：]\\s*[「『]?|[「『])\\s*(.*?)\\s*[」』]?\\s*$`,
  );
}

export function parseDialogueSegments(
  text: string,
  speakerNames: string[],
): DialogueSegment[] {
  const pattern = buildSpeakerPattern(speakerNames);
  const segments: DialogueSegment[] = [];
  let narration: string[] = [];
  const flushNarration = () => {
    const joined = narration.join("\n").trim();
    if (joined) segments.push({ kind: "narration", text: joined });
    narration = [];
  };
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      // 空行は段落の区切り。地の文をここで確定させる
      flushNarration();
      continue;
    }
    const match = pattern?.exec(line);
    if (match) {
      flushNarration();
      segments.push({ kind: "dialogue", speaker: match[1], text: match[2] });
    } else {
      narration.push(line);
    }
  }
  flushNarration();
  return segments;
}

/** 指定した話者のセリフだけを本文の順に取り出す */
export function partnerLines(text: string, partnerName: string): string[] {
  const name = partnerName.trim();
  if (!name) return [];
  return parseDialogueSegments(text, [name])
    .filter(
      (segment) => segment.kind === "dialogue" && segment.speaker === name,
    )
    .map((segment) => segment.text.trim())
    .filter(Boolean);
}

/** 文末とみなす記号。閉じ括弧は直前の文末記号を兼ねる */
const SENTENCE_END_RE = /[。！？!?…」』]$/;

/** 文末記号が無い行に句点を補う(joinForSpeech と同じ規則の単行版) */
export function ensureSentenceEnd(line: string): string {
  const trimmed = line.trim();
  if (!trimmed) return "";
  return SENTENCE_END_RE.test(trimmed) ? trimmed : `${trimmed}。`;
}

/** 読み上げ用に複数行を1本へ結合する。文末記号が無い行には句点を補う */
export function joinForSpeech(lines: string[]): string {
  return lines.map(ensureSentenceEnd).filter(Boolean).join("");
}

/** 読み上げセグメントの最小文字数。これ未満の断片は隣へ結合する */
const SPEECH_SEGMENT_MIN_CHARS = 10;
/** 読み上げセグメントの目安上限。超える文は読点で再分割する */
const SPEECH_SEGMENT_MAX_CHARS = 120;

/** 長すぎる文を読点(等)で SPEECH_SEGMENT_MAX_CHARS 以下に切る */
function splitLongSentence(sentence: string): string[] {
  const pieces: string[] = [];
  let rest = sentence;
  while (rest.length > SPEECH_SEGMENT_MAX_CHARS) {
    const window = rest.slice(0, SPEECH_SEGMENT_MAX_CHARS + 1);
    const cut = Math.max(window.lastIndexOf("、"), window.lastIndexOf("，"));
    if (cut < SPEECH_SEGMENT_MIN_CHARS) break;
    pieces.push(rest.slice(0, cut + 1));
    rest = rest.slice(cut + 1).trim();
  }
  if (rest) pieces.push(rest);
  return pieces;
}

/**
 * 逐次読み上げ用にテキストを文単位のセグメントへ分割する。
 * 細切れの合成リクエストを避けるため、短い断片は次の文とまとめ、
 * 長すぎる文は読点で再分割する。結合しても元の文字列順は変えない。
 */
export function splitForSpeech(text: string): string[] {
  const source = text.trim();
  if (!source) return [];
  const fragments = source
    .split(/(?<=[。！？!?…])/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .flatMap(splitLongSentence);

  const segments: string[] = [];
  let current = "";
  for (const fragment of fragments) {
    current = current ? `${current}${fragment}` : fragment;
    if (current.length >= SPEECH_SEGMENT_MIN_CHARS) {
      segments.push(current);
      current = "";
    }
  }
  if (current) {
    if (segments.length > 0 && current.length < SPEECH_SEGMENT_MIN_CHARS) {
      segments[segments.length - 1] += current;
    } else {
      segments.push(current);
    }
  }
  return segments;
}

/** ト書き(括弧書き)と鉤括弧を落とし、読み上げに不要な記号を除く */
export function stripStageDirections(text: string): string {
  return text
    .replace(/（[^）]*）/g, " ")
    .replace(/\([^)]*\)/g, " ")
    .replace(/[「」『』]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** トーク返答の先頭ヘッダの角括弧ブロック(1行・120文字まで) */
const TALK_HEADER_BLOCK_RE = /^\s*\[([^[\]\n]{1,120})\]\s*/;
const TALK_HEADER_LABEL_RE = /(?:expression|gesture)\s*[=:]/i;
const TALK_HEADER_TOKEN_RE = /[A-Za-z][A-Za-z_-]*/g;

/**
 * トーク返答の先頭ヘッダをセリフから取り除く。バックエンドの
 * parse_talk_header と同じ規則で、正規形([expression=.. gesture=..])に加え
 * LLM が略記した変形([surprised=tilt_head] 等)も受ける。剥がし損ねて
 * 保存されたログの表示・読み上げ前の防御に使う。語彙もラベルも含まない
 * 角括弧はセリフの一部として残す
 */
export function stripTalkHeader(text: string): string {
  const match = TALK_HEADER_BLOCK_RE.exec(text);
  if (!match) return text;
  const body = match[1];
  const tokens = body.match(TALK_HEADER_TOKEN_RE) ?? [];
  const hasVocab = tokens.some(
    (token) =>
      normalizeAvatarExpression(token) !== null ||
      normalizeAvatarGesture(token) !== null,
  );
  if (!TALK_HEADER_LABEL_RE.test(body) && !hasVocab) return text;
  return text.slice(match[0].length);
}
