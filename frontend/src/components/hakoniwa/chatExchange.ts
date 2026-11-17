import type { HakoniwaChatEntry } from "../../apis/hakoniwa";

/**
 * 会話の窓に出す最新の返事(プレイヤー以外の最後の発言)と、その前のプレイヤーの最後の言葉。
 * 変身のあとは [player, system, resident] の順なので、返事の直前とは限らない。
 */
export function latestExchange(history: HakoniwaChatEntry[]): {
  latest: HakoniwaChatEntry | undefined;
  lastPlayerLine: string | undefined;
} {
  let index = history.length - 1;
  while (index >= 0 && history[index].role === "player") index -= 1;
  const latest = index >= 0 ? history[index] : undefined;
  for (let at = (index >= 0 ? index : history.length) - 1; at >= 0; at -= 1) {
    if (history[at].role === "player") {
      return { latest, lastPlayerLine: history[at].text };
    }
  }
  return { latest, lastPlayerLine: undefined };
}
