import type { VoiceSegment } from "../hooks/useAdventureVoice";
import { ensureSentenceEnd, splitForSpeech } from "./adventureDialogue";

// Adventure の台本・本文を読み上げセグメントへ変換する純関数群。

/**
 * 手番のセリフ読み上げの識別キー。turn id は本文確定(narrative_done)時点で
 * 未確定のため手番番号で識別し、先読みと到着時の読み上げで同じキーになる
 */
export function turnVoiceKey(runId: string, turnNumber: number): string {
  return `turn:${runId}:${turnNumber}`;
}

/**
 * 台本の行(攻略対象のセリフ)を読み上げセグメントへ変換する。
 * id は「行番号:文番号」で安定させ、ストリーミング中に同じ確定行を
 * 繰り返し渡しても appendSegments 側の重複判定で一度だけ読まれる
 */
export function linesToVoiceSegments(
  lines: string[],
  groupKey: string,
): VoiceSegment[] {
  return lines.flatMap((line, lineIndex) =>
    splitForSpeech(ensureSentenceEnd(line)).map((text, partIndex) => ({
      id: `${groupKey}#${lineIndex}:${partIndex}`,
      text,
    })),
  );
}

/** 単一テキストを文単位の読み上げセグメントへ変換する */
export function textToVoiceSegments(
  text: string,
  groupKey: string,
): VoiceSegment[] {
  return splitForSpeech(text).map((part, index) => ({
    id: `${groupKey}#${index}`,
    text: part,
  }));
}
