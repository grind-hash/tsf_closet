/**
 * 箱庭の部屋ステージ(Phaser 3)。
 *
 * 背景と住民を描き、住民の徘徊と、出来事の再生で参加住民を集める動きを担当する。
 * 吹き出しとキャプションは React(DOM)側が重ね、このモジュールは吹き出しの位置と
 * 住民のクリックを知らせる。箱庭の画面を開いたときだけ動的 import で読み込む。
 */

import Phaser from "phaser";
import {
  AVATAR_H,
  anchorRatio,
  approach,
  BREATH_PERIOD_MS,
  BREATH_STRETCH,
  brakePoint,
  depthScale,
  focusTargets,
  focusZone,
  GAME_H,
  GAME_W,
  IDLE_MAX_MS,
  IDLE_MIN_MS,
  initialPosition,
  isPathBlocked,
  NAME_OFFSET,
  nearestWithin,
  onFloor,
  type Point,
  pickWanderTarget,
  STEP_STRETCH,
  stepToward,
  TURN_MIN_DX,
  TURN_MIN_WIDTH,
  TURN_MS,
  WALK_BLEND_MS,
  WALK_SPEED,
  WALK_SWAY,
  WALK_SWAY_SPEED,
  walkSpeedFactor,
  type XRange,
  yJitter,
} from "./roomLayout";

/** 部屋の住民の表示情報 */
export interface StageResident {
  id: string;
  name: string;
  /** 表示する画像(背景を透過済みの URL)。無ければ頭文字の仮の姿 */
  imageUrl: string | null;
}

/** 部屋に置く家具(スロットの位置に足元を合わせて描く) */
export interface StageFurniture {
  key: string;
  url: string;
  x: number;
  y: number;
  height: number;
  /** 幅と深さは家具の底面に合わせる */
  shadowWidth: number;
}

export interface RoomStageCallbacks {
  onResidentClick?: (residentId: string) => void;
}

export interface RoomStageHandle {
  update: (
    residents: StageResident[],
    backgroundUrl: string | null,
    areaId: string,
    furniture?: StageFurniture[],
  ) => void;
  /** 参加住民を集めて向き合わせる。全員が着くか見切り時間で解決する */
  focusGroup: (ids: string[]) => Promise<boolean>;
  releaseFocus: () => void;
  setSelected: (id: string | null) => void;
  setInvolved: (ids: string[]) => void;
  /** 動きを止める(OS の「動きを減らす」)。止めても住民の表示はそのまま */
  setMotionEnabled: (enabled: boolean) => void;
  /** 吹き出しの位置(部屋の枠に対する割合)。住民がいなければ null */
  getAnchor: (id: string) => Point | null;
  destroy: () => void;
}

const FOCUS_TIMEOUT_MS = 5000;
/** 足元の影: ぼかした楕円の質感(中心が濃く、縁へ消える) */
const SHADOW_TEXTURE = "hakoniwa-shadow";
/**
 * 足の裏に密着させる濃い影と、周りに広がる薄い影(幅・高さ・濃さ・中心の y)。
 * 立ち絵は足を正面から描いているので、床に触れる位置は画像の下端(つま先)より少し上
 * (かかと寄り)になる。影の中心はそこへ合わせる。
 */
const CONTACT_SHADOW = { width: 96, height: 16, alpha: 0.6, y: -9 };
const AMBIENT_SHADOW = { width: 176, height: 38, alpha: 0.28, y: -7 };
const BOOT_TIMEOUT_MS = 8000;
/** 前に人がいて立ち止まったあと、向かい直すまでの間 */
const YIELD_MIN_MS = 600;
const YIELD_MAX_MS = 1500;
/** 立ち止まったとき、この距離以内の住民の方へ向き直ることがある(確率) */
const FACE_NEIGHBOR_RANGE = 420;
const FACE_NEIGHBOR_CHANCE = 0.4;
const NAME_FONT =
  '"Hiragino Kaku Gothic ProN", "Yu Gothic", "Noto Sans JP", sans-serif';

type AgentMode = "idle" | "toFocus" | "focus";

interface Agent {
  id: string;
  name: string;
  container: Phaser.GameObjects.Container;
  sprite: Phaser.GameObjects.Image;
  nameText: Phaser.GameObjects.Text;
  highlight: Phaser.GameObjects.Ellipse;
  selRing: Phaser.GameObjects.Ellipse;
  url: string | null | undefined;
  /** 立ち絵の高さを AVATAR_H に合わせる縮尺(歩き・呼吸の伸び縮みはこれに掛ける) */
  baseScale: number;
  position: Point;
  target: Point | null;
  mode: AgentMode;
  waitUntil: number;
  /** 歩きの揺れの位相 */
  phase: number;
  /** 呼吸の位相 */
  breathPhase: number;
  /** 歩きの揺れの強さ(0〜1)。歩き出し・立ち止まりで滑らかに出し入れする */
  walkBlend: number;
  /** 今の目標へ歩き出してからの時間(加速に使う) */
  walkedMs: number;
  /** 前に人がいて減速して止まろうとしているところ */
  braking: boolean;
  /**
   * 出来事の寄り合いの場所から外へよけているところ。抜け道が参加住民の向こうにしか
   * 無いこともあるので、前に人がいても立ち止まらない
   */
  evacuating: boolean;
  /** 左を向くか(画像の左右反転) */
  facingLeft: boolean;
  /** 向きの見た目(1 = 反転なし 〜 -1 = 反転)。振り向くときに 0 をまたいで裏返す */
  turn: number;
  /** 寄り合いの位置に着いたら向く向き */
  focusFacingLeft: boolean;
  jitter: number;
  arrived: boolean;
}

interface FocusSession {
  agents: Agent[];
  resolve: (arrived: boolean) => void;
  timer: ReturnType<typeof setTimeout>;
}

class RoomStage {
  private scene: Phaser.Scene | null = null;
  private readonly agents = new Map<string, Agent>();
  private readonly textureKeys = new Map<string, string>();
  private readonly textureWaiters = new Map<
    string,
    ((key: string | null) => void)[]
  >();
  private textureSeq = 0;
  private background: Phaser.GameObjects.Image | null = null;
  private backgroundUrl: string | null | undefined = undefined;
  private pending: {
    residents: StageResident[];
    backgroundUrl: string | null;
    areaId: string;
    furniture: StageFurniture[];
  } = { residents: [], backgroundUrl: null, areaId: "living", furniture: [] };
  private readonly furnitureSprites = new Map<
    string,
    {
      group: Phaser.GameObjects.Container;
      image: Phaser.GameObjects.Image;
      url: string;
    }
  >();
  private focus: FocusSession | null = null;
  /** 出来事の再生中に、居合わせない住民が空ける横の範囲 */
  private zone: XRange | null = null;
  private selectedId: string | null = null;
  private involved = new Set<string>();
  private motionEnabled = true;

  private readonly callbacks: RoomStageCallbacks;

  constructor(callbacks: RoomStageCallbacks) {
    this.callbacks = callbacks;
  }

  attach(scene: Phaser.Scene): void {
    this.scene = scene;
    // 背景が読めないときの下地
    scene.add
      .rectangle(0, 0, GAME_W, GAME_H, 0xf3e7cf)
      .setOrigin(0, 0)
      .setDepth(-20);
    scene.textures.createCanvas("hakoniwa-blank", 4, 4);
    this.createShadowTexture(scene);
    this.background = scene.add
      .image(0, 0, "hakoniwa-blank")
      .setOrigin(0, 0)
      .setDepth(-10)
      .setVisible(false);
    this.apply();
  }

  // --- テクスチャ ---

  /** 足元の影の質感(円の放射グラデーション)。楕円に引き伸ばして使う */
  private createShadowTexture(scene: Phaser.Scene): void {
    if (scene.textures.exists(SHADOW_TEXTURE)) return;
    const size = 64;
    const texture = scene.textures.createCanvas(SHADOW_TEXTURE, size, size);
    if (!texture) return;
    const ctx = texture.getContext();
    const gradient = ctx.createRadialGradient(
      size / 2,
      size / 2,
      0,
      size / 2,
      size / 2,
      size / 2,
    );
    gradient.addColorStop(0, "rgba(0,0,0,1)");
    gradient.addColorStop(0.45, "rgba(0,0,0,0.75)");
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    texture.refresh();
  }

  private shadowImage(
    scene: Phaser.Scene,
    shape: { width: number; height: number; alpha: number; y: number },
  ): Phaser.GameObjects.Image {
    return scene.add
      .image(0, shape.y, SHADOW_TEXTURE)
      .setDisplaySize(shape.width, shape.height)
      .setAlpha(shape.alpha);
  }

  private ensureTexture(url: string, callback: (key: string | null) => void) {
    const scene = this.scene;
    if (!scene) {
      callback(null);
      return;
    }
    const existing = this.textureKeys.get(url);
    if (existing && scene.textures.exists(existing)) {
      callback(existing);
      return;
    }
    const waiters = this.textureWaiters.get(url);
    if (waiters) {
      waiters.push(callback);
      return;
    }
    this.textureWaiters.set(url, [callback]);
    const settle = (key: string | null) => {
      const queued = this.textureWaiters.get(url) ?? [];
      this.textureWaiters.delete(url);
      for (const waiter of queued) waiter(key);
    };
    const image = new Image();
    image.onload = () => {
      if (!this.scene) return;
      this.textureSeq += 1;
      const key = `hakoniwa-tex-${this.textureSeq}`;
      this.scene.textures.addImage(key, image);
      this.textureKeys.set(url, key);
      settle(key);
    };
    image.onerror = () => settle(null);
    image.src = url;
  }

  /**
   * どの住民・背景・家具も使っておらず、表示もしていないテクスチャを破棄する。
   * 新しい画像を読み込む間は古いテクスチャを表示し続けるため、表示中のものは残す
   * (破棄すると WebGL の描画で glTexture が null になり、描画が止まる)。
   */
  private collectTextures(): void {
    const scene = this.scene;
    if (!scene) return;
    const used = new Set<string | null | undefined>([this.backgroundUrl]);
    const shown = new Set<string>();
    if (this.background) shown.add(this.background.texture.key);
    for (const agent of this.agents.values()) {
      used.add(agent.url);
      shown.add(agent.sprite.texture.key);
    }
    for (const item of this.furnitureSprites.values()) {
      used.add(item.url);
      shown.add(item.image.texture.key);
    }
    for (const [url, key] of this.textureKeys) {
      if (used.has(url) || shown.has(key) || this.textureWaiters.has(url)) {
        continue;
      }
      this.textureKeys.delete(url);
      if (scene.textures.exists(key)) scene.textures.remove(key);
    }
  }

  private placeholderKey(resident: { id: string; name: string }): string {
    const scene = this.scene as Phaser.Scene;
    const key = `hakoniwa-placeholder-${resident.id}`;
    if (scene.textures.exists(key)) return key;
    const texture = scene.textures.createCanvas(key, 240, 360);
    if (!texture) return key;
    const ctx = texture.getContext();
    ctx.fillStyle = "#efe3cd";
    ctx.fillRect(0, 0, 240, 360);
    ctx.strokeStyle = "#b08968";
    ctx.lineWidth = 6;
    ctx.setLineDash([14, 10]);
    ctx.strokeRect(8, 8, 224, 344);
    ctx.setLineDash([]);
    ctx.fillStyle = "#8c6a4f";
    ctx.font = "bold 130px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(Array.from(resident.name)[0] ?? "?", 120, 188);
    texture.refresh();
    return key;
  }

  private applyTexture(agent: Agent, key: string): void {
    const scene = this.scene as Phaser.Scene;
    agent.sprite.setTexture(key);
    const frame = scene.textures.getFrame(key);
    const height = frame && frame.height > 0 ? frame.height : AVATAR_H;
    agent.baseScale = AVATAR_H / height;
    agent.sprite.setScale(agent.baseScale);
  }

  // --- 住民 ---

  private createAgent(resident: StageResident, index: number, count: number) {
    const scene = this.scene as Phaser.Scene;
    const start = initialPosition(index, count, this.pending.areaId);
    const container = scene.add.container(start.x, start.y);
    const selRing = scene.add
      .ellipse(0, 4, 158, 32)
      .setStrokeStyle(4, 0xd2691e, 0.95)
      .setFillStyle(0xffffff, 0)
      .setVisible(false);
    const highlight = scene.add
      .ellipse(0, 4, 176, 36)
      .setFillStyle(0xb08968, 0.35)
      .setVisible(false);
    // 影は足の裏に重ねる(足と影の間が空くと浮いて見える)
    const ambientShadow = this.shadowImage(scene, AMBIENT_SHADOW);
    const contactShadow = this.shadowImage(scene, CONTACT_SHADOW);
    const sprite = scene.add
      .image(0, 0, this.placeholderKey(resident))
      .setOrigin(0.5, 1);
    const nameText = scene.add
      .text(0, -AVATAR_H - NAME_OFFSET, resident.name, {
        fontFamily: NAME_FONT,
        fontSize: "22px",
        color: "#3d3630",
        backgroundColor: "rgba(255,253,248,0.9)",
        padding: { x: 10, y: 5 },
      })
      .setOrigin(0.5, 1);
    container.add([
      selRing,
      highlight,
      ambientShadow,
      contactShadow,
      sprite,
      nameText,
    ]);
    container.setDepth(start.y);
    const agent: Agent = {
      id: resident.id,
      name: resident.name,
      container,
      sprite,
      nameText,
      highlight,
      selRing,
      url: undefined,
      baseScale: 1,
      position: start,
      target: null,
      mode: "idle",
      // 開いた直後に全員が一斉に歩き出さないよう、歩き出す時刻をばらす
      waitUntil: scene.time.now + 600 + Math.random() * 3400,
      phase: Math.random() * Math.PI * 2,
      breathPhase: Math.random() * Math.PI * 2,
      walkBlend: 0,
      walkedMs: 0,
      braking: false,
      evacuating: false,
      facingLeft: false,
      turn: 1,
      focusFacingLeft: false,
      jitter: yJitter(index),
      arrived: false,
    };
    this.applyTexture(agent, this.placeholderKey(resident));
    sprite.setInteractive({ useHandCursor: true });
    sprite.on("pointerdown", () => this.callbacks.onResidentClick?.(agent.id));
    this.agents.set(resident.id, agent);
    return agent;
  }

  /** 家具を置き直す(表示中の場所の家具だけ)。奥行きは足元の y で住民と前後させる */
  private applyFurniture(): void {
    const scene = this.scene;
    if (!scene) return;
    const desired = new Map(
      this.pending.furniture.map((item) => [item.key, item]),
    );
    for (const [key, sprite] of this.furnitureSprites) {
      if (desired.get(key)?.url === sprite.url) continue;
      sprite.group.destroy();
      this.furnitureSprites.delete(key);
    }
    for (const [key, item] of desired) {
      if (this.furnitureSprites.has(key)) continue;
      const shadow = this.shadowImage(scene, {
        width: item.shadowWidth,
        height: Math.max(12, item.shadowWidth * 0.16),
        alpha: 0.43,
        y: -4,
      });
      const image = scene.add.image(0, 0, "hakoniwa-blank").setOrigin(0.5, 1);
      const group = scene.add
        .container(item.x, item.y, [shadow, image])
        .setDepth(item.y - 1)
        .setVisible(false);
      this.furnitureSprites.set(key, { group, image, url: item.url });
      this.ensureTexture(item.url, (texture) => {
        if (!image.active || !texture || !this.scene) return;
        image.setTexture(texture);
        image.setScale(item.height / image.height);
        group.setVisible(true);
      });
    }
  }

  private apply(): void {
    const scene = this.scene;
    if (!scene) return;
    const { residents, backgroundUrl } = this.pending;
    this.applyFurniture();
    if (backgroundUrl !== this.backgroundUrl) {
      this.backgroundUrl = backgroundUrl;
      if (backgroundUrl) {
        this.ensureTexture(backgroundUrl, (key) => {
          if (this.backgroundUrl !== backgroundUrl || !this.background) return;
          if (key) {
            this.background
              .setTexture(key)
              .setDisplaySize(GAME_W, GAME_H)
              .setVisible(true);
          } else {
            this.background.setVisible(false);
          }
          this.collectTextures();
        });
      } else {
        this.background?.setVisible(false);
      }
    }
    const seen = new Set<string>();
    residents.forEach((resident, index) => {
      seen.add(resident.id);
      const agent =
        this.agents.get(resident.id) ??
        this.createAgent(resident, index, residents.length);
      if (agent.name !== resident.name) {
        agent.name = resident.name;
        agent.nameText.setText(resident.name);
      }
      if (agent.url === resident.imageUrl) return;
      agent.url = resident.imageUrl;
      const url = resident.imageUrl;
      if (!url) {
        this.applyTexture(agent, this.placeholderKey(resident));
        this.collectTextures();
        return;
      }
      this.ensureTexture(url, (key) => {
        if (agent.url !== url || !agent.container.active) return;
        this.applyTexture(agent, key ?? this.placeholderKey(resident));
        this.collectTextures();
      });
    });
    for (const [id, agent] of this.agents) {
      if (seen.has(id)) continue;
      agent.container.destroy();
      this.agents.delete(id);
    }
    this.applyMarkers();
  }

  private applyMarkers(): void {
    for (const agent of this.agents.values()) {
      agent.selRing.setVisible(agent.id === this.selectedId);
      agent.highlight.setVisible(this.involved.has(agent.id));
    }
  }

  update(
    residents: StageResident[],
    backgroundUrl: string | null,
    areaId: string,
    furniture: StageFurniture[] = [],
  ): void {
    if (areaId !== this.pending.areaId) {
      this.releaseFocus();
      for (const agent of this.agents.values()) {
        agent.position = onFloor(agent.position, areaId);
        agent.target = null;
      }
    }
    this.pending = { residents, backgroundUrl, areaId, furniture };
    this.apply();
    this.collectTextures();
  }

  setSelected(id: string | null): void {
    this.selectedId = id;
    this.applyMarkers();
  }

  setInvolved(ids: string[]): void {
    this.involved = new Set(ids);
    this.applyMarkers();
  }

  setMotionEnabled(enabled: boolean): void {
    this.motionEnabled = enabled;
  }

  // --- 寄り合い ---

  private finishFocus(arrived: boolean): void {
    const session = this.focus;
    if (!session) return;
    this.focus = null;
    clearTimeout(session.timer);
    session.resolve(arrived);
  }

  releaseFocus(): void {
    this.finishFocus(false);
    this.zone = null;
    const now = this.scene?.time.now ?? 0;
    for (const agent of this.agents.values()) {
      if (agent.mode === "idle") continue;
      agent.mode = "idle";
      agent.target = null;
      agent.braking = false;
      agent.evacuating = false;
      agent.arrived = false;
      agent.waitUntil = now + 1200 + Math.random() * 2000;
    }
  }

  /** 他の住民の今の位置と、歩いている住民の行き先(目標点選びで避ける点) */
  private occupiedPoints(agent: Agent): Point[] {
    const points: Point[] = [];
    for (const other of this.agents.values()) {
      if (other === agent) continue;
      points.push(other.position);
      if (other.target) points.push(other.target);
    }
    return points;
  }

  private otherPositions(agent: Agent): Point[] {
    const points: Point[] = [];
    for (const other of this.agents.values()) {
      if (other !== agent) points.push(other.position);
    }
    return points;
  }

  /** 横へ十分に動くときだけ、進む方へ向く(奥・手前への移動では向きを変えない) */
  private faceToward(agent: Agent, x: number): void {
    const dx = x - agent.position.x;
    if (Math.abs(dx) >= TURN_MIN_DX) agent.facingLeft = dx < 0;
  }

  private startWalk(agent: Agent, target: Point): void {
    agent.target = target;
    agent.walkedMs = 0;
    agent.braking = false;
    agent.evacuating = false;
    this.faceToward(agent, target.x);
  }

  focusGroup(ids: string[]): Promise<boolean> {
    if (!this.scene) return Promise.resolve(false);
    const group = ids
      .map((id) => this.agents.get(id))
      .filter((agent): agent is Agent => agent !== undefined);
    if (group.length === 0) return Promise.resolve(false);
    this.releaseFocus();
    const targets = focusTargets(
      group.map((agent) => agent.position),
      this.pending.areaId,
    );
    this.zone = focusZone(targets);
    // 居合わせない住民は、集まる場所から外へよける
    const members = new Set(group);
    for (const agent of this.agents.values()) {
      if (members.has(agent) || !this.zone) continue;
      const x = agent.target?.x ?? agent.position.x;
      if (x < this.zone.min || x > this.zone.max) continue;
      const target = pickWanderTarget(
        agent.position,
        this.occupiedPoints(agent),
        agent.jitter,
        this.pending.areaId,
        Math.random,
        this.zone,
      );
      if (this.motionEnabled) {
        this.startWalk(agent, target);
        agent.evacuating = true;
      } else {
        agent.position = target;
        agent.target = null;
      }
    }
    group.forEach((agent, index) => {
      const target = targets[index];
      agent.mode = "toFocus";
      agent.arrived = false;
      agent.focusFacingLeft = target.flip;
      // 歩いている間は進む方を向き、着いてから相手の方へ向き直る
      this.startWalk(agent, { x: target.x, y: target.y });
      if (!this.motionEnabled) {
        // 動きを減らす設定では、歩かずにその場へ移す
        agent.position = { x: target.x, y: target.y };
        agent.facingLeft = target.flip;
      }
    });
    return new Promise((resolve) => {
      const timer = setTimeout(() => this.finishFocus(false), FOCUS_TIMEOUT_MS);
      this.focus = { agents: group, resolve, timer };
    });
  }

  // --- フレーム更新 ---

  /** 目標へ一歩進める。歩き出しは加速し、目標の手前で減速する */
  private walk(agent: Agent, target: Point, delta: number) {
    agent.walkedMs += delta;
    const remaining = Math.hypot(
      target.x - agent.position.x,
      target.y - agent.position.y,
    );
    const speed = WALK_SPEED * walkSpeedFactor(agent.walkedMs, remaining);
    const step = stepToward(agent.position, target, delta, speed);
    agent.position = step.position;
    return step;
  }

  private wanderTick(agent: Agent, time: number, delta: number): void {
    if (!agent.target && time >= agent.waitUntil) {
      this.startWalk(
        agent,
        pickWanderTarget(
          agent.position,
          this.occupiedPoints(agent),
          agent.jitter,
          this.pending.areaId,
          Math.random,
          this.zone,
        ),
      );
    }
    if (!agent.target) return;
    const others = this.otherPositions(agent);
    if (
      !agent.braking &&
      !agent.evacuating &&
      isPathBlocked(agent.position, agent.target, others)
    ) {
      // 前に人がいるときは、少し進んで止まり、間を置いてから別の場所へ向かい直す
      agent.target = brakePoint(agent.position, agent.target);
      agent.braking = true;
    }
    const step = this.walk(agent, agent.target, delta);
    if (!step.arrived) return;
    agent.target = null;
    agent.evacuating = false;
    if (agent.braking) {
      agent.braking = false;
      agent.waitUntil =
        time + YIELD_MIN_MS + Math.random() * (YIELD_MAX_MS - YIELD_MIN_MS);
      return;
    }
    agent.waitUntil =
      time + IDLE_MIN_MS + Math.random() * (IDLE_MAX_MS - IDLE_MIN_MS);
    // 立ち止まったら、近くの住民の方へ向き直ることがある
    const neighbor = nearestWithin(agent.position, others, FACE_NEIGHBOR_RANGE);
    if (neighbor && Math.random() < FACE_NEIGHBOR_CHANCE) {
      this.faceToward(agent, neighbor.x);
    }
  }

  /** 振り向き・歩きの揺れ・呼吸を立ち絵に反映する */
  private animate(agent: Agent, delta: number): void {
    const goal = agent.facingLeft ? -1 : 1;
    if (!this.motionEnabled) {
      agent.turn = goal;
      agent.walkBlend = 0;
      agent.sprite.setFlipX(agent.facingLeft);
      agent.sprite.rotation = 0;
      agent.sprite.setScale(agent.baseScale);
      return;
    }
    // 振り向くときは横幅を縮め、裏返してから元の幅へ戻す(一瞬で反転させない)
    agent.turn = approach(agent.turn, goal, (2 * delta) / TURN_MS);
    if (agent.turn !== 0) agent.sprite.setFlipX(agent.turn < 0);
    // 正弦で縮めて、いちばん細い時間を短くする
    const width = Math.max(
      Math.abs(Math.sin((agent.turn * Math.PI) / 2)),
      TURN_MIN_WIDTH,
    );
    // 歩くときは足元を軸に左右へ揺らし、一歩ごとに縦へわずかに伸ばす
    // (体ごと上下させると足が床から離れて見える)。立っている間は呼吸だけ
    const walking = agent.target !== null;
    agent.walkBlend = approach(
      agent.walkBlend,
      walking ? 1 : 0,
      delta / WALK_BLEND_MS,
    );
    if (agent.walkBlend > 0) agent.phase += delta * WALK_SWAY_SPEED;
    agent.breathPhase =
      (agent.breathPhase + (delta / BREATH_PERIOD_MS) * Math.PI * 2) %
      (Math.PI * 2);
    const stepWave = Math.sin(agent.phase);
    agent.sprite.rotation = stepWave * WALK_SWAY * agent.walkBlend;
    const stretch =
      1 +
      Math.abs(stepWave) * STEP_STRETCH * agent.walkBlend +
      Math.sin(agent.breathPhase) * BREATH_STRETCH * (1 - agent.walkBlend);
    agent.sprite.setScale(agent.baseScale * width, agent.baseScale * stretch);
  }

  tick(time: number, delta: number): void {
    for (const agent of this.agents.values()) {
      if (agent.mode === "idle" && this.motionEnabled) {
        this.wanderTick(agent, time, delta);
      } else if (agent.mode === "toFocus" && agent.target) {
        const step = this.walk(agent, agent.target, delta);
        if (step.arrived) {
          agent.mode = "focus";
          agent.target = null;
          agent.arrived = true;
          agent.facingLeft = agent.focusFacingLeft;
        }
      }
      this.animate(agent, delta);
      const y = agent.position.y;
      agent.container.setPosition(agent.position.x, y);
      // 奥に立つほど小さく描く(名札・影・選択の輪もまとめて縮める)
      agent.container.setScale(depthScale(y));
      agent.container.setDepth(y);
    }
    if (this.focus?.agents.every((agent) => agent.arrived)) {
      this.finishFocus(true);
    }
  }

  getAnchor(id: string): Point | null {
    const agent = this.agents.get(id);
    return agent ? anchorRatio(agent.position) : null;
  }

  dispose(): void {
    this.finishFocus(false);
    this.agents.clear();
    this.furnitureSprites.clear();
    this.textureKeys.clear();
    this.textureWaiters.clear();
    this.scene = null;
  }
}

/**
 * container の中に部屋ステージを起動する。起動できなければ例外で失敗する。
 */
export function createRoomStage(
  container: HTMLElement,
  callbacks: RoomStageCallbacks,
): Promise<RoomStageHandle> {
  const stage = new RoomStage(callbacks);
  return new Promise((resolve, reject) => {
    let settled = false;
    let game: Phaser.Game | null = null;
    const handle: RoomStageHandle = {
      update: (residents, backgroundUrl, areaId, furniture) =>
        stage.update(residents, backgroundUrl, areaId, furniture),
      focusGroup: (ids) => stage.focusGroup(ids),
      releaseFocus: () => stage.releaseFocus(),
      setSelected: (id) => stage.setSelected(id),
      setInvolved: (ids) => stage.setInvolved(ids),
      setMotionEnabled: (enabled) => stage.setMotionEnabled(enabled),
      getAnchor: (id) => stage.getAnchor(id),
      destroy: () => {
        stage.dispose();
        game?.destroy(true);
        game = null;
      },
    };
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      handle.destroy();
      reject(new Error("Phaser did not start in time"));
    }, BOOT_TIMEOUT_MS);

    class HakoniwaRoomScene extends Phaser.Scene {
      constructor() {
        super("hakoniwa-room");
      }

      create() {
        stage.attach(this);
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          resolve(handle);
        }
      }

      update(time: number, delta: number) {
        stage.tick(time, delta);
      }
    }

    try {
      game = new Phaser.Game({
        type: Phaser.AUTO,
        parent: container,
        transparent: true,
        scale: {
          mode: Phaser.Scale.FIT,
          autoCenter: Phaser.Scale.CENTER_BOTH,
          width: GAME_W,
          height: GAME_H,
        },
        scene: [HakoniwaRoomScene],
        banner: false,
        audio: { noAudio: true },
        // window 全体の押下を拾うと、キャンバスの上に重なったダイアログ等のクリックまで
        // 住民のクリックとして扱われる。キャンバス上の操作だけを受け取る
        input: { windowEvents: false },
      });
    } catch (error) {
      settled = true;
      clearTimeout(timeout);
      reject(error);
    }
  });
}
