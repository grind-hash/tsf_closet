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
import { smoothLevel } from "../../../utils/voiceLevelMeter";
import {
  ARM_REST,
  type ArmChannels,
  type ArmSide,
  addPose,
  armChannels,
  axisBetween,
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  blinkWeight,
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
  mouthWeightsFromLevel,
  nextBlinkDelay,
  poseToBoneRotation,
  sampleGesture,
  UP,
  type Vec3,
  ZERO_POSE,
} from "./avatarMotion";

export interface VrmAvatarEngineOptions {
  canvas: HTMLCanvasElement;
  /** キャンバスの親。サイズはこの要素に追従する */
  container: HTMLElement;
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
  /** 前腕のひねり軸。rest の骨軸(±X)と平行で、手のひら(rest で下向き)を前方へ向ける */
  twistAxis: THREE.Vector3;
  /** 手ボーン。ひねりの半分を受け持つ(無いモデルは前腕が全部受ける) */
  hand: THREE.Object3D | null;
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
 * 同じ指の各関節に共通の軸を使う(rest では指は一直線なので十分)
 */
function applyFingerCurl(humanoid: VRMHumanoid, side: ArmSide): void {
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
  }
}

/**
 * 腕を体側へ下ろし、肘を前へ曲げ、指を軽く握った待機姿勢にする。
 * 回転軸は実際のボーンの向きから求めるので、腕が +X に伸びる VRM 1.0 でも
 * -X に伸びる 0.x でも同じ見た目になる。軸はすべてリグへ保存し、
 * 身振り再生中は applyArmPose が同じ軸で毎フレーム組み直す
 */
function applyArmRestPose(humanoid: VRMHumanoid, facing: Facing): ArmRig[] {
  const forward: Vec3 = [0, 0, facing];
  const rigs: ArmRig[] = [];
  for (const side of ARM_SIDES) {
    const upperArm = humanoid.getNormalizedBoneNode(`${side}UpperArm`);
    const lowerArm = humanoid.getNormalizedBoneNode(`${side}LowerArm`);
    const hand = humanoid.getNormalizedBoneNode(`${side}Hand`);
    const armDir = boneDirection(lowerArm);
    if (!upperArm || !lowerArm || !armDir) continue;
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
      hand,
    };
    applyArmPose(rig, armChannels(ZERO_POSE, side));
    applyFingerCurl(humanoid, side);
    rigs.push(rig);
  }
  return rigs;
}

const armPoseQuat = new THREE.Quaternion();

/**
 * 片腕の回転を組み直す。上腕は「下ろす(lift ぶん戻す)→ 前へ振る」、
 * 前腕は「手のひらをひねる → 肘を前へ曲げる → 前額面で上へ振り上げる」の順。
 * 肘は待機角より逆(伸展)側へは曲げない。ひねりは前腕と手に半分ずつ配り、
 * 手首・肘まわりのメッシュのねじれを抑える
 */
function applyArmPose(rig: ArmRig, arm: ArmChannels): void {
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
  let smoothedLevel = 0;

  let blinkTimer = nextBlinkDelay(Math.random);
  let blinkElapsed = -1;

  const frameSpan = { bottom: 0, top: 1.6 };

  function resize(): void {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
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
    const arms = applyArmRestPose(humanoid, facing);
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
      [...EMOTION_PRESETS, "aa", "ih", "ou", "blink"].filter(
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
    let raw = 0;
    try {
      raw = getLevel();
    } catch {
      raw = 0;
    }
    smoothedLevel = smoothLevel(smoothedLevel, raw, delta);
    const weights = mouthWeightsFromLevel(smoothedLevel, elapsed);
    if (availableExpressions.has("aa")) manager.setValue("aa", weights.aa);
    if (availableExpressions.has("ih")) manager.setValue("ih", weights.ih);
    if (availableExpressions.has("ou")) manager.setValue("ou", weights.ou);
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

  return { load, setExpression, playGesture, setLevelSource, dispose };
}
