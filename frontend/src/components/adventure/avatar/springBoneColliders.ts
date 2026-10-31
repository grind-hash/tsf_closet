/**
 * 揺れもの(SpringBone)の当たり判定を、読み込んだモデルに合わせて補正する。
 */

import type {
  VRMSpringBoneCollider,
  VRMSpringBoneColliderGroup,
  VRMSpringBoneJoint,
} from "@pixiv/three-vrm";
import * as THREE from "three";

/** 子ボーンの無いジョイントの仮想的な先端までの長さ(three-vrm と同じ値) */
const VIRTUAL_TAIL_LENGTH = 0.07;

const restTailPosition = new THREE.Vector3();
const collisionDirection = new THREE.Vector3();

/**
 * 静止姿勢の時点で揺れもの骨の先端を既に内側に含んでいるコライダーを、
 * その骨の当たり判定から外す。外した組(骨 × コライダー)の数を返す。
 *
 * 当たり判定は先端をコライダーの外へ押し出すため、配布時点で髪の根元や
 * スカートが球に埋まっているモデルでは、物理の初回で髪が逆立ったり裾が
 * 跳ね上がったりする。作者が置いた静止姿勢で重なっている組は意図した
 * 当たりではないとみなす。コライダーグループは複数の骨で共有されているため
 * 書き換えず、外すものがある骨にだけ専用のグループ配列を持たせる。
 * 読み込み直後、腕を下ろすなどの姿勢変更より前に呼ぶ。
 */
export function dropRestPoseColliderOverlaps(
  root: THREE.Object3D,
  joints: Iterable<VRMSpringBoneJoint>,
): number {
  root.updateMatrixWorld(true);
  const refreshed = new Set<VRMSpringBoneCollider>();
  let dropped = 0;
  for (const joint of joints) {
    const tail = restTail(joint, restTailPosition);
    let changed = false;
    const groups: VRMSpringBoneColliderGroup[] = [];
    for (const group of joint.colliderGroups) {
      const kept = group.colliders.filter((collider) => {
        if (!refreshed.has(collider)) {
          // colliderMatrix は updateWorldMatrix でだけ更新される
          collider.updateWorldMatrix(true, false);
          refreshed.add(collider);
        }
        const overlapping =
          collider.shape.calculateCollision(
            collider.colliderMatrix,
            tail,
            joint.settings.hitRadius,
            collisionDirection,
          ) < 0;
        if (overlapping) dropped += 1;
        return !overlapping;
      });
      if (kept.length === group.colliders.length) {
        groups.push(group);
        continue;
      }
      changed = true;
      if (kept.length > 0) groups.push({ ...group, colliders: kept });
    }
    if (changed) joint.colliderGroups = groups;
  }
  return dropped;
}

/** three-vrm と同じ規則で、静止姿勢での先端のワールド座標を求める */
function restTail(
  joint: VRMSpringBoneJoint,
  target: THREE.Vector3,
): THREE.Vector3 {
  if (joint.child) return joint.child.getWorldPosition(target);
  target
    .copy(joint.bone.position)
    .normalize()
    .multiplyScalar(VIRTUAL_TAIL_LENGTH);
  return joint.bone.localToWorld(target);
}
