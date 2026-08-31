/**
 * viseme タイムラインの参照ユーティリティ(純関数)。
 *
 * タイムラインは合成音声のメディア時刻(秒)で表されるため、audio.currentTime
 * で引けば playbackRate に依存せず口形が同期する。毎フレーム呼ばれる前提で、
 * 単調前進カーソルにより通常は O(1) で現在のイベントへ届く。時刻が逆行した
 * とき(再再生・シーク)は先頭から探し直す。
 */
import type { VisemeEvent } from "../apis/speechSynthesis";

/** ある瞬間の口形。viseme が null なら閉口(タイムラインの空白区間) */
export interface VisemeFrame {
  viseme: string | null;
  w: number;
}

/** visemeAtTime の探索位置。タイムラインごとに1つ持ち、使い回す */
export interface VisemeCursor {
  index: number;
}

export const CLOSED_VISEME_FRAME: VisemeFrame = { viseme: null, w: 0 };

export function createVisemeCursor(): VisemeCursor {
  return { index: 0 };
}

/** 時刻 tSec の口形を返す。cursor は呼び出しのたびに前進する */
export function visemeAtTime(
  timeline: VisemeEvent[],
  tSec: number,
  cursor: VisemeCursor,
): VisemeFrame {
  if (timeline.length === 0) return CLOSED_VISEME_FRAME;
  let index = Math.min(Math.max(cursor.index, 0), timeline.length);
  // 直前に通過したイベントの終了より前の時刻を聞かれたら逆行とみなす
  if (index > 0 && tSec < timeline[index - 1].t1) {
    index = 0;
  }
  while (index < timeline.length && timeline[index].t1 <= tSec) {
    index += 1;
  }
  cursor.index = index;
  if (index < timeline.length && tSec >= timeline[index].t0) {
    const event = timeline[index];
    return { viseme: event.viseme, w: event.w };
  }
  return CLOSED_VISEME_FRAME;
}
