/**
 * 掟の切り替え直後の反応を、話し手のいる場所ごとの場面に分ける。
 *
 * 部屋のステージは再生中の場面の参加者を呼び寄せて表示するため、別の場所にいる
 * 住民の行を同じ場面に入れると、その住民が一時的に部屋へ現れて再生後に消える。
 * 場所ごとに場面を分け、いま見ている場所の場面を最後にする(再生後に元の場所へ戻る)。
 */

export interface ReactionLine {
  resident_id: string;
  text: string;
}

export interface ReactionScene {
  area: string;
  lines: ReactionLine[];
}

export function reactionScenes(
  lines: ReactionLine[],
  residentAreas: ReadonlyMap<string, string>,
  viewArea: string,
  fallbackArea: string,
): ReactionScene[] {
  const scenes: ReactionScene[] = [];
  for (const line of lines) {
    const area = residentAreas.get(line.resident_id) ?? fallbackArea;
    const scene = scenes.find((item) => item.area === area);
    if (scene) {
      scene.lines.push(line);
    } else {
      scenes.push({ area, lines: [line] });
    }
  }
  const here = scenes.findIndex((scene) => scene.area === viewArea);
  if (here >= 0 && here !== scenes.length - 1) {
    scenes.push(...scenes.splice(here, 1));
  }
  return scenes;
}
