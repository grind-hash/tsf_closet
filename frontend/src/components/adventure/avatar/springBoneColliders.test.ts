import {
  VRMSpringBoneCollider,
  type VRMSpringBoneColliderGroup,
  VRMSpringBoneColliderShapeSphere,
  VRMSpringBoneJoint,
} from "@pixiv/three-vrm";
import { Object3D, Vector3 } from "three";
import { describe, expect, it } from "vitest";
import { dropRestPoseColliderOverlaps } from "./springBoneColliders";

function sphere(
  parent: Object3D,
  offset: Vector3,
  radius: number,
): VRMSpringBoneCollider {
  const collider = new VRMSpringBoneCollider(
    new VRMSpringBoneColliderShapeSphere({ offset, radius }),
  );
  parent.add(collider);
  return collider;
}

/**
 * root 直下の骨と、その先端(子)を作る。VRMSpringBoneJoint は骨の
 * matrixAutoUpdate を切るため、読み込み済みモデルと同じく行列を先に確定させる
 */
function chain(
  root: Object3D,
  at: Vector3,
  tail: Vector3 | null,
): { bone: Object3D; child: Object3D | null } {
  const bone = new Object3D();
  bone.position.copy(at);
  bone.updateMatrix();
  root.add(bone);
  if (!tail) return { bone, child: null };
  const child = new Object3D();
  child.position.copy(tail);
  bone.add(child);
  return { bone, child };
}

describe("dropRestPoseColliderOverlaps", () => {
  it("静止時に先端を含むコライダーだけを、その骨から外す", () => {
    const root = new Object3D();
    const buried = sphere(root, new Vector3(0, -0.1, 0), 0.05);
    const clear = sphere(root, new Vector3(0.5, 0, 0), 0.05);
    const shared: VRMSpringBoneColliderGroup = {
      name: "head",
      colliders: [buried, clear],
    };
    const near = chain(root, new Vector3(0, 0, 0), new Vector3(0, -0.1, 0));
    const far = chain(root, new Vector3(0, 1, 0), new Vector3(0, -0.1, 0));
    const nearJoint = new VRMSpringBoneJoint(near.bone, near.child, {}, [
      shared,
    ]);
    const farJoint = new VRMSpringBoneJoint(far.bone, far.child, {}, [shared]);

    const dropped = dropRestPoseColliderOverlaps(root, [nearJoint, farJoint]);

    expect(dropped).toBe(1);
    expect(nearJoint.colliderGroups).toHaveLength(1);
    expect(nearJoint.colliderGroups[0].colliders).toEqual([clear]);
    expect(nearJoint.colliderGroups[0].name).toBe("head");
    // 共有グループ自体と、重ならない骨の参照は変えない
    expect(shared.colliders).toEqual([buried, clear]);
    expect(farJoint.colliderGroups[0]).toBe(shared);
  });

  it("すべて重なるグループは骨から取り除く", () => {
    const root = new Object3D();
    const group: VRMSpringBoneColliderGroup = {
      colliders: [sphere(root, new Vector3(0, -0.1, 0), 0.05)],
    };
    const { bone, child } = chain(
      root,
      new Vector3(0, 0, 0),
      new Vector3(0, -0.1, 0),
    );
    const joint = new VRMSpringBoneJoint(bone, child, {}, [group]);

    expect(dropRestPoseColliderOverlaps(root, [joint])).toBe(1);
    expect(joint.colliderGroups).toEqual([]);
  });

  it("当たり半径(hitRadius)も含めて重なりを判定する", () => {
    const root = new Object3D();
    const group: VRMSpringBoneColliderGroup = {
      colliders: [sphere(root, new Vector3(0, -0.2, 0), 0.05)],
    };
    const { bone, child } = chain(
      root,
      new Vector3(0, 0, 0),
      new Vector3(0, -0.1, 0),
    );
    const thin = new VRMSpringBoneJoint(bone, child, { hitRadius: 0.02 }, [
      group,
    ]);
    const thick = new VRMSpringBoneJoint(bone, child, { hitRadius: 0.06 }, [
      group,
    ]);

    expect(dropRestPoseColliderOverlaps(root, [thin, thick])).toBe(1);
    expect(thin.colliderGroups).toEqual([group]);
    expect(thick.colliderGroups).toEqual([]);
  });

  it("子の無い骨は親からの向きに 7cm 伸ばした先端で判定する", () => {
    const root = new Object3D();
    const group: VRMSpringBoneColliderGroup = {
      colliders: [sphere(root, new Vector3(0, -1.07, 0), 0.01)],
    };
    const { bone } = chain(root, new Vector3(0, -1, 0), null);
    const joint = new VRMSpringBoneJoint(bone, null, {}, [group]);

    expect(dropRestPoseColliderOverlaps(root, [joint])).toBe(1);
  });

  it("重なりが無ければ何も変えない", () => {
    const root = new Object3D();
    const group: VRMSpringBoneColliderGroup = {
      colliders: [sphere(root, new Vector3(0.5, 0, 0), 0.05)],
    };
    const { bone, child } = chain(
      root,
      new Vector3(0, 0, 0),
      new Vector3(0, -0.1, 0),
    );
    const groups = [group];
    const joint = new VRMSpringBoneJoint(bone, child, {}, groups);

    expect(dropRestPoseColliderOverlaps(root, [joint])).toBe(0);
    expect(joint.colliderGroups).toBe(groups);
  });
});
