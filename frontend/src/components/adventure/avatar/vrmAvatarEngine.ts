/**
 * VRM アバターの描画エンジン(React 非依存)。
 *
 * three.js + @pixiv/three-vrm で VRM を読み込み、対面会話モードのステージ上で
 * 呼吸・まばたき・視線・口パク・表情・手続き的な身振りを毎フレーム合成する。
 * 全身モーション素材は使わず、頭・背骨・腰の回転と位置だけを動かす。
 */

import { type VRM, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
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
  addPose,
  BLINK_CLOSE_SEC,
  BLINK_OPEN_SEC,
  blinkWeight,
  GESTURE_CLIPS,
  gestureDuration,
  idlePose,
  mouthWeightsFromLevel,
  nextBlinkDelay,
  sampleGesture,
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
/**
 * 腕を下ろす角度(rad)。VRM の rest は T/A ポーズなので初期姿勢で下げる。
 * normalized bone では左腕(+X 方向)を Z 軸の正回転で下げる(負だと万歳になる)
 */
const ARM_LOWER_ANGLE = 1.15;
const LOWER_ARM_BEND = 0.2;
/** 上半身の見せ方: 外接ボックスの上端からモデル全高のこの割合までを収める */
const FRAME_VISIBLE_RATIO = 0.62;
const FRAME_HEADROOM_RATIO = 0.06;

interface RestPose {
  head: THREE.Euler;
  spine: THREE.Euler;
  hipsY: number;
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

  function applyRestPose(model: VRM): RestPose {
    const humanoid = model.humanoid;
    const leftUpperArm = humanoid.getNormalizedBoneNode("leftUpperArm");
    const rightUpperArm = humanoid.getNormalizedBoneNode("rightUpperArm");
    const leftLowerArm = humanoid.getNormalizedBoneNode("leftLowerArm");
    const rightLowerArm = humanoid.getNormalizedBoneNode("rightLowerArm");
    if (leftUpperArm) leftUpperArm.rotation.z = ARM_LOWER_ANGLE;
    if (rightUpperArm) rightUpperArm.rotation.z = -ARM_LOWER_ANGLE;
    if (leftLowerArm) leftLowerArm.rotation.z = LOWER_ARM_BEND;
    if (rightLowerArm) rightLowerArm.rotation.z = -LOWER_ARM_BEND;
    const head = humanoid.getNormalizedBoneNode("head");
    const spine = humanoid.getNormalizedBoneNode("spine");
    const hips = humanoid.getNormalizedBoneNode("hips");
    return {
      head: head ? head.rotation.clone() : new THREE.Euler(),
      spine: spine ? spine.rotation.clone() : new THREE.Euler(),
      hipsY: hips ? hips.position.y : 0,
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
    rest = applyRestPose(loaded);
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
    if (head) {
      head.rotation.set(
        restPose.head.x + pose.headPitch,
        restPose.head.y + pose.headYaw,
        restPose.head.z + pose.headRoll,
      );
    }
    if (spine) spine.rotation.x = restPose.spine.x + pose.spinePitch;
    if (hips) hips.position.y = restPose.hipsY + pose.hipsY;
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
