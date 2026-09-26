/**
 * 同梱 Live2D 衣装の、描画にだけ関わる設定。
 *
 * どの衣装があるか(id・実行素材の URL・姿の説明)はバックエンドの
 * consts/character_chat.py が持ち、表示名は i18n にある。衣装を足したとき、
 * 寄りの構図が既定で合うならここへ書き足す必要はない。
 */

/** 寄り表示で切り取る範囲 [x, y, 幅, 高さ]。モデルのキャンバス座標(896x1280) */
export type Live2dPortraitFrame = readonly [number, number, number, number];

/** 既定の寄り。頭の上から胸元までが入る、ドレス衣装の原画に合わせた範囲 */
const DEFAULT_PORTRAIT: Live2dPortraitFrame = [203, 12, 476, 600];

/**
 * 既定では顔の位置が合わない衣装の寄り。
 *
 * バニーはうさ耳のぶん顔が下がり、中心もわずかに右にあるため、耳の先を切らない
 * まま同じ寄り具合になるよう、横位置を顔に合わせて少し縦長にしている。
 */
const PORTRAIT_FRAMES: Record<string, Live2dPortraitFrame> = {
  bunny: [211, 12, 476, 620],
};

/** 衣装の寄りの構図。未知の衣装は既定の構図で描く */
export function live2dPortraitFrame(
  costume: string | null | undefined,
): Live2dPortraitFrame {
  return (costume && PORTRAIT_FRAMES[costume]) || DEFAULT_PORTRAIT;
}
