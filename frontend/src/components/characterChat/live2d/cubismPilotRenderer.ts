// 全身 v4 専用。変形はモデル内のキーを使い、マスク・特殊合成には対応しない。
export type PilotEmotion = "neutral" | "happy" | "angry" | "sad" | "thinking";
export type PilotWeights = Record<PilotEmotion, number>;
export type PilotCamera = "full" | "portrait";

const PARAMETERS = [
  "ParamEmotionHappy",
  "ParamEmotionAngry",
  "ParamEmotionSad",
  "ParamEmotionThinking",
  "ParamEyeLOpen",
  "ParamEyeROpen",
  "ParamMouthOpenY",
  "ParamBreath",
  "ParamBodyAngleZ",
  "ParamHairImageLeft",
  "ParamHairImageRight",
  "ParamSleeveImageLeft",
  "ParamSleeveImageRight",
] as const;

interface PilotFrame {
  weights: PilotWeights;
  blink: number;
  mouth: number;
  timeSeconds: number;
  motionEnabled: boolean;
  camera: PilotCamera;
  cameraMix: number;
  /**
   * 構図を収める範囲の高さ(CSS px)。キャンバスの上端から数える。
   * キャンバスがこれより高ければ、その下へモデルの続きを描く。null はキャンバス全体。
   */
  frameHeight: number | null;
}

/**
 * Cubism Core は実行時に読み込む外部スクリプト。公式の型定義ファイルは Live2D
 * Proprietary Software License の配布物で、原本の同梱も書き写しも行わないため、
 * API の形はこのリポジトリでは宣言しない。境界をこの別名ひとつに閉じ込め、
 * 正しく読み込めたかは loadCore の存在確認と、moc の整合性・必要パラメータの
 * 有無・WebGL の実行時チェックで担保する。
 */
// biome-ignore lint/suspicious/noExplicitAny: 型を持たない外部スクリプトとの境界
type CubismCore = any;

/** 読み込み済みの Cubism Core。未読込なら undefined。 */
function cubismCore(): CubismCore | undefined {
  return (globalThis as { Live2DCubismCore?: CubismCore }).Live2DCubismCore;
}

/**
 * Cubism Core の配信 URL。Live2D Proprietary Software License の配布物のため
 * リポジトリには含めず、利用者が frontend/public/live2d/vendor/ (配布版は
 * backend/static/live2d/vendor/) へ配置する。
 */
export const LIVE2D_CORE_URL = "/live2d/vendor/live2dcubismcore.min.js";

let coreLoading: Promise<void> | null = null;
let coreAvailable: Promise<boolean> | null = null;

/**
 * Core が配置されているかを調べる。選択肢の出し分けに使う。
 *
 * 未配置のパスは開発サーバー・配布版のどちらも SPA フォールバックで index.html を
 * 200 で返すため、ステータスだけでは判定できない。Content-Type が HTML でないこと
 * まで見る。FastAPI は GET に HEAD を自動追加しないので GET で取得し、ヘッダを
 * 読んだ時点で本体を捨てる。
 */
export function live2dCoreAvailable(): Promise<boolean> {
  if (cubismCore()) return Promise.resolve(true);
  if (coreAvailable) return coreAvailable;
  coreAvailable = fetch(LIVE2D_CORE_URL)
    .then((response) => {
      void response.body?.cancel();
      const type = response.headers.get("content-type") ?? "";
      return response.ok && !type.includes("text/html");
    })
    .catch(() => false);
  return coreAvailable;
}

/** 配置し直した後に調べ直せるよう、判定結果を捨てる。 */
export function resetLive2dCoreAvailable(): void {
  coreAvailable = null;
}

function loadCore(): Promise<void> {
  if (cubismCore()) return Promise.resolve();
  if (coreLoading) return coreLoading;
  coreLoading = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    const finish = (error?: Error) => {
      clearTimeout(timeout);
      script.onload = null;
      script.onerror = null;
      if (error) {
        script.remove();
        reject(error);
      } else resolve();
    };
    const timeout = window.setTimeout(
      () => finish(new Error("Cubism Core の読み込みがタイムアウトしました")),
      20_000,
    );
    script.src = LIVE2D_CORE_URL;
    script.onload = () =>
      finish(
        cubismCore() ? undefined : new Error("Cubism Core を初期化できません"),
      );
    script.onerror = () => finish(new Error("Cubism Core を読み込めません"));
    document.head.append(script);
  }).catch((error: unknown) => {
    coreLoading = null;
    throw error;
  });
  return coreLoading;
}

interface ModelSettings {
  FileReferences: { Moc: string; Textures: string[] };
}

export class CubismPilotRenderer {
  private moc: CubismCore | null = null;
  private model: CubismCore | null = null;
  private gl: WebGLRenderingContext | null = null;
  private program: WebGLProgram | null = null;
  private shaders: WebGLShader[] = [];
  private textures: WebGLTexture[] = [];
  private buffers: WebGLBuffer[] = [];
  private parameterIds = new Map<string, number>();
  private canvas: HTMLCanvasElement | null = null;
  private view = [0, 0, 0, 0];
  private position = -1;
  private uv = -1;
  private opacity: WebGLUniformLocation | null = null;
  private viewUniform: WebGLUniformLocation | null = null;

  static async create(
    canvas: HTMLCanvasElement,
    modelUrl: string,
    signal: AbortSignal,
  ) {
    const renderer = new CubismPilotRenderer();
    try {
      await renderer.load(canvas, modelUrl, signal);
      return renderer;
    } catch (error) {
      renderer.dispose();
      throw error;
    }
  }

  private async load(
    canvas: HTMLCanvasElement,
    modelUrl: string,
    signal: AbortSignal,
  ) {
    await loadCore();
    signal.throwIfAborted();
    const get = async (url: string | URL) => {
      const response = await fetch(url, { signal });
      if (!response.ok) throw new Error("Live2D の実行素材を読み込めません");
      return response;
    };
    const settings: ModelSettings = await (await get(modelUrl)).json();
    const base = new URL(modelUrl, location.href);
    const bytes = await (
      await get(new URL(settings.FileReferences.Moc, base))
    ).arrayBuffer();
    signal.throwIfAborted();
    this.moc = cubismCore().Moc.fromArrayBuffer(bytes);
    if (this.moc?.hasMocConsistency(bytes) !== 1)
      throw new Error("Live2D モデルの整合性を確認できません");
    this.model = cubismCore().Model.fromMoc(this.moc);
    if (!this.model) throw new Error("Live2D モデルを初期化できません");
    const model = this.model;
    const d = model.drawables;
    // Core の配列ビュー末尾を含めず、実在する Drawable だけを検査する。
    if (
      model.offscreens.count ||
      Array.from(
        { length: d.count },
        (_, i) => d.maskCounts[i] || d.blendModes[i],
      ).some(Boolean)
    )
      throw new Error("この Live2D モデルの描画形式には対応していません");
    const parameterIds: string[] = model.parameters.ids;
    this.parameterIds = new Map(parameterIds.map((id, index) => [id, index]));
    for (const id of PARAMETERS) {
      if (!this.parameterIds.has(id))
        throw new Error(`必要な Live2D パラメータがありません: ${id}`);
    }
    this.canvas = canvas;
    let contextError = "";
    const onContextError = (event: Event) => {
      contextError = (event as WebGLContextEvent).statusMessage;
    };
    canvas.addEventListener("webglcontextcreationerror", onContextError);
    const gl = canvas.getContext("webgl", {
      alpha: true,
      premultipliedAlpha: true,
    });
    canvas.removeEventListener("webglcontextcreationerror", onContextError);
    if (!gl) throw new Error(`WebGL を使用できません: ${contextError}`);
    this.gl = gl;
    const shader = (type: number, code: string) => {
      const item = gl.createShader(type);
      if (!item) throw new Error("シェーダーを作成できません");
      this.shaders.push(item);
      gl.shaderSource(item, code);
      gl.compileShader(item);
      if (!gl.getShaderParameter(item, gl.COMPILE_STATUS))
        throw new Error("シェーダーをコンパイルできません");
      return item;
    };
    const program = gl.createProgram();
    if (!program) throw new Error("描画プログラムを作成できません");
    this.program = program;
    gl.attachShader(
      program,
      shader(
        gl.VERTEX_SHADER,
        `attribute vec2 position;
attribute vec2 uv;
uniform vec3 canvasInfo;
uniform vec4 view;
varying vec2 textureUv;
void main() {
  vec2 p = vec2(position.x * canvasInfo.z + canvasInfo.x, canvasInfo.y - position.y * canvasInfo.z);
  vec2 clip = (p - view.xy) / view.zw * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  textureUv = vec2(uv.x, 1.0 - uv.y);
}`,
      ),
    );
    gl.attachShader(
      program,
      shader(
        gl.FRAGMENT_SHADER,
        "precision mediump float;uniform sampler2D texture0;uniform float opacity;varying vec2 textureUv;void main(){vec4 c=texture2D(texture0,textureUv);gl_FragColor=vec4(c.rgb*c.a,c.a)*opacity;}",
      ),
    );
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS))
      throw new Error("描画プログラムをリンクできません");
    // biome-ignore lint/correctness/useHookAtTopLevel: WebGL API であり React Hook ではない
    gl.useProgram(program);
    this.position = gl.getAttribLocation(program, "position");
    this.uv = gl.getAttribLocation(program, "uv");
    this.opacity = gl.getUniformLocation(program, "opacity");
    this.viewUniform = gl.getUniformLocation(program, "view");
    const info = model.canvasinfo;
    this.view = [0, 0, info.CanvasWidth, info.CanvasHeight];
    gl.uniform3f(
      gl.getUniformLocation(program, "canvasInfo"),
      info.CanvasOriginX,
      info.CanvasOriginY,
      info.PixelsPerUnit,
    );
    gl.uniform1i(gl.getUniformLocation(program, "texture0"), 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.CULL_FACE);
    for (const file of settings.FileReferences.Textures) {
      const blob = await (await get(new URL(file, base))).blob();
      const bitmap = await createImageBitmap(blob, {
        premultiplyAlpha: "none",
      });
      try {
        signal.throwIfAborted();
        const texture = gl.createTexture();
        if (!texture) throw new Error("テクスチャを作成できません");
        this.textures.push(texture);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(
          gl.TEXTURE_2D,
          0,
          gl.RGBA,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          bitmap,
        );
        for (const name of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER])
          gl.texParameteri(gl.TEXTURE_2D, name, gl.LINEAR);
        for (const name of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T])
          gl.texParameteri(gl.TEXTURE_2D, name, gl.CLAMP_TO_EDGE);
      } finally {
        bitmap.close();
      }
    }
    for (let i = 0; i < d.count; i++) {
      for (let j = 0; j < 3; j++) {
        const buffer = gl.createBuffer();
        if (!buffer) throw new Error("描画バッファーを作成できません");
        this.buffers.push(buffer);
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers[i * 3 + 1]);
      gl.bufferData(gl.ARRAY_BUFFER, d.vertexUvs[i], gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.buffers[i * 3 + 2]);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, d.indices[i], gl.STATIC_DRAW);
    }
  }

  render(state: PilotFrame) {
    const { gl, model, program } = this;
    const canvas = this.canvas;
    if (!gl || !model || !program || !canvas) return;
    if (gl.isContextLost()) throw new Error("WebGL コンテキストが失われました");
    const { weights, blink, mouth, timeSeconds: t, motionEnabled } = state;
    // v4 デモと同じ周期・振幅。物理演算や表示側の頂点変形は行わない。
    const values: Record<(typeof PARAMETERS)[number], number> = {
      ParamEmotionHappy: weights.happy,
      ParamEmotionAngry: weights.angry,
      ParamEmotionSad: weights.sad,
      ParamEmotionThinking: weights.thinking,
      ParamEyeLOpen: 1 - blink,
      ParamEyeROpen: 1 - blink,
      ParamMouthOpenY: mouth,
      ParamBreath: motionEnabled ? 0.35 * (1 - Math.cos(1.65 * t)) : 0,
      ParamBodyAngleZ: motionEnabled ? 5 * Math.sin(0.78 * t) : 0,
      ParamHairImageLeft: motionEnabled ? 0.45 * Math.sin(1.18 * t) : 0,
      ParamHairImageRight: motionEnabled ? 0.45 * Math.sin(1.18 * t + 0.6) : 0,
      ParamSleeveImageLeft: motionEnabled ? 0.45 * Math.sin(1.65 * t - 0.4) : 0,
      ParamSleeveImageRight: motionEnabled
        ? 0.45 * Math.sin(1.65 * t - 0.05)
        : 0,
    };
    const parameters = model.parameters;
    for (const [id, value] of Object.entries(values)) {
      const index = this.parameterIds.get(id);
      if (index !== undefined)
        parameters.values[index] = Number.isFinite(value)
          ? Math.max(
              parameters.minimumValues[index],
              Math.min(parameters.maximumValues[index], value),
            )
          : parameters.defaultValues[index];
    }
    model.update();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    // 寄り表示の範囲は v4 原画の座標。全身と同じモデルを使う。
    const info = model.canvasinfo;
    const target =
      state.camera === "portrait"
        ? [203, 12, 476, 600]
        : [0, 0, info.CanvasWidth, info.CanvasHeight];
    for (let i = 0; i < 4; i++)
      this.view[i] += (target[i] - this.view[i]) * state.cameraMix;
    const [x, y, w, h] = this.view;
    const frame =
      state.frameHeight === null
        ? height
        : Math.min(height, Math.max(1, Math.round(state.frameHeight * ratio)));
    const fit = Math.min(width / w, frame / h);
    const viewWidth = width / fit;
    const viewHeight = height / fit;
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    // biome-ignore lint/correctness/useHookAtTopLevel: WebGL API であり React Hook ではない
    gl.useProgram(program);
    gl.uniform4f(
      this.viewUniform,
      x - (viewWidth - w) / 2,
      // 全身は 2D 立ち絵の object-position: bottom center にそろえ、寄りは構図の範囲の中央に置く。
      y - (frame / fit - h) * (state.camera === "full" ? 1 : 0.5),
      viewWidth,
      viewHeight,
    );
    const d = model.drawables;
    const orders = model.getRenderOrders();
    const order = Array.from({ length: d.count }, (_, i) => i).sort(
      (a, b) => orders[a] - orders[b],
    );
    for (const i of order) {
      if (d.opacities[i] < 0.0001) continue;
      gl.bindTexture(gl.TEXTURE_2D, this.textures[d.textureIndices[i]]);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers[i * 3]);
      gl.bufferData(gl.ARRAY_BUFFER, d.vertexPositions[i], gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(this.position);
      gl.vertexAttribPointer(this.position, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers[i * 3 + 1]);
      gl.enableVertexAttribArray(this.uv);
      gl.vertexAttribPointer(this.uv, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.buffers[i * 3 + 2]);
      gl.uniform1f(this.opacity, d.opacities[i]);
      gl.drawElements(gl.TRIANGLES, d.indexCounts[i], gl.UNSIGNED_SHORT, 0);
    }
    d.resetDynamicFlags();
  }

  dispose() {
    const gl = this.gl;
    if (gl) {
      for (const buffer of this.buffers) gl.deleteBuffer(buffer);
      for (const texture of this.textures) gl.deleteTexture(texture);
      for (const shader of this.shaders) gl.deleteShader(shader);
      if (this.program) gl.deleteProgram(this.program);
    }
    this.model?.release();
    this.moc?._release();
    this.model = null;
    this.moc = null;
    this.gl = null;
    this.canvas = null;
    this.program = null;
    this.buffers = [];
    this.textures = [];
    this.shaders = [];
  }
}
