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
  FLOOR_BOTTOM,
  FLOOR_TOP,
  focusTargets,
  focusZone,
  GAME_H,
  GAME_W,
  initialPosition,
  NAME_OFFSET,
  type Point,
  pickWanderTarget,
  stepToward,
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

export interface RoomStageCallbacks {
  onResidentClick?: (residentId: string) => void;
}

export interface RoomStageHandle {
  update: (residents: StageResident[], backgroundUrl: string | null) => void;
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
const BOOT_TIMEOUT_MS = 8000;
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
  position: Point;
  target: Point | null;
  mode: AgentMode;
  waitUntil: number;
  phase: number;
  jitter: number;
  arrived: boolean;
  bob: number;
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
  } = { residents: [], backgroundUrl: null };
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
    this.background = scene.add
      .image(0, 0, "hakoniwa-blank")
      .setOrigin(0, 0)
      .setDepth(-10)
      .setVisible(false);
    this.apply();
  }

  // --- テクスチャ ---

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

  /** どの住民・背景も使っていないテクスチャを破棄する */
  private collectTextures(): void {
    const scene = this.scene;
    if (!scene) return;
    const used = new Set<string | null | undefined>([this.backgroundUrl]);
    for (const agent of this.agents.values()) used.add(agent.url);
    for (const [url, key] of this.textureKeys) {
      if (used.has(url) || this.textureWaiters.has(url)) continue;
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
    agent.sprite.setScale(AVATAR_H / height);
  }

  // --- 住民 ---

  private createAgent(resident: StageResident, index: number, count: number) {
    const scene = this.scene as Phaser.Scene;
    const start = initialPosition(index, count);
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
    const shadow = scene.add
      .ellipse(0, 4, 118, 22)
      .setFillStyle(0x000000, 0.22);
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
    container.add([selRing, highlight, shadow, sprite, nameText]);
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
      position: start,
      target: null,
      mode: "idle",
      waitUntil: scene.time.now + Math.random() * 2000,
      phase: Math.random() * Math.PI * 2,
      jitter: yJitter(index),
      arrived: false,
      bob: 0,
    };
    this.applyTexture(agent, this.placeholderKey(resident));
    sprite.setInteractive({ useHandCursor: true });
    sprite.on("pointerdown", () => this.callbacks.onResidentClick?.(agent.id));
    this.agents.set(resident.id, agent);
    return agent;
  }

  private apply(): void {
    const scene = this.scene;
    if (!scene) return;
    const { residents, backgroundUrl } = this.pending;
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

  update(residents: StageResident[], backgroundUrl: string | null): void {
    this.pending = { residents, backgroundUrl };
    this.apply();
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
      agent.arrived = false;
      agent.waitUntil = now + 1200 + Math.random() * 2000;
    }
  }

  focusGroup(ids: string[]): Promise<boolean> {
    if (!this.scene) return Promise.resolve(false);
    const group = ids
      .map((id) => this.agents.get(id))
      .filter((agent): agent is Agent => agent !== undefined);
    if (group.length === 0) return Promise.resolve(false);
    this.releaseFocus();
    const targets = focusTargets(group.map((agent) => agent.position));
    this.zone = focusZone(targets);
    // 居合わせない住民は、集まる場所から外へよける
    const members = new Set(group);
    for (const agent of this.agents.values()) {
      if (members.has(agent) || !this.zone) continue;
      const x = agent.target?.x ?? agent.position.x;
      if (x < this.zone.min || x > this.zone.max) continue;
      const others = [...this.agents.values()]
        .filter((other) => other !== agent)
        .map((other) => other.target ?? other.position);
      agent.target = pickWanderTarget(
        others,
        agent.jitter,
        Math.random,
        this.zone,
      );
      if (!this.motionEnabled) {
        agent.position = { ...agent.target };
        agent.target = null;
      }
    }
    group.forEach((agent, index) => {
      const target = targets[index];
      agent.mode = "toFocus";
      agent.arrived = false;
      agent.target = { x: target.x, y: target.y };
      agent.sprite.setFlipX(target.flip);
      if (!this.motionEnabled) {
        // 動きを減らす設定では、歩かずにその場へ移す
        agent.position = { x: target.x, y: target.y };
      }
    });
    return new Promise((resolve) => {
      const timer = setTimeout(() => this.finishFocus(false), FOCUS_TIMEOUT_MS);
      this.focus = { agents: group, resolve, timer };
    });
  }

  // --- フレーム更新 ---

  tick(time: number, delta: number): void {
    for (const agent of this.agents.values()) {
      if (agent.mode === "idle" && this.motionEnabled) {
        if (!agent.target && time >= agent.waitUntil) {
          const others = [...this.agents.values()]
            .filter((other) => other !== agent)
            .map((other) => other.target ?? other.position);
          agent.target = pickWanderTarget(
            others,
            agent.jitter,
            Math.random,
            this.zone,
          );
        }
        if (agent.target) {
          const step = stepToward(agent.position, agent.target, delta);
          agent.position = step.position;
          agent.sprite.setFlipX(step.movingLeft);
          if (step.arrived) {
            agent.target = null;
            agent.waitUntil = time + 2200 + Math.random() * 3800;
          }
        }
      } else if (agent.mode === "toFocus" && agent.target) {
        const step = stepToward(agent.position, agent.target, delta);
        agent.position = step.position;
        if (step.arrived) {
          agent.mode = "focus";
          agent.target = null;
          agent.arrived = true;
        }
      }
      const walking = agent.target !== null && this.motionEnabled;
      if (walking) {
        agent.phase += delta * 0.011;
        agent.bob = Math.sin(agent.phase) * 3.2;
      } else {
        agent.bob = 0;
      }
      agent.sprite.y = agent.bob;
      agent.nameText.y = agent.bob - AVATAR_H - NAME_OFFSET;
      const y = Math.min(Math.max(agent.position.y, FLOOR_TOP), FLOOR_BOTTOM);
      agent.container.setPosition(agent.position.x, y);
      agent.container.setDepth(y);
    }
    if (this.focus?.agents.every((agent) => agent.arrived)) {
      this.finishFocus(true);
    }
  }

  getAnchor(id: string): Point | null {
    const agent = this.agents.get(id);
    return agent ? anchorRatio(agent.position, agent.bob) : null;
  }

  dispose(): void {
    this.finishFocus(false);
    this.agents.clear();
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
      update: (residents, backgroundUrl) =>
        stage.update(residents, backgroundUrl),
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
      });
    } catch (error) {
      settled = true;
      clearTimeout(timeout);
      reject(error);
    }
  });
}
