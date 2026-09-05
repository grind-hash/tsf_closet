import type { TFunction } from "i18next";
import type {
  AdventureInventory,
  AdventureRun,
  AdventureSim,
  AdventureTalkEntry,
  AdventureTurn,
  AdventureVisualCharacter,
} from "../apis/adventure";
import { formatInventoryEvents } from "../components/adventure/AdventureInventoryPanel";
import type { AdventureStageFrame } from "./adventureFrames";

export interface AdventureSceneView {
  latestTurn: AdventureTurn | null;
  /** 本文をストリーム中か(pendingUserInput が立っている間) */
  isStreamingNarrative: boolean;
  /** メッセージ窓に出す本文。ストリーム中はその途中経過、過去閲覧中はその手番 */
  activeNarrative: string;
  activeAction: string | null | undefined;
  activeLocation: string | null | undefined;
  availableChoices: AdventureRun["choices"];
  completedMilestones: Set<string>;
  /** 「現実改変：〜」で宣言され、以降の判定に効いている世界ルール */
  realityRules: string[];
  /** 持ち物システム(全プリセット)。OFF の run は null */
  inventory: AdventureInventory | null;
  inventoryCount: number;
  /** romance の公開シミュ状態。他プリセットでは null */
  sim: AdventureSim | null;
  cast: AdventureVisualCharacter[];
  partnerName: string;
  partnerClothing: string;
  playerDisplayName: string;
  /** トークモード(romance): 行動パネルを会話スレッドに切り替える */
  talkMode: boolean;
  currentTalkEntries: AdventureTalkEntry[];
  lastPartnerTalk: AdventureTalkEntry | null;
  /** 表示中フレームの持ち物の変化(1行)。無ければ null */
  inventoryNote: string | null;
}

interface BuildSceneViewOptions {
  activeRun: AdventureRun;
  selectedFrame: AdventureStageFrame | undefined;
  latestFrame: AdventureStageFrame | undefined;
  isViewingPast: boolean;
  streamingNarrative: string;
  pendingUserInput: string | null;
  actionMode: "act" | "talk";
  t: TFunction;
}

/**
 * プレイ画面の各部(HUD・メッセージ窓・ステージ)が共有する「いま映している場面」の
 * 派生値をまとめて求める。状態は持たず、描画ごとに呼ぶ純関数。
 */
export function buildAdventureSceneView({
  activeRun,
  selectedFrame,
  latestFrame,
  isViewingPast,
  streamingNarrative,
  pendingUserInput,
  actionMode,
  t,
}: BuildSceneViewOptions): AdventureSceneView {
  const latestTurn = activeRun.turns.at(-1) ?? null;
  const isStreamingNarrative = pendingUserInput !== null;
  const activeNarrative = isStreamingNarrative
    ? streamingNarrative
    : isViewingPast
      ? (selectedFrame?.narrative ?? activeRun.opening_narrative)
      : (latestTurn?.narrative ?? activeRun.opening_narrative);
  const activeAction = isStreamingNarrative
    ? pendingUserInput
    : isViewingPast
      ? selectedFrame?.userInput
      : latestTurn?.user_input;
  const activeLocation = isViewingPast
    ? selectedFrame?.location
    : (latestTurn?.location ?? activeRun.visual_state?.location);
  const availableChoices = activeRun.choices.filter(
    (choice) => choice.label.trim().length > 0,
  );
  const completedMilestones = new Set(activeRun.completed_milestones);
  // romance では「付与した属性」として表示する
  const realityRules = activeRun.reality_rules ?? [];
  const inventory = activeRun.inventory_enabled
    ? (activeRun.inventory ?? { items: [], log: [] })
    : null;
  const inventoryCount = inventory
    ? inventory.items.reduce((sum, item) => sum + item.quantity, 0)
    : 0;
  const sim = activeRun.preset === "romance" ? (activeRun.sim ?? null) : null;
  const cast = activeRun.visual_state?.main_characters ?? [];
  // 攻略対象の服装は sim ではなく現在の場面側に載る。名前の部分一致で引く
  // (バックエンドの _romance_partner_visual_entry と同じ突合)
  const partnerName = sim?.partner_name?.trim() ?? "";
  const partnerClothing = partnerName
    ? (cast.find((member) => {
        const name = member.name.trim();
        // 空名エントリは partnerName.includes("") で誤ヒットするため除く
        return (
          name !== "" &&
          (name.includes(partnerName) || partnerName.includes(name))
        );
      })?.clothing ?? "")
    : "";
  // 表示中フレームの持ち物の変化。メッセージ窓のメタ行に1行で出す
  const frameWorldEvents = inventory
    ? ((isViewingPast ? selectedFrame : latestFrame)?.worldEvents ?? [])
    : [];
  const inventoryNote =
    frameWorldEvents.length > 0
      ? formatInventoryEvents(frameWorldEvents, t)
      : null;
  const talkMode = Boolean(sim) && actionMode === "talk";
  const playerDisplayName = sim?.player_name?.trim() || t("adventure.talk.you");
  const currentTalkEntries = (activeRun.talk_log ?? []).filter(
    (entry) => entry.after_turn === activeRun.turn_count,
  );
  const lastPartnerTalk =
    [...(activeRun.talk_log ?? [])]
      .reverse()
      .find((entry) => entry.role === "partner") ?? null;
  return {
    latestTurn,
    isStreamingNarrative,
    activeNarrative,
    activeAction,
    activeLocation,
    availableChoices,
    completedMilestones,
    realityRules,
    inventory,
    inventoryCount,
    sim,
    cast,
    partnerName,
    partnerClothing,
    playerDisplayName,
    talkMode,
    currentTalkEntries,
    lastPartnerTalk,
    inventoryNote,
  };
}
