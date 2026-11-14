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
/** 部屋の中での住民の表示高さ(いちばん手前に立ったとき) */
export const AVATAR_H = Math.round(GAME_H * 0.55);
/** 床のいちばん奥に立ったときの縮尺(奥ほど小さく描き、浮いて見えないようにする) */
export const DEPTH_SCALE_BACK = 0.84;
/**
 * 歩くときの左右の揺れ(足元を軸にした回転、ラジアン)と、位相の進む速さ(ラジアン / ms)。
 * 揺れの 1 往復(約 1 秒)を 2 歩とする。
 */
export const WALK_SWAY = 0.022;
export const WALK_SWAY_SPEED = 0.0065;
/** 一歩ごとに体を縦へ伸ばす割合。足元を軸に伸ばすので足は床から離れない */
export const STEP_STRETCH = 0.012;
/** 歩きの揺れを出し入れする時間(歩き出し・立ち止まりで揺れが急に切り替わらないように) */
export const WALK_BLEND_MS = 280;
/** 立っている間の呼吸(縦の伸び縮みの割合と、1 呼吸の長さ) */
export const BREATH_STRETCH = 0.006;
export const BREATH_PERIOD_MS = 3600;
/**
 * 振り向き: 横幅を縮めて裏返す時間と、裏返す瞬間の最小の横幅。
 * 細くしすぎると紙の切り抜きのように線になって見えるので、4 割の幅で止める。
 */
export const TURN_MS = 200;
export const TURN_MIN_WIDTH = 0.4;
/** 横の移動がこれより小さい歩き(奥・手前への移動)では振り向かない */
export const TURN_MIN_DX = 28;
/** 手前での家具の高さ。住民の身長を基準にしたゲーム座標 */
const FURNITURE_SIZES: Readonly<
  Record<string, { height: number; shadowWidth: number }>
> = {
  houseplant: { height: 248, shadowWidth: 68 },
  cat_tower: { height: 278, shadowWidth: 159 },
  bookshelf: { height: 338, shadowWidth: 254 },
  round_table: { height: 169, shadowWidth: 169 },
  lamp: { height: 347, shadowWidth: 76 },
  plush: { height: 104, shadowWidth: 77 },
  aquarium: { height: 245, shadowWidth: 158 },
  kotatsu: { height: 103, shadowWidth: 279 },
};

export function furnitureSize(id: string, y: number) {
  const { height, shadowWidth } = FURNITURE_SIZES[id] ?? {
    height: 215,
    shadowWidth: 120,
  };
  const scale = depthScale(y);
  return { height: height * scale, shadowWidth: shadowWidth * scale };
}
/** 歩く速さ(ゲーム座標 px / 秒) */
export const WALK_SPEED = 70;
/** 歩き出しで速さが上がりきるまでの時間と、立ち止まる前に減速し始める距離 */
export const WALK_ACCEL_MS = 450;
export const WALK_SLOW_RADIUS = 28;
/** 名札と頭の間隔、名札のおおよその高さ(吹き出しの位置合わせ用) */
export const NAME_OFFSET = 10;
export const NAME_HEIGHT = 36;
/**
 * 住民どうしが空ける間合い(楕円の横・奥行きの半径)。横は立ち絵の体の幅に合わせる。
 * 立ち絵は背が高く、奥行きが少し違うだけでは前の住民が後ろの住民をほぼ隠すので、
 * 立ち止まる場所では奥行きの半径を床の奥行きより大きく取り、横に離れて立たせる。
 * 歩いて前後をすれ違うのは自然なので、道筋では奥行きの半径を小さく取る。
 */
export const PERSONAL_SPACE_X = 160;
export const STANDING_SPACE_Y = 260;
export const PASSING_SPACE_Y = 100;
/** 歩く道筋が他の住民の前後をかすめてよい近さ(間合いに対する割合) */
export const PASSING_CLEARANCE = 0.7;
/** 歩く先の様子を見る距離(この先に人がいれば立ち止まる) */
export const LOOKAHEAD = 40;
/** 近場をぶらつく歩きの割合と、その横の距離・奥行きの幅 */
export const STROLL_CHANCE = 0.65;
export const STROLL_MIN_DX = 90;
export const STROLL_MAX_DX = 320;
export const STROLL_MAX_DY = 80;
/** 立ち止まっている時間(着いてから次に歩き出すまで) */
export const IDLE_MIN_MS = 3000;
export const IDLE_MAX_MS = 8000;
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

/** 背景の幅1216に対する床の奥端。左右の壁と家具の手前に靴を置ける余白を取る。
 * 折れ線の傾きを単調増加にして、床上の任意の2点を結ぶ直線も床に収める。 */
const FLOOR_EDGES: Readonly<Record<string, readonly Point[]>> = {
  living: [
    { x: 0, y: 784 },
    { x: 418, y: 652 },
    { x: 801, y: 654 },
    { x: GAME_W, y: 812 },
  ],
  study: [
    { x: 0, y: 846 },
    { x: 520, y: 643 },
    { x: 788, y: 599 },
    { x: GAME_W, y: 827 },
  ],
  garden: [
    { x: 0, y: 762 },
    { x: 420, y: 629 },
    { x: 790, y: 606 },
    { x: GAME_W, y: 747 },
  ],
};

/** 背景と横位置から歩ける範囲を求める。書斎の両端には床幅が足りない。 */
export function onFloor(point: Point, areaId: string): Point {
  const inset = areaId === "study" ? 174 : 80;
  const x = clamp(point.x, inset, GAME_W - inset);
  const edge = FLOOR_EDGES[areaId];
  const rightIndex = edge?.findIndex((p) => p.x >= x) ?? -1;
  let top = FLOOR_TOP;
  if (edge && rightIndex > 0) {
    const left = edge[rightIndex - 1];
    const right = edge[rightIndex];
    top = left.y + ((x - left.x) / (right.x - left.x)) * (right.y - left.y);
  }
  return { x, y: clamp(point.y, top, FLOOR_BOTTOM) };
}

/** 住民の初期位置。並び順で横に散らし、足元の高さも少しずつずらす */
export function initialPosition(
  index: number,
  count: number,
  areaId: string,
): Point {
  const slots = Math.max(count, 1);
  // 入室直後は両端の置き場所を少し空けて、小物が住民の真後ろに隠れないようにする
  const inset = 118;
  const x = inset + ((index + 0.5) / slots) * (GAME_W - 2 * inset);
  const y = clamp(
    FLOOR_TOP + 70 + ((index * 47) % 170),
    FLOOR_TOP,
    FLOOR_BOTTOM,
  );
  return onFloor({ x, y }, areaId);
}

/** 住民ごとの足元の高さの癖(重なりにくくする) */
export function yJitter(index: number): number {
  return (index % 5) * 14 - 28;
}

/** value を goal へ maxStep だけ近づける */
export function approach(value: number, goal: number, maxStep: number): number {
  if (Math.abs(goal - value) <= maxStep) return goal;
  return value + Math.sign(goal - value) * maxStep;
}

/**
 * 間合いで測った 2 点の近さ。1 未満なら相手の間合いに入っている。
 * 奥行きの半径は、立ち止まる場所なら STANDING_SPACE_Y、すれ違いなら PASSING_SPACE_Y。
 */
export function spaceDistance(
  a: Point,
  b: Point,
  radiusY = STANDING_SPACE_Y,
): number {
  return Math.hypot((a.x - b.x) / PERSONAL_SPACE_X, (a.y - b.y) / radiusY);
}

/**
 * from から to へまっすぐ歩くとき、other にいちばん近づいたときの近さ
 * (すれ違いの間合い PASSING_SPACE_Y で測る)
 */
export function pathClearance(from: Point, to: Point, other: Point): number {
  const ax = from.x / PERSONAL_SPACE_X;
  const ay = from.y / PASSING_SPACE_Y;
  const dx = to.x / PERSONAL_SPACE_X - ax;
  const dy = to.y / PASSING_SPACE_Y - ay;
  const ox = other.x / PERSONAL_SPACE_X;
  const oy = other.y / PASSING_SPACE_Y;
  const lengthSq = dx * dx + dy * dy;
  const t =
    lengthSq === 0
      ? 0
      : clamp(((ox - ax) * dx + (oy - ay) * dy) / lengthSq, 0, 1);
  return Math.hypot(ax + dx * t - ox, ay + dy * t - oy);
}

/**
 * 目標点の良さ。1 以上なら、着いた先が誰の間合いにも入らず、道筋も人をすり抜けない。
 * すでに間合いに入っている相手については、離れていく道筋なら問わず、
 * 近づいていく道筋だけを見る(isPathBlocked で止められる道筋を選ばないため)。
 */
function targetScore(from: Point, candidate: Point, others: Point[]): number {
  let score = Number.POSITIVE_INFINITY;
  for (const other of others) {
    score = Math.min(score, spaceDistance(candidate, other));
    const start = spaceDistance(from, other, PASSING_SPACE_Y);
    const closest = pathClearance(from, candidate, other);
    if (start >= 1 || closest < start - 0.01) {
      score = Math.min(score, closest / PASSING_CLEARANCE);
    }
  }
  return score;
}

/** x を歩ける横の範囲のどれかに収める(外れていれば近い方の端へ寄せる) */
function clampToRanges(x: number, ranges: XRange[]): number {
  let best = x;
  let bestGap = Number.POSITIVE_INFINITY;
  for (const range of ranges) {
    const inside = clamp(x, range.min, range.max);
    const gap = Math.abs(inside - x);
    if (gap < bestGap) {
      best = inside;
      bestGap = gap;
    }
  }
  return best;
}

/**
 * 徘徊の目標点を選ぶ。たいていは今いる場所の近くをぶらつき、ときどき部屋の別の側へ渡る。
 * 着いた先が他の住民(の位置と、歩いている住民の目標)の間合いに入らず、道筋が人を
 * すり抜けない点を 12 回まで探し、見つからなければいちばん空いている候補を返す。
 */
export function pickWanderTarget(
  from: Point,
  others: Point[],
  jitter: number,
  areaId: string,
  random: () => number = Math.random,
  avoid: XRange | null = null,
): Point {
  let best: Point = { x: GAME_W / 2, y: (FLOOR_TOP + FLOOR_BOTTOM) / 2 };
  let bestScore = Number.NEGATIVE_INFINITY;
  // 出来事の再生中は、集まっている場所の外側だけから選ぶ
  const inset = areaId === "study" ? 174 : 100;
  const walkRange = { min: inset, max: GAME_W - inset };
  const ranges = avoid ? freeRanges(avoid, walkRange) : [walkRange];
  for (let attempt = 0; attempt < 12; attempt += 1) {
    let candidate: Point;
    if (random() < STROLL_CHANCE) {
      const direction = random() < 0.5 ? -1 : 1;
      const dx = STROLL_MIN_DX + random() * (STROLL_MAX_DX - STROLL_MIN_DX);
      candidate = {
        x: clampToRanges(from.x + direction * dx, ranges),
        y: clamp(
          from.y + (random() * 2 - 1) * STROLL_MAX_DY,
          FLOOR_TOP,
          FLOOR_BOTTOM,
        ),
      };
    } else {
      const range = ranges[Math.floor(random() * ranges.length)] ?? ranges[0];
      candidate = {
        x: range.min + random() * Math.max(range.max - range.min, 0),
        y: clamp(
          FLOOR_TOP + 30 + random() * (FLOOR_BOTTOM - FLOOR_TOP - 60) + jitter,
          FLOOR_TOP,
          FLOOR_BOTTOM,
        ),
      };
    }
    candidate = onFloor(candidate, areaId);
    const score = targetScore(from, candidate, others);
    if (score > bestScore) {
      best = candidate;
      bestScore = score;
    }
    if (score >= 1) break;
  }
  return best;
}

/**
 * 歩く先(LOOKAHEAD 先)で他の住民の間合いに深く入り、しかも近づいていくか。
 * 前に人がいるときは立ち止まって向かい直すのに使う。離れていく動きは止めない。
 */
export function isPathBlocked(
  position: Point,
  target: Point,
  others: Point[],
): boolean {
  const dx = target.x - position.x;
  const dy = target.y - position.y;
  const distance = Math.hypot(dx, dy);
  if (distance < 1) return false;
  const reach = Math.min(LOOKAHEAD, distance);
  const ahead = {
    x: position.x + (dx / distance) * reach,
    y: position.y + (dy / distance) * reach,
  };
  return others.some((other) => {
    const next = spaceDistance(ahead, other, PASSING_SPACE_Y);
    return (
      next < PASSING_CLEARANCE &&
      next < spaceDistance(position, other, PASSING_SPACE_Y)
    );
  });
}

/** 立ち止まった場所から、少し進んだ先で止まるための点(急に止まらず減速して止まる) */
export function brakePoint(position: Point, target: Point): Point {
  const dx = target.x - position.x;
  const dy = target.y - position.y;
  const distance = Math.hypot(dx, dy);
  if (distance < 1) return { ...position };
  const reach = Math.min(WALK_SLOW_RADIUS / 2, distance);
  return {
    x: position.x + (dx / distance) * reach,
    y: position.y + (dy / distance) * reach,
  };
}

/**
 * 歩き出してからの時間と残りの距離に応じた速さの割合(0.2〜1)。
 * 歩き出しは滑らかに加速し、目標の手前で減速して止まる。
 */
export function walkSpeedFactor(walkedMs: number, remaining: number): number {
  const t = clamp(walkedMs / WALK_ACCEL_MS, 0, 1);
  const start = t * t * (3 - 2 * t);
  // 一定の減速度で止まるときの速さは残りの距離の平方根に比例する
  const end = Math.sqrt(clamp(remaining / WALK_SLOW_RADIUS, 0, 1));
  return Math.max(0.2, Math.min(start, end));
}

/** 立ち止まったときに向き直る相手(range 以内でいちばん近い住民)。いなければ null */
export function nearestWithin(
  position: Point,
  others: Point[],
  range: number,
): Point | null {
  let nearest: Point | null = null;
  let nearestDistance = range;
  for (const other of others) {
    const distance = Math.hypot(other.x - position.x, other.y - position.y);
    if (distance <= nearestDistance) {
      nearest = other;
      nearestDistance = distance;
    }
  }
  return nearest;
}

export interface XRange {
  min: number;
  max: number;
}

/** 避ける範囲の左右に残る、歩ける横の範囲 */
function freeRanges(avoid: XRange, walk: XRange): XRange[] {
  const ranges: XRange[] = [];
  if (avoid.min - walk.min > 60)
    ranges.push({ min: walk.min, max: Math.min(avoid.min, walk.max) });
  if (walk.max - avoid.max > 60) {
    ranges.push({ min: Math.max(avoid.max, walk.min), max: walk.max });
  }
  return ranges.length > 0 ? ranges : [walk];
}

/** 出来事の参加住民が集まる横の範囲(居合わせない住民はここを空ける) */
export function focusZone(
  targets: Point[],
  margin = PERSONAL_SPACE_X,
): XRange | null {
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
export function focusTargets(
  positions: Point[],
  areaId: string,
): FocusTarget[] {
  if (positions.length === 0) return [];
  const left = onFloor({ x: 0, y: FLOOR_BOTTOM }, areaId).x;
  const width = GAME_W - 2 * left;
  const spacing = Math.min(
    FOCUS_SPACING,
    width / Math.max(1, positions.length - 1),
  );
  const span = spacing * (positions.length - 1);
  const margin = Math.max(240, left + span / 2);
  const midX = clamp(
    positions.reduce((sum, point) => sum + point.x, 0) / positions.length,
    margin,
    GAME_W - margin,
  );
  const midY = clamp(
    positions.reduce((sum, point) => sum + point.y, 0) / positions.length,
    FOCUS_MIN_Y,
    FLOOR_BOTTOM - 20,
  );
  if (positions.length === 1) {
    return [{ ...onFloor({ x: midX, y: midY }, areaId), flip: false }];
  }
  const order = positions
    .map((point, index) => ({ point, index }))
    .sort((a, b) => a.point.x - b.point.x);
  const targets: FocusTarget[] = new Array(positions.length);
  order.forEach(({ index }, rank) => {
    const x = midX - span / 2 + rank * spacing;
    // 右側の住民ほど左(中央)を向く。3人の中央は正面のまま
    const center = (positions.length - 1) / 2;
    targets[index] = {
      ...onFloor({ x, y: midY }, areaId),
      flip: rank > center,
    };
  });
  return targets;
}

/**
 * 吹き出しの位置(部屋の枠に対する割合)。名札の上端を指す。
 * bob は歩行中の上下動のずれ。
 */
/** 足元の高さ(奥行き)に応じた縮尺。奥 DEPTH_SCALE_BACK 〜 手前 1 */
export function depthScale(y: number): number {
  const ratio =
    (clamp(y, FLOOR_TOP, FLOOR_BOTTOM) - FLOOR_TOP) /
    (FLOOR_BOTTOM - FLOOR_TOP);
  return DEPTH_SCALE_BACK + (1 - DEPTH_SCALE_BACK) * ratio;
}

/** 吹き出しを置く位置(名札の上)。奥に立つ住民は縮めて描くので、その分だけ下げる */
export function anchorRatio(position: Point): Point {
  const scale = depthScale(position.y);
  return {
    x: position.x / GAME_W,
    y: (position.y - (AVATAR_H + NAME_OFFSET + NAME_HEIGHT) * scale) / GAME_H,
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
