import type {
  HakoniwaAvatarBatch,
  HakoniwaBusy,
  HakoniwaEventProgress,
  HakoniwaLookProgress,
} from "../../contexts/HakoniwaContext";

/** 上端のバーに出す、いま進めている処理の種類(hakoniwa.activity.* の文言のキー) */
export type HakoniwaActivityKind =
  | "day"
  | "eventWriting"
  | "eventPlanning"
  | "eventPortraits"
  | "eventScene"
  | "transform"
  | "reality"
  | "avatar"
  | "avatarBatch"
  | "look"
  | "memoPlanning"
  | "scene";

export interface HakoniwaActivity {
  kind: HakoniwaActivityKind;
  /** 1人ずつ進める処理の、終わった人数と全体の人数 */
  done?: number;
  total?: number;
  /** 生成している姿(掟の id・"combo"・"memo")。kind が look のときだけ */
  lookTarget?: string;
}

export interface HakoniwaActivityInput {
  busy: HakoniwaBusy;
  lookTarget: string | null;
  lookProgress: HakoniwaLookProgress | null;
  avatarBatch: HakoniwaAvatarBatch | null;
  eventProgress: HakoniwaEventProgress | null;
}

const EVENT_PHASE_KINDS = {
  writing: "eventWriting",
  planning: "eventPlanning",
  portraits: "eventPortraits",
  scene: "eventScene",
} as const;

/**
 * 処理中の状態から、上端のバーに出す表示を決める。
 * テキスト生成や画像生成で待つ処理だけを対象にし、すぐ終わる操作
 * (設定・家具・掟の切り替えなど)と、専用の画面を持つ操作(会話・タッチ)は出さない。
 */
export function currentActivity({
  busy,
  lookTarget,
  lookProgress,
  avatarBatch,
  eventProgress,
}: HakoniwaActivityInput): HakoniwaActivity | null {
  switch (busy) {
    case "day":
      return { kind: "day" };
    case "event": {
      if (!eventProgress) return { kind: "eventWriting" };
      const kind = EVENT_PHASE_KINDS[eventProgress.phase];
      return kind === "eventPortraits"
        ? { kind, done: eventProgress.done, total: eventProgress.total }
        : { kind };
    }
    case "transform":
      return { kind: "transform" };
    case "reality":
      return { kind: "reality" };
    case "avatar":
      return avatarBatch
        ? {
            kind: "avatarBatch",
            done: avatarBatch.done,
            total: avatarBatch.total,
          }
        : { kind: "avatar" };
    case "look":
      if (lookProgress) {
        return {
          kind: "look",
          lookTarget: lookProgress.target,
          done: lookProgress.done,
          total: lookProgress.total,
        };
      }
      // 姿の人数が決まる前: 世界のメモが姿に関わるかを確かめている
      return lookTarget === "memo" ? { kind: "memoPlanning" } : null;
    case "scene":
      return { kind: "scene" };
    default:
      return null;
  }
}
