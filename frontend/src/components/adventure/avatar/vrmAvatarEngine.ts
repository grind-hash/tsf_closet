/**
 * VRM アバターの描画エンジン(React 非依存)。
 *
 * three.js + @pixiv/three-vrm で VRM を読み込み、対面会話モードのステージ上で
 * 呼吸・まばたき・視線・口パク・表情・手続き的な身振りを毎フレーム合成する。
 * 全身モーション素材は使わず、読込時に腕・肘・指を力を抜いた待機姿勢へ置き、
 * 以降は頭・背骨・腰と、腕の持ち上げ・前振り・肘の曲げを毎フレーム組み直して
 * 動かす。
 */

import {
  type VRM,
  type VRMHumanBoneName,
  type VRMHumanoid,
  VRMLoaderPlugin,
  VRMUtils,
} from "@pixiv/three-vrm";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  AVATAR_EXPRESSION_DEFAULT,
  AVATAR_GESTURE_DEFAULT,
  type AvatarExpressionKey,
  type AvatarGestureKey,
} from "../../../constants/companionAvatar";
import type { VisemeFrame } from "../../../utils/visemeTimeline";
import { smoothLevel } from "../../../utils/voiceLevelMeter";
import {
  ARM_REST,
  type ArmChannels,
  type ArmSide,
  type AvatarRestPose,
  addPose,
  addV,
  approachMouthTargets,
  armChannels,
  axisBetween,
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  blinkWeight,
  CLOSED_MOUTH_TARGETS,
  claspHold,
  claspPalm,
  claspTargets,
  DOWN,
  detectFacing,
  type Facing,
  FINGER_CURL,
  FINGER_NAMES,
  FINGER_SEGMENTS,
  fingerBoneName,
  GESTURE_CLIPS,
  gestureDuration,
  idlePose,
  lengthV,
  type MouthTargets,
  mouthWeightsFromLevel,
  mouthWeightsFromViseme,
  nextBlinkDelay,
  poseToBoneRotation,
  sampleGesture,
  scaleV,
  solveArmIk,
  subV,
  THUMB_TUCK,
  UP,
  type Vec3,
  ZERO_POSE,
} from "./avatarMotion";

export interface VrmAvatarEngineOptions {
  canvas: HTMLCanvasElement;
  /**
   * キャンバスの親。構図(上半身の収まり)はこの要素の高さで決める。
   * キャンバスを CSS で親より下へはみ出させると、はみ出した分にモデルの続きを描く
   */
  container: HTMLElement;
  /** 待機姿勢の種類。既定は腕を体側へ下ろす relaxed */
  restPose?: AvatarRestPose;
  onError: (error: unknown) => void;
}

export interface VrmAvatarLoadResult {
  specVersion: "0" | "1";
  /** このモデルに無いプリセット表情(0.x の surprised など) */
  missingExpressions: string[];
}

export interface VrmAvatarEngine {
  load: (url: string) => Promise<VrmAvatarLoadResult>;
  setExpression: (key: AvatarExpressionKey | null) => void;
  playGesture: (key: AvatarGestureKey | null) => void;
  setLevelSource: (getLevel: () => number) => void;
  /**
   * viseme 口パクの供給元。null を返す間は音量ベースの口パクへ
   * フォールバックする。解除は null を渡す
   */
  setVisemeSource: (source: (() => VisemeFrame | null) | null) => void;
  /** 待機姿勢の種類を切り替える(読み込み済みのモデルへ即座に反映する) */
  setRestPose: (pose: AvatarRestPose) => void;
  dispose: () => void;
}

/** 感情プリセット。neutral は「すべて 0」で表す */
const EMOTION_PRESETS = [
  "happy",
  "sad",
  "angry",
  "surprised",
  "relaxed",
] as const;
type EmotionPreset = (typeof EMOTION_PRESETS)[number];

const MAX_PIXEL_RATIO = 1.5;
const CAMERA_FOV_DEG = 18;
const EXPRESSION_FADE_TAU = 0.12;
const EXPRESSION_MAX_WEIGHT = 0.9;
/** 上半身の見せ方: 外接ボックスの上端からモデル全高のこの割合までを収める */
const FRAME_VISIBLE_RATIO = 0.62;
const FRAME_HEADROOM_RATIO = 0.06;

/** 片腕のリグ。待機姿勢を基準に、毎フレーム持ち上げ・前振り・肘の曲げを組み直す */
interface ArmRig {
  side: ArmSide;
  upperArm: THREE.Object3D;
  lowerArm: THREE.Object3D;
  /** 上腕を体側へ下ろす回転軸(rest 局所系) */
  lowerAxis: THREE.Vector3;
  /** T ポーズから下ろす角度 */
  lowerAngle: number;
  /** 下ろした腕を前方へ振る回転軸 */
  forwardAxis: THREE.Vector3;
  /** 前方へ振る待機角。armForward を加算する */
  forwardRest: number;
  /** 肘を前方へ曲げる回転軸 */
  bendAxis: THREE.Vector3;
  /** 肘の待機曲げ角。elbow を加算する(0 未満には曲げない) */
  bendRest: number;
  /** 前腕を前額面で上へ振り上げる回転軸 */
  upAxis: THREE.Vector3;
  /**
   * 手を体の前で重ねた姿勢(2 ボーン IK の解)。clasped のときだけ入り、
   * 腕を動かす身振りの間は claspHold の割合だけ関節角の姿勢へ戻す
   */
  clasp: {
    upper: THREE.Quaternion;
    fore: THREE.Quaternion;
    hand: THREE.Quaternion;
  } | null;
  /** 前腕のひねり軸。rest の骨軸(±X)と平行で、手のひら(rest で下向き)を前方へ向ける */
  twistAxis: THREE.Vector3;
  /** 手ボーン。ひねりの半分を受け持つ(無いモデルは前腕が全部受ける) */
  hand: THREE.Object3D | null;
  /** rest での上腕の向き(単位ベクトル)。IK の基準になる */
  armDir: Vec3;
  /** rest での前腕の向き。T ポーズが完全な直線でないモデルがあるため別に持つ */
  foreDir: Vec3;
  /** rest での肩・上腕・前腕の寸法(normalized bone の局所系)。IK に使う */
  shoulder: Vec3 | null;
  upperLength: number;
  foreLength: number;
}

interface RestPose {
  head: THREE.Euler;
  spine: THREE.Euler;
  hipsY: number;
  hipsX: number;
  arms: ArmRig[];
  /** normalized bone の局所系での前方の Z 符号。頭・背骨の傾きの向きに使う */
  facing: Facing;
}

const ARM_SIDES: readonly ArmSide[] = ["left", "right"];

function toVec3(v: THREE.Vector3): Vec3 {
  return [v.x, v.y, v.z];
}

function axisOf(axis: Vec3): THREE.Vector3 {
  return new THREE.Vector3(axis[0], axis[1], axis[2]);
}

/**
 * 子ボーンの rest 位置から親ボーンの向きを求める。
 * normalized bone は rest の局所系がワールド系と一致するため、子の position が
 * そのまま親ボーンの伸びる方向になる
 */
function boneDirection(child: THREE.Object3D | null): Vec3 | null {
  if (!child) return null;
  const length = child.position.length();
  if (!(length > 1e-6)) return null;
  return toVec3(child.position.clone().divideScalar(length));
}

/**
 * 指を手のひら側へ軽く曲げる。指の向きは根元 2 関節の位置関係から取り、
 * 同じ指の各関節に共通の軸を使う(rest では指は一直線なので十分)。
 * 親指だけは付け根を人差し指の側へ寄せ、開いたままにしない
 */
function applyFingerCurl(humanoid: VRMHumanoid, side: ArmSide): void {
  const indexDir = boneDirection(
    humanoid.getNormalizedBoneNode(
      fingerBoneName(side, "index", "proximal") as VRMHumanBoneName,
    ),
  );
  for (const finger of FINGER_NAMES) {
    const segments = FINGER_SEGMENTS[finger];
    const curls = FINGER_CURL[finger];
    const nodes = segments.map((segment) =>
      humanoid.getNormalizedBoneNode(
        fingerBoneName(side, finger, segment) as VRMHumanBoneName,
      ),
    );
    const direction = boneDirection(nodes[1] ?? null);
    if (!direction || !nodes[0]) continue;
    const curlAxis = axisBetween(direction, DOWN);
    if (!curlAxis) continue;
    const axis = axisOf(curlAxis);
    nodes.forEach((node, index) => {
      const angle = curls[index] ?? 0;
      if (node && angle !== 0) node.quaternion.setFromAxisAngle(axis, angle);
    });
    // 親指の付け根は曲げずに、人差し指の側へ寄せる
    if (finger === "thumb" && indexDir && nodes[0]) {
      const tuckAxis = axisBetween(direction, indexDir);
      if (tuckAxis) {
        nodes[0].quaternion.setFromAxisAngle(axisOf(tuckAxis), THUMB_TUCK);
      }
    }
  }
}

/** normalized bone の位置を、normalized リグの局所系で読む */
function normalizedPosition(humanoid: VRMHumanoid, node: THREE.Object3D): Vec3 {
  node.updateWorldMatrix(true, false);
  const point = new THREE.Vector3().setFromMatrixPosition(node.matrixWorld);
  humanoid.normalizedHumanBonesRoot.worldToLocal(point);
  return [point.x, point.y, point.z];
}

interface ArmGeometry {
  shoulder: Vec3;
  upperLength: number;
  foreLength: number;
}

/** rest 姿勢のまま、肩の位置と上腕・前腕の長さを測る(手ボーンが無ければ null) */
function measureArm(
  humanoid: VRMHumanoid,
  upperArm: THREE.Object3D,
  lowerArm: THREE.Object3D,
  hand: THREE.Object3D | null,
): ArmGeometry | null {
  if (!hand) return null;
  const shoulder = normalizedPosition(humanoid, upperArm);
  const elbow = normalizedPosition(humanoid, lowerArm);
  const wrist = normalizedPosition(humanoid, hand);
  const upperLength = lengthV(subV(elbow, shoulder));
  const foreLength = lengthV(subV(wrist, elbow));
  if (upperLength <= 0 || foreLength <= 0) return null;
  return { shoulder, upperLength, foreLength };
}

/**
 * 手のひらを狙いの向きへ回すために、前腕の軸まわりに必要なひねり角を求める。
 * rest の手のひらの法線は左右とも下向き。前腕の軸に平行な成分しか無いときは 0
 */
function palmTwistAngle(
  facing: Facing,
  upper: THREE.Quaternion,
  fore: THREE.Quaternion,
  foreDirWorld: Vec3,
): number {
  const axis = new THREE.Vector3(...foreDirWorld).normalize();
  const current = new THREE.Vector3(...DOWN)
    .applyQuaternion(fore)
    .applyQuaternion(upper)
    .projectOnPlane(axis);
  const wanted = new THREE.Vector3(...claspPalm(facing)).projectOnPlane(axis);
  if (current.lengthSq() < 1e-8 || wanted.lengthSq() < 1e-8) return 0;
  current.normalize();
  wanted.normalize();
  const angle = Math.acos(Math.min(1, Math.max(-1, current.dot(wanted))));
  return current.cross(wanted).dot(axis) < 0 ? -angle : angle;
}

/**
 * 手を体の前で重ねた姿勢を 2 ボーン IK で解き、各腕へ入れる。
 *
 * 左右で腕の長さや肩の高さが違うモデルがあるため、関節角ではなく手の位置を
 * 目標にする。寸法を測れない腕(手ボーンが無い等)は組まない
 */
function solveClaspPose(rigs: ArmRig[], facing: Facing): void {
  const left = rigs.find((rig) => rig.side === "left");
  const right = rigs.find((rig) => rig.side === "right");
  if (!left?.shoulder || !right?.shoulder) {
    for (const rig of rigs) rig.clasp = null;
    return;
  }
  const shoulderMid = scaleV(addV(left.shoulder, right.shoulder), 0.5);
  const armLength =
    (left.upperLength +
      left.foreLength +
      right.upperLength +
      right.foreLength) /
    2;
  const targets = claspTargets(shoulderMid, armLength, facing);
  for (const rig of rigs) {
    // 肘は体の外側・やや後ろへ出す
    const pole = addV(scaleV(rig.armDir, 0.7), [0, 0, -facing * 0.5]);
    const solution = rig.shoulder
      ? solveArmIk({
          shoulder: rig.shoulder,
          upperLength: rig.upperLength,
          foreLength: rig.foreLength,
          target: targets[rig.side],
          pole,
        })
      : null;
    if (!solution) {
      rig.clasp = null;
      continue;
    }
    const upper = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(...rig.armDir),
      new THREE.Vector3(...solution.upperDir),
    );
    // 前腕の回転は上腕の局所系で持ち、前腕自身の rest 向きから回す
    const localFore = new THREE.Vector3(...solution.foreDir).applyQuaternion(
      upper.clone().invert(),
    );
    const fore = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(...rig.foreDir),
      localFore,
    );
    // 手のひらを狙いの向きへ。ひねりは前腕と手で半分ずつ持ち、手首のねじれを抑える
    const twist = palmTwistAngle(facing, upper, fore, solution.foreDir);
    const hand = new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(...rig.foreDir),
      twist / 2,
    );
    fore.premultiply(
      new THREE.Quaternion().setFromAxisAngle(localFore, twist / 2),
    );
    rig.clasp = { upper, fore, hand };
  }
}

/**
 * 腕を体側へ下ろし、肘を軽く曲げ、指を軽く握った待機姿勢にする。
 * clasped のときは続けて、手を体の前で重ねる姿勢を IK で解いて重ねる。
 * 回転軸は実際のボーンの向きから求めるので、腕が +X に伸びる VRM 1.0 でも
 * -X に伸びる 0.x でも同じ見た目になる。軸はすべてリグへ保存し、
 * 身振り再生中は applyArmPose が同じ軸で毎フレーム組み直す
 */
function applyArmRestPose(
  humanoid: VRMHumanoid,
  facing: Facing,
  restPose: AvatarRestPose,
): ArmRig[] {
  const forward: Vec3 = [0, 0, facing];
  const rigs: ArmRig[] = [];
  for (const side of ARM_SIDES) {
    const upperArm = humanoid.getNormalizedBoneNode(`${side}UpperArm`);
    const lowerArm = humanoid.getNormalizedBoneNode(`${side}LowerArm`);
    const hand = humanoid.getNormalizedBoneNode(`${side}Hand`);
    const armDir = boneDirection(lowerArm);
    if (!upperArm || !lowerArm || !armDir) continue;
    // 回転を当てる前に、rest の寸法を測る(手を重ねる姿勢の IK に使う)
    const geometry = measureArm(humanoid, upperArm, lowerArm, hand);
    const angles = ARM_REST[side];
    const lowerAxis = axisBetween(armDir, DOWN);
    const forwardAxis = axisBetween(DOWN, forward);
    const bendAxis = axisBetween(boneDirection(hand) ?? armDir, forward);
    const upAxis = axisBetween(armDir, UP);
    // DOWN→forward の軸は ±X で rest の骨軸と平行なので、前腕まわりの純粋な
    // ひねりになる。手のひらの rest 法線は左右とも DOWN のため、同じ回転で
    // 両手のひらが前方を向く
    const twistAxis = axisBetween(DOWN, forward);
    if (!lowerAxis || !forwardAxis || !bendAxis || !upAxis || !twistAxis)
      continue;
    const rig: ArmRig = {
      side,
      upperArm,
      lowerArm,
      lowerAxis: axisOf(lowerAxis),
      lowerAngle: angles.lower,
      forwardAxis: axisOf(forwardAxis),
      forwardRest: angles.forward,
      bendAxis: axisOf(bendAxis),
      bendRest: angles.bend,
      upAxis: axisOf(upAxis),
      twistAxis: axisOf(twistAxis),
      clasp: null,
      hand,
      armDir,
      foreDir: boneDirection(hand) ?? armDir,
      shoulder: geometry?.shoulder ?? null,
      upperLength: geometry?.upperLength ?? 0,
      foreLength: geometry?.foreLength ?? 0,
    };
    applyArmPose(rig, armChannels(ZERO_POSE, side));
    applyFingerCurl(humanoid, side);
    rigs.push(rig);
  }
  if (restPose === "clasped") solveClaspPose(rigs, facing);
  for (const rig of rigs) applyArmPose(rig, armChannels(ZERO_POSE, rig.side));
  return rigs;
}

const armPoseQuat = new THREE.Quaternion();

/**
 * 片腕の回転を組み直す。上腕は「下ろす(lift ぶん戻す)→ 前へ振る → 内旋する」、
 * 前腕は「手のひらをひねる → 肘を前へ曲げる → 前額面で上へ振り上げる」の順。
 * 肘は待機角より逆(伸展)側へは曲げない。ひねりは前腕と手に半分ずつ配り、
 * 手首・肘まわりのメッシュのねじれを抑える。
 * 手を前で組む上乗せ(内旋と肘の追加曲げ)は claspHold の割合だけ効かせ、
 * 腕を持ち上げる身振りの間は腕を下ろした姿勢から動かす
 */
function applyArmPose(rig: ArmRig, arm: ArmChannels): void {
  const hold = rig.clasp ? claspHold(arm) : 0;
  rig.upperArm.quaternion
    .setFromAxisAngle(rig.lowerAxis, rig.lowerAngle - arm.lift)
    .premultiply(
      armPoseQuat.setFromAxisAngle(
        rig.forwardAxis,
        rig.forwardRest + arm.forward,
      ),
    );
  const palm = Math.max(0, arm.palmTurn);
  const forearmTwist = rig.hand ? palm / 2 : palm;
  rig.lowerArm.quaternion
    .setFromAxisAngle(rig.twistAxis, forearmTwist)
    .premultiply(
      armPoseQuat.setFromAxisAngle(
        rig.bendAxis,
        Math.max(0, rig.bendRest + arm.elbow),
      ),
    )
    .premultiply(
      armPoseQuat.setFromAxisAngle(rig.upAxis, Math.max(0, arm.elbowUp)),
    );
  if (rig.hand) {
    rig.hand.quaternion.setFromAxisAngle(rig.twistAxis, palm - forearmTwist);
  }
  // 手を重ねた姿勢へ寄せる。身振りで腕が動くぶんだけ関節角の姿勢へ戻る
  if (rig.clasp && hold > 0) {
    rig.upperArm.quaternion.slerp(rig.clasp.upper, hold);
    rig.lowerArm.quaternion.slerp(rig.clasp.fore, hold);
    rig.hand?.quaternion.slerp(rig.clasp.hand, hold);
  }
}

interface ActiveGesture {
  key: AvatarGestureKey;
  startedAt: number;
  duration: number;
  releaseLookAt: boolean;
}

function isExpressionKey(value: string): value is EmotionPreset {
  return (EMOTION_PRESETS as readonly string[]).includes(value);
}

export function createVrmAvatarEngine(
  options: VrmAvatarEngineOptions,
): VrmAvatarEngine {
  const { canvas, container, onError } = options;
  let restPoseKind: AvatarRestPose = options.restPose ?? "relaxed";
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: "low-power",
  });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(
    Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO),
  );

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(CAMERA_FOV_DEG, 1, 0.05, 30);
  camera.position.set(0, 1.3, 3);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444466, 1.0));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
  keyLight.position.set(1, 2, 3);
  scene.add(keyLight);

  const timer = new THREE.Timer();
  let vrm: VRM | null = null;
  let rest: RestPose | null = null;
  let loadToken = 0;
  let disposed = false;
  let rafId: number | null = null;
  let elapsed = 0;

  let targetExpression: AvatarExpressionKey = AVATAR_EXPRESSION_DEFAULT;
  const expressionWeights = new Map<EmotionPreset, number>();
  let availableExpressions = new Set<string>();

  let gesture: ActiveGesture | null = null;
  let getLevel: () => number = () => 0;
  let getViseme: (() => VisemeFrame | null) | null = null;
  let smoothedLevel = 0;
  let mouthTargets: MouthTargets = { ...CLOSED_MOUTH_TARGETS };

  let blinkTimer = nextBlinkDelay(Math.random);
  let blinkElapsed = -1;

  const frameSpan = { bottom: 0, top: 1.6 };

  function resize(): void {
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    const frameHeight = Math.min(height, Math.max(1, container.clientHeight));
    renderer.setSize(width, height, false);
    // 構図は親の高さで組み、キャンバスがそれより高ければ視錐台を下へ延ばす
    camera.aspect = width / frameHeight;
    if (frameHeight < height)
      camera.setViewOffset(width, frameHeight, 0, 0, width, height);
    else camera.clearViewOffset();
    frameCamera();
  }

  /** 上半身(腰の少し下〜頭上)が縦に収まる距離を求め、下端寄せで構える */
  function frameCamera(): void {
    const span = Math.max(0.3, frameSpan.top - frameSpan.bottom);
    const halfFov = THREE.MathUtils.degToRad(CAMERA_FOV_DEG / 2);
    const distance = span / 2 / Math.tan(halfFov);
    const center = (frameSpan.top + frameSpan.bottom) / 2;
    camera.position.set(0, center, distance);
    camera.lookAt(0, center, 0);
    camera.updateProjectionMatrix();
  }

  /**
   * 外接ボックスからモデル全高を取り、頭上に少し余白を残して上半身を収める。
   * 頭ボーンの位置は頭頂より低く、髪型で高さも変わるためボーンでは測らない
   */
  function measureModel(model: VRM): void {
    model.scene.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(model.scene);
    const height = Math.max(0.5, box.max.y - box.min.y);
    frameSpan.top = box.max.y + height * FRAME_HEADROOM_RATIO;
    frameSpan.bottom = box.max.y - height * FRAME_VISIBLE_RATIO;
    frameCamera();
  }

  function applyRestPose(model: VRM, specVersion: "0" | "1"): RestPose {
    const humanoid = model.humanoid;
    const facing = detectFacing(
      boneDirection(humanoid.getNormalizedBoneNode("leftLowerArm")),
      specVersion,
    );
    const arms = applyArmRestPose(humanoid, facing, restPoseKind);
    const head = humanoid.getNormalizedBoneNode("head");
    const spine = humanoid.getNormalizedBoneNode("spine");
    const hips = humanoid.getNormalizedBoneNode("hips");
    return {
      head: head ? head.rotation.clone() : new THREE.Euler(),
      spine: spine ? spine.rotation.clone() : new THREE.Euler(),
      hipsY: hips ? hips.position.y : 0,
      hipsX: hips ? hips.position.x : 0,
      arms,
      facing,
    };
  }

  function disposeModel(): void {
    if (!vrm) return;
    scene.remove(vrm.scene);
    VRMUtils.deepDispose(vrm.scene);
    vrm = null;
    rest = null;
    gesture = null;
    availableExpressions = new Set();
    expressionWeights.clear();
  }

  async function load(url: string): Promise<VrmAvatarLoadResult> {
    const token = ++loadToken;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    const gltf = await loader.loadAsync(url);
    const loaded = gltf.userData.vrm as VRM | undefined;
    if (!loaded) {
      throw new Error("not_a_vrm");
    }
    if (disposed || token !== loadToken) {
      VRMUtils.deepDispose(loaded.scene);
      throw new Error("load_cancelled");
    }
    disposeModel();
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    VRMUtils.combineSkeletons(gltf.scene);
    const specVersion: "0" | "1" = loaded.meta.metaVersion === "0" ? "0" : "1";
    if (specVersion === "0") {
      // 0.x は -Z 向きで出力されるため 1.0 と同じ +Z 向きに揃える
      VRMUtils.rotateVRM0(loaded);
    }
    loaded.scene.traverse((object) => {
      object.frustumCulled = false;
    });
    if (loaded.lookAt) loaded.lookAt.target = camera;
    scene.add(loaded.scene);
    vrm = loaded;
    rest = applyRestPose(loaded, specVersion);
    loaded.update(0);
    measureModel(loaded);

    const manager = loaded.expressionManager;
    availableExpressions = new Set(
      [...EMOTION_PRESETS, "aa", "ih", "ou", "ee", "oh", "blink"].filter(
        (name) => manager?.getExpression(name) != null,
      ),
    );
    for (const preset of EMOTION_PRESETS) expressionWeights.set(preset, 0);
    const missingExpressions = EMOTION_PRESETS.filter(
      (preset) => !availableExpressions.has(preset),
    );
    startLoop();
    return { specVersion, missingExpressions };
  }

  function setRestPose(pose: AvatarRestPose): void {
    if (pose === restPoseKind) return;
    restPoseKind = pose;
    if (!rest) return;
    // 腕の回転は毎フレーム組み直すので、重ねる姿勢を差し替えるだけでよい
    if (pose === "clasped") solveClaspPose(rest.arms, rest.facing);
    else for (const arm of rest.arms) arm.clasp = null;
  }

  function setExpression(key: AvatarExpressionKey | null): void {
    targetExpression = key ?? AVATAR_EXPRESSION_DEFAULT;
  }

  function playGesture(key: AvatarGestureKey | null): void {
    const resolved = key ?? AVATAR_GESTURE_DEFAULT;
    if (gesture?.releaseLookAt && vrm?.lookAt) vrm.lookAt.target = camera;
    if (resolved === "idle") {
      gesture = null;
      return;
    }
    const clip = GESTURE_CLIPS[resolved];
    gesture = {
      key: resolved,
      startedAt: elapsed,
      duration: gestureDuration(resolved),
      releaseLookAt: Boolean(clip.releaseLookAt),
    };
    if (gesture.releaseLookAt && vrm?.lookAt) vrm.lookAt.target = null;
  }

  function setLevelSource(source: () => number): void {
    getLevel = source;
  }

  function setVisemeSource(source: (() => VisemeFrame | null) | null): void {
    getViseme = source;
  }

  function updateBlink(delta: number, model: VRM): void {
    if (!availableExpressions.has("blink")) return;
    if (blinkElapsed < 0) {
      blinkTimer -= delta;
      if (blinkTimer <= 0) blinkElapsed = 0;
      return;
    }
    blinkElapsed += delta;
    const weight = blinkWeight(blinkElapsed);
    model.expressionManager?.setValue("blink", weight);
    if (blinkElapsed >= BLINK_CLOSE_SEC + BLINK_OPEN_SEC) {
      blinkElapsed = -1;
      blinkTimer = nextBlinkDelay(Math.random);
      model.expressionManager?.setValue("blink", 0);
    }
  }

  function updateExpressions(delta: number, model: VRM): void {
    const manager = model.expressionManager;
    if (!manager) return;
    const k = 1 - Math.exp(-delta / EXPRESSION_FADE_TAU);
    const wanted =
      isExpressionKey(targetExpression) &&
      availableExpressions.has(targetExpression)
        ? targetExpression
        : null;
    for (const preset of EMOTION_PRESETS) {
      if (!availableExpressions.has(preset)) continue;
      const current = expressionWeights.get(preset) ?? 0;
      const target = preset === wanted ? EXPRESSION_MAX_WEIGHT : 0;
      const next = current + (target - current) * k;
      expressionWeights.set(preset, next);
      manager.setValue(preset, next);
    }
  }

  function updateMouth(delta: number, model: VRM): void {
    const manager = model.expressionManager;
    if (!manager) return;
    let frame: VisemeFrame | null = null;
    if (getViseme) {
      try {
        frame = getViseme();
      } catch {
        frame = null;
      }
    }
    let target: MouthTargets;
    if (frame) {
      // viseme 経路: タイムラインが示す口形へ追従する
      target = mouthWeightsFromViseme(
        frame.viseme,
        frame.w,
        availableExpressions.has("ee"),
        availableExpressions.has("oh"),
      );
    } else {
      // 音量経路(タイムライン無し・非再生時)。ee / oh は 0 へ戻す
      let raw = 0;
      try {
        raw = getLevel();
      } catch {
        raw = 0;
      }
      smoothedLevel = smoothLevel(smoothedLevel, raw, delta);
      const weights = mouthWeightsFromLevel(smoothedLevel, elapsed);
      target = { aa: weights.aa, ih: weights.ih, ou: weights.ou, ee: 0, oh: 0 };
    }
    // 適用値は常に mouthTargets へ書き戻し、経路切替でも口形が飛ばないようにする
    mouthTargets = approachMouthTargets(mouthTargets, target, delta);
    if (availableExpressions.has("aa")) manager.setValue("aa", mouthTargets.aa);
    if (availableExpressions.has("ih")) manager.setValue("ih", mouthTargets.ih);
    if (availableExpressions.has("ou")) manager.setValue("ou", mouthTargets.ou);
    if (availableExpressions.has("ee")) manager.setValue("ee", mouthTargets.ee);
    if (availableExpressions.has("oh")) manager.setValue("oh", mouthTargets.oh);
  }

  function updatePose(model: VRM, restPose: RestPose): void {
    let pose = idlePose(elapsed);
    if (gesture) {
      const progress = (elapsed - gesture.startedAt) / gesture.duration;
      if (progress >= 1) {
        if (gesture.releaseLookAt && model.lookAt) model.lookAt.target = camera;
        gesture = null;
      } else {
        pose = addPose(pose, sampleGesture(gesture.key, progress));
      }
    } else {
      pose = addPose(pose, ZERO_POSE);
    }
    const humanoid = model.humanoid;
    const head = humanoid.getNormalizedBoneNode("head");
    const spine = humanoid.getNormalizedBoneNode("spine");
    const hips = humanoid.getNormalizedBoneNode("hips");
    // モデル基準の「前・左」をボーン局所系の回転へ(0.x は前後・左右の傾きが反転する)
    const rotation = poseToBoneRotation(pose, restPose.facing);
    if (head) {
      head.rotation.set(
        restPose.head.x + rotation.head[0],
        restPose.head.y + rotation.head[1],
        restPose.head.z + rotation.head[2],
      );
    }
    if (spine) {
      spine.rotation.set(
        restPose.spine.x + rotation.spine[0],
        restPose.spine.y + rotation.spine[1],
        restPose.spine.z + rotation.spine[2],
      );
    }
    if (hips) {
      hips.position.y = restPose.hipsY + pose.hipsY;
      hips.position.x = restPose.hipsX + restPose.facing * pose.hipsX;
    }
    for (const arm of restPose.arms) {
      applyArmPose(arm, armChannels(pose, arm.side));
    }
  }

  function frame(): void {
    rafId = null;
    if (disposed) return;
    timer.update();
    const delta = Math.min(timer.getDelta(), 0.1);
    elapsed += delta;
    if (vrm && rest) {
      updatePose(vrm, rest);
      updateBlink(delta, vrm);
      updateExpressions(delta, vrm);
      updateMouth(delta, vrm);
      vrm.update(delta);
    }
    renderer.render(scene, camera);
    if (!document.hidden) rafId = requestAnimationFrame(frame);
  }

  function startLoop(): void {
    if (disposed || rafId !== null || document.hidden) return;
    // 停止中に溜まった経過時間を捨て、再開直後の大きな delta を防ぐ
    timer.update();
    rafId = requestAnimationFrame(frame);
  }

  function stopLoop(): void {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  const onVisibilityChange = (): void => {
    if (document.hidden) stopLoop();
    else startLoop();
  };
  const onContextLost = (event: Event): void => {
    event.preventDefault();
    stopLoop();
    onError(new Error("webgl_context_lost"));
  };
  document.addEventListener("visibilitychange", onVisibilityChange);
  canvas.addEventListener("webglcontextlost", onContextLost);
  const observer = new ResizeObserver(() => resize());
  observer.observe(container);
  observer.observe(canvas);
  resize();

  function dispose(): void {
    if (disposed) return;
    disposed = true;
    loadToken += 1;
    stopLoop();
    observer.disconnect();
    document.removeEventListener("visibilitychange", onVisibilityChange);
    canvas.removeEventListener("webglcontextlost", onContextLost);
    disposeModel();
    renderer.dispose();
    renderer.forceContextLoss();
  }

  return {
    load,
    setExpression,
    playGesture,
    setLevelSource,
    setVisemeSource,
    setRestPose,
    dispose,
  };
}
