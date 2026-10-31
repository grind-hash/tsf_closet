/**
 * VRM アバターのライティング設定(three.js 非依存の数値だけを持つ)。
 *
 * three-vrm の MToon は直接光を BRDF_Lambert(1/π)で割って使うため、主光源の
 * 強さが π のとき光の当たる面がテクスチャ本来の色になる(three-vrm 公式の
 * examples/basic.html も DirectionalLight の強さに Math.PI を使う)。
 * keyScale はその π に対する倍率、半球光(環境光)はその上に足し込む分。
 */

import type { AvatarLightingPreset } from "../../../constants/companionAvatar";

export interface AvatarLightingSpec {
  /** 主光源の色 */
  keyColor: number;
  /** 主光源の強さ(π に対する倍率) */
  keyScale: number;
  hemisphereSky: number;
  hemisphereGround: number;
  hemisphereIntensity: number;
  /** MToon のパラメトリックリムの色。モデルがリムを持たない材質にだけ足す */
  rimColor: number;
  /** リムの強さ(rimColor に掛ける) */
  rimStrength: number;
}

export const AVATAR_LIGHTING_SPECS: Record<
  AvatarLightingPreset,
  AvatarLightingSpec
> = {
  standard: {
    keyColor: 0xfff8f2,
    keyScale: 0.85,
    hemisphereSky: 0xffffff,
    hemisphereGround: 0xd6ccd2,
    hemisphereIntensity: 0.75,
    rimColor: 0xe6dcff,
    rimStrength: 0.18,
  },
  bright: {
    keyColor: 0xffffff,
    keyScale: 0.9,
    hemisphereSky: 0xffffff,
    hemisphereGround: 0xe8e2e6,
    hemisphereIntensity: 0.85,
    rimColor: 0xffffff,
    rimStrength: 0.15,
  },
  sunset: {
    keyColor: 0xffd4b0,
    keyScale: 0.85,
    hemisphereSky: 0xffe6d2,
    hemisphereGround: 0x8c6e80,
    hemisphereIntensity: 0.6,
    rimColor: 0xffb070,
    rimStrength: 0.35,
  },
  night: {
    keyColor: 0xb4c2ff,
    keyScale: 0.55,
    hemisphereSky: 0x8a98d0,
    hemisphereGround: 0x342c48,
    hemisphereIntensity: 0.6,
    rimColor: 0x9bb6ff,
    rimStrength: 0.4,
  },
};

/** リムの細さ(フレネルの指数)。大きいほど輪郭のごく外側だけが光る */
export const AVATAR_RIM_FRESNEL_POWER = 5;

/**
 * 主光源の向き(モデルの注視点から見た方向)。モデルは +Z を向き、カメラは +Z 側に
 * いるため、正面やや上・やや向かって右から当てると顔全体が明るく保たれる
 */
export const AVATAR_KEY_LIGHT_DIRECTION: readonly [number, number, number] = [
  0.35, 0.75, 1,
];
