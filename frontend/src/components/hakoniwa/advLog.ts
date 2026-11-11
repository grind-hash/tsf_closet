import type { HakoniwaEvent } from "../../apis/hakoniwa";

/** ADV の1幕。speaker が null なら地の文 */
export interface AdvLine {
  speaker: string | null;
  text: string;
}

/** ログの1場面(出来事)と、そのうち読み終えた幕 */
export interface AdvLogScene {
  event: HakoniwaEvent;
  lines: AdvLine[];
}

/** 出来事を ADV の幕に並べる(地の文 → 台詞の順) */
export function advScript(event: HakoniwaEvent): AdvLine[] {
  return [
    { speaker: null, text: event.narration },
    ...event.lines.map((line) => ({ speaker: line.speaker, text: line.text })),
  ];
}

/**
 * ADV のログに出す場面。「続きを指示」でつないだ場面は元の場面までさかのぼって古い順に並べ、
 * いま開いている場面は step(0 始まり)の幕までを出す(まだ読んでいない幕は出さない)。
 */
export function advLogScenes(
  events: HakoniwaEvent[],
  eventId: string,
  step: number,
): AdvLogScene[] {
  const byId = new Map(events.map((event) => [event.id, event]));
  const chain: HakoniwaEvent[] = [];
  const seen = new Set<string>();
  let current = byId.get(eventId);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    chain.unshift(current);
    current = current.continues ? byId.get(current.continues) : undefined;
  }
  return chain.map((event) => {
    const script = advScript(event);
    return {
      event,
      lines: event.id === eventId ? script.slice(0, step + 1) : script,
    };
  });
}
