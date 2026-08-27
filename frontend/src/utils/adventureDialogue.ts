/**
 * Adventure(romance)の台本形式テキストを扱うユーティリティ。
 *
 * 対面会話モードでは本文を `名前「セリフ」` の独立行で書かせる。ここでは
 * その行を話者付きのセグメントへ分解し、読み上げ対象(攻略対象のセリフだけ)を
 * 取り出す。地の文は括弧なしの行としてそのまま残す。
 */

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

/** 読み上げ用に複数行を1本へ結合する。文末記号が無い行には句点を補う */
export function joinForSpeech(lines: string[]): string {
  return lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => (/[。！？!?…」』]$/.test(line) ? line : `${line}。`))
    .join("");
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
