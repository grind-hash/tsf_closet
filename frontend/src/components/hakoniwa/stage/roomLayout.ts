/**
 * 箱庭の部屋ステージの座標計算(Phaser に依存しない純粋関数)。
 *
 * ゲーム座標は背景素材(1216x832)に合わせる。住民の足元は床の帯の中に収め、
 * 出来事の再生では参加住民を手前寄りの位置へ集めて向き合わせる。
 */

export const GAME_W = 1216;
export const GAME_H = 832;
/** 住民の足元 y の範囲(奥〜手前) */
export const FLOOR_TOP = 580;
export const FLOOR_BOTTOM = 784;
/** 部屋の中での住民の表示高さ */
export const AVATAR_H = Math.round(GAME_H * 0.55);
/** 歩く速さ(ゲーム座標 px / 秒) */
export const WALK_SPEED = 58;
/** 名札と頭の間隔、名札のおおよその高さ(吹き出しの位置合わせ用) */
export const NAME_OFFSET = 10;
export const NAME_HEIGHT = 36;
/** 徘徊の目標点を他の住民から離す距離 */
export const MIN_SPACING = 95;
/** 寄り合いで隣り合う住民の間隔 */
export const FOCUS_SPACING = 164;
/** 寄り合いの位置は手前寄りに取る(奥だと吹き出しが上端からはみ出す) */
export const FOCUS_MIN_Y = 648;

export interface Point {
  x: number;
  y: number;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** 住民の初期位置。並び順で横に散らし、足元の高さも少しずつずらす */
export function initialPosition(index: number, count: number): Point {
  const slots = Math.max(count, 1);
  const x = clamp(((index + 0.5) / slots) * GAME_W, 80, GAME_W - 80);
  const y = clamp(
    FLOOR_TOP + 70 + ((index * 47) % 170),
    FLOOR_TOP,
    FLOOR_BOTTOM,
  );
  return { x, y };
}

/** 住民ごとの足元の高さの癖(重なりにくくする) */
export function yJitter(index: number): number {
  return (index % 5) * 14 - 28;
}

/**
 * 徘徊の目標点を選ぶ。他の住民の位置(または目標)から MIN_SPACING 以上離れた点を
 * 8 回まで探し、見つからなければ最後の候補を返す。
 */
export function pickWanderTarget(
  others: Point[],
  jitter: number,
  random: () => number = Math.random,
  avoid: XRange | null = null,
): Point {
  let best: Point = { x: GAME_W / 2, y: (FLOOR_TOP + FLOOR_BOTTOM) / 2 };
  // 出来事の再生中は、集まっている場所の外側だけから選ぶ
  const ranges = avoid ? freeRanges(avoid) : [{ min: 100, max: GAME_W - 100 }];
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const range = ranges[Math.floor(random() * ranges.length)] ?? ranges[0];
    const x = range.min + random() * Math.max(range.max - range.min, 0);
    const y = clamp(
      FLOOR_TOP + 30 + random() * (FLOOR_BOTTOM - FLOOR_TOP - 60) + jitter,
      FLOOR_TOP,
      FLOOR_BOTTOM,
    );
    best = { x, y };
    if (
      others.every(
        (other) => Math.hypot(other.x - x, other.y - y) >= MIN_SPACING,
      )
    ) {
      break;
    }
  }
  return best;
}

export interface XRange {
  min: number;
  max: number;
}

/** 避ける範囲の左右に残る、歩ける横の範囲 */
function freeRanges(avoid: XRange): XRange[] {
  const ranges: XRange[] = [];
  if (avoid.min - 100 > 60) ranges.push({ min: 100, max: avoid.min });
  if (GAME_W - 100 - avoid.max > 60) {
    ranges.push({ min: avoid.max, max: GAME_W - 100 });
  }
  return ranges.length > 0 ? ranges : [{ min: 100, max: GAME_W - 100 }];
}

/** 出来事の参加住民が集まる横の範囲(居合わせない住民はここを空ける) */
export function focusZone(targets: Point[], margin = 130): XRange | null {
  if (targets.length === 0) return null;
  const xs = targets.map((target) => target.x);
  return { min: Math.min(...xs) - margin, max: Math.max(...xs) + margin };
}

export interface FocusTarget extends Point {
  /** 左を向くか(画像の左右反転) */
  flip: boolean;
}

/**
 * 出来事の参加住民(1〜3人)を集める位置。今の位置の左から順に並べ、端の住民は
 * 中央を向く。1人なら今の位置の近くで正面を向く。
 */
export function focusTargets(positions: Point[]): FocusTarget[] {
  if (positions.length === 0) return [];
  const midX = clamp(
    positions.reduce((sum, point) => sum + point.x, 0) / positions.length,
    240,
    GAME_W - 240,
  );
  const midY = clamp(
    positions.reduce((sum, point) => sum + point.y, 0) / positions.length,
    FOCUS_MIN_Y,
    FLOOR_BOTTOM - 20,
  );
  if (positions.length === 1) {
    return [{ x: midX, y: midY, flip: false }];
  }
  const order = positions
    .map((point, index) => ({ point, index }))
    .sort((a, b) => a.point.x - b.point.x);
  const span = FOCUS_SPACING * (positions.length - 1);
  const targets: FocusTarget[] = new Array(positions.length);
  order.forEach(({ index }, rank) => {
    const x = midX - span / 2 + rank * FOCUS_SPACING;
    // 右側の住民ほど左(中央)を向く。3人の中央は正面のまま
    const center = (positions.length - 1) / 2;
    targets[index] = { x, y: midY, flip: rank > center };
  });
  return targets;
}

/**
 * 吹き出しの位置(部屋の枠に対する割合)。名札の上端を指す。
 * bob は歩行中の上下動のずれ。
 */
export function anchorRatio(position: Point, bob = 0): Point {
  return {
    x: position.x / GAME_W,
    y: (position.y + bob - AVATAR_H - NAME_OFFSET - NAME_HEIGHT) / GAME_H,
  };
}

/** 目標へ一歩進めた位置と、着いたかどうか */
export function stepToward(
  position: Point,
  target: Point,
  deltaMs: number,
  speed = WALK_SPEED,
): { position: Point; arrived: boolean; movingLeft: boolean } {
  const dx = target.x - position.x;
  const dy = target.y - position.y;
  const distance = Math.hypot(dx, dy);
  const step = (speed * deltaMs) / 1000;
  if (distance <= Math.max(step, 2)) {
    return { position: { ...target }, arrived: true, movingLeft: dx < 0 };
  }
  return {
    position: {
      x: position.x + (dx / distance) * step,
      y: position.y + (dy / distance) * step,
    },
    arrived: false,
    movingLeft: dx < 0,
  };
}
