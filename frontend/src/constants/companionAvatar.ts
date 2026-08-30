/**
 * 対面会話モードの 3D アバター(VRM)向け表情・身振りの語彙。
 *
 * バックエンドの `backend/gateway/consts/companion_avatar.py` と同じキー集合を
 * 必ず維持すること。LLM はバックエンド側の語彙からキーを選ぶため、片方だけ
 * 増減すると選ばれたキーをフロントエンドで再生できなくなる。
 */

/** VRM 1.0 のプリセット表情名。0.x のモデルはライブラリ側で対応付けられる */
export const AVATAR_EXPRESSIONS = [
  "neutral",
  "happy",
  "sad",
  "angry",
  "surprised",
  "relaxed",
] as const;
export type AvatarExpressionKey = (typeof AVATAR_EXPRESSIONS)[number];

/** フロントエンドが手続き的に再生する身振り。全身モーション素材は使わない */
export const AVATAR_GESTURES = [
  "idle",
  "nod",
  "shake_head",
  "tilt_head",
  "lean_forward",
  "lean_back",
  "look_away",
  "bounce",
] as const;
export type AvatarGestureKey = (typeof AVATAR_GESTURES)[number];

export const AVATAR_EXPRESSION_DEFAULT: AvatarExpressionKey = "neutral";
export const AVATAR_GESTURE_DEFAULT: AvatarGestureKey = "idle";

/**
 * バックエンドの `_normalize_key` と同じ規則で正規化する。
 * 前後空白を除き、小文字化し、`-` と空白を `_` に置き換える。
 */
function normalizeKey<T extends string>(
  value: unknown,
  allowed: readonly T[],
): T | null {
  if (value === null || value === undefined) return null;
  const key = String(value).trim().toLowerCase().replace(/[- ]/g, "_");
  return (allowed as readonly string[]).includes(key) ? (key as T) : null;
}

/** 語彙に無い表情は null(呼び出し側で neutral に倒す) */
export function normalizeAvatarExpression(
  value: unknown,
): AvatarExpressionKey | null {
  return normalizeKey(value, AVATAR_EXPRESSIONS);
}

/** 語彙に無い身振りは null(呼び出し側で idle に倒す) */
export function normalizeAvatarGesture(
  value: unknown,
): AvatarGestureKey | null {
  return normalizeKey(value, AVATAR_GESTURES);
}
