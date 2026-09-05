import type {
  AdventureBgmKey,
  AdventureInventory,
  AdventureInventoryLogEntry,
  AdventurePartnerPortraitStatus,
  AdventureRun,
  AdventureSim,
  AdventureTurn,
} from "../apis/adventure";
import {
  type AvatarExpressionKey,
  type AvatarGestureKey,
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "../constants/companionAvatar";

// AdventureRun をステージ表示用のフレーム列に変換する純関数群。

export interface AdventureStageFrame {
  key: string;
  turnNumber: number;
  /** ステージ／サムネイル用の代表画像 */
  imageUrl: string;
  /** imageUrl が合成シーンか立ち絵か、対面会話モードの攻略対象立ち絵かを示す */
  kind: "composite" | "portrait" | "partner";
  /** 非合成モードの背景。romance ではこの手番の現在地・時間帯のもの */
  backgroundUrl: string | null;
  /** この手番の立ち絵（白背景の元画像）。無ければ null */
  portraitUrl: string | null;
  /** この手番の立ち絵生成の結果。"failed" のとき再試行導線を出す */
  portraitStatus: string | null;
  /** この手番の合成シーン。非合成モードでは null */
  sceneUrl: string | null;
  userInput: string | null;
  inputKind: AdventureTurn["input_kind"] | null;
  narrative: string;
  location: string | null;
  /** romance のみ。この手番確定時点の公開シミュ状態 */
  sim: AdventureSim | null;
  /** romance のみ。この手番の攻略対象の様子 */
  partnerNote: string | null;
  /** romance 非合成のみ。この手番時点の攻略対象の立ち絵(白背景の元画像) */
  partnerUrl: string | null;
  /** romance のみ。この手番で攻略対象の立ち絵を描いたか、据え置いた理由。旧ターンは null */
  partnerStatus: AdventurePartnerPortraitStatus | null;
  /** 攻略対象の立ち絵がこの手番で描き直されず前の1枚のままか(開幕・合成モードは false) */
  partnerInherited: boolean;
  /** この手番時点のBGMカテゴリ。据え置きターンは直前の値を引き継ぐ */
  bgm: AdventureBgmKey;
  /** この手番のBGM選曲理由。キーと対で引き継ぎ、旧runでは null */
  bgmReason: string | null;
  /** 対面会話モードの 3D モデル向け。攻略対象の表情・身振り(無ければ null) */
  partnerExpression?: AvatarExpressionKey | null;
  partnerGesture?: AvatarGestureKey | null;
  /** 持ち物 ON のみ。この手番確定時点の所持品(開幕・旧ターンは undefined) */
  inventory?: AdventureInventory | null;
  /** 持ち物 ON のみ。この手番で適用した持ち物の変化 */
  worldEvents?: AdventureInventoryLogEntry[];
}

/**
 * 攻略対象の立ち絵がその手番で描き直されず、前の1枚のままかを判定する。
 * status が記録された手番はそれを信じる。SSE 由来の turn は URL に API_BASE が
 * 付かず GET 由来の前手番と一致しないため、URL 比較は status の無い旧ターン専用
 */
export function partnerPortraitInherited(
  turn: AdventureTurn,
  previousPartnerUrl: string | null,
): boolean {
  if (turn.partner_portrait_status) {
    return turn.partner_portrait_status !== "generated";
  }
  return (
    !turn.partner_portrait_url ||
    turn.partner_portrait_url === previousPartnerUrl
  );
}

/** 据え置き理由の i18n キー末尾。未記録(旧ターン)は unknown */
export function partnerPortraitReasonKey(
  status: AdventurePartnerPortraitStatus | null,
): Exclude<AdventurePartnerPortraitStatus, "generated"> | "unknown" {
  return status && status !== "generated" ? status : "unknown";
}

/**
 * フレームが描いている日付と時間帯。サーバの scene_day/scene_slot が唯一の情報源。
 * sim.day/slot は「次に行動する枠」で常に半日先を指すため使わない。
 */
export function frameDaySlot(
  frame: AdventureStageFrame | undefined,
): { day: number; slot: "day" | "night" } | null {
  const day = frame?.sim?.scene_day;
  const slot = frame?.sim?.scene_slot;
  if (!frame || frame.turnNumber <= 0) return null;
  if (typeof day !== "number" || (slot !== "day" && slot !== "night"))
    return null;
  return { day, slot };
}

/** AdventureRun からステージとサムネイルに使うフレーム列を組み立てる。 */
export function buildStageFrames(
  activeRun: AdventureRun | null,
): AdventureStageFrame[] {
  if (!activeRun) return [];
  const list: AdventureStageFrame[] = [];
  const runBackground =
    activeRun.background_image_url ?? activeRun.current_image_url ?? null;
  if (activeRun.preset === "romance" && activeRun.companion_mode) {
    // 対面会話モード: 代表画像は攻略対象の立ち絵。生成の無い手番も
    // フレームにし、立ち絵と背景は直前の1枚を引き継ぐ。
    // 背景は生成済みの1枚だけを使い、無ければ null(無地のステージ)にする。
    // current_image_url は主人公の開始画像に落ちうるため背景へ流用しない
    let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
    let lastBackgroundUrl: string | null =
      activeRun.background_image_url ?? null;
    let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
    let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
    list.push({
      key: "opening",
      turnNumber: 0,
      imageUrl:
        lastPartnerUrl ?? lastBackgroundUrl ?? activeRun.opening_image_url,
      kind: "partner",
      backgroundUrl: lastBackgroundUrl,
      portraitUrl: null,
      portraitStatus: null,
      sceneUrl: null,
      userInput: null,
      inputKind: null,
      narrative: activeRun.opening_narrative,
      location: null,
      sim: activeRun.opening_sim ?? null,
      partnerNote: null,
      partnerUrl: lastPartnerUrl,
      partnerStatus: null,
      partnerInherited: false,
      bgm: lastBgm,
      bgmReason: lastBgmReason,
    });
    for (const turn of activeRun.turns) {
      if (turn.bgm) {
        lastBgm = turn.bgm;
        lastBgmReason = turn.bgm_reason ?? null;
      }
      // 引き継ぎ判定は lastPartnerUrl を進める前に行う
      const partnerInherited = partnerPortraitInherited(turn, lastPartnerUrl);
      lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
      lastBackgroundUrl = turn.background_image_url ?? lastBackgroundUrl;
      list.push({
        key: turn.id,
        turnNumber: turn.turn_number,
        imageUrl:
          lastPartnerUrl ?? lastBackgroundUrl ?? activeRun.current_image_url,
        kind: "partner",
        backgroundUrl: lastBackgroundUrl,
        portraitUrl: null,
        portraitStatus: null,
        sceneUrl: null,
        userInput: turn.user_input,
        inputKind: turn.input_kind,
        narrative: turn.narrative,
        inventory: turn.inventory ?? null,
        worldEvents: turn.world_events_applied ?? [],
        location: turn.location,
        sim: turn.sim ?? null,
        partnerNote: turn.partner_note ?? null,
        partnerUrl: lastPartnerUrl,
        partnerStatus: turn.partner_portrait_status ?? null,
        partnerInherited,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
        partnerExpression: normalizeAvatarExpression(turn.partner_expression),
        partnerGesture: normalizeAvatarGesture(turn.partner_gesture),
      });
    }
  } else if (activeRun.enable_composite_scene) {
    // 合成モードでは攻略対象の立ち絵をターンごとに再生成しないが、
    // ライトボックスの攻略対象タブ用に直近の1枚(最低でも開幕分)を引き継ぐ
    let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
    let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
    let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
    if (activeRun.opening_image_url) {
      list.push({
        key: "opening",
        turnNumber: 0,
        imageUrl: activeRun.opening_image_url,
        kind: "composite",
        backgroundUrl: null,
        portraitUrl: activeRun.opening_portrait_url ?? null,
        portraitStatus: null,
        sceneUrl: activeRun.opening_image_url,
        userInput: null,
        inputKind: null,
        narrative: activeRun.opening_narrative,
        location: null,
        sim: activeRun.opening_sim ?? null,
        partnerNote: null,
        partnerUrl: lastPartnerUrl,
        partnerStatus: null,
        partnerInherited: false,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
      });
    }
    for (const turn of activeRun.turns) {
      // 画像の無いターンもBGMは進むため、continue より前に引き継ぐ。
      // 理由はキー更新時だけ取り込み、キーとの食い違いを作らない
      if (turn.bgm) {
        lastBgm = turn.bgm;
        lastBgmReason = turn.bgm_reason ?? null;
      }
      if (!turn.image_url) continue;
      lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
      list.push({
        key: turn.id,
        turnNumber: turn.turn_number,
        imageUrl: turn.image_url,
        kind: "composite",
        backgroundUrl: null,
        portraitUrl: turn.portrait_image_url,
        portraitStatus: turn.portrait_status,
        sceneUrl: turn.image_url,
        userInput: turn.user_input,
        inputKind: turn.input_kind,
        narrative: turn.narrative,
        inventory: turn.inventory ?? null,
        worldEvents: turn.world_events_applied ?? [],
        location: turn.location,
        sim: turn.sim ?? null,
        partnerNote: turn.partner_note ?? null,
        partnerUrl: lastPartnerUrl,
        partnerStatus: turn.partner_portrait_status ?? null,
        // 合成モードでは立ち絵をステージに出さないため案内も出さない
        partnerInherited: false,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
      });
    }
  } else {
    // 攻略対象の立ち絵は生成失敗ターンで欠けうるため、直前の1枚を引き継ぐ
    let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
    let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
    let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
    if (activeRun.opening_portrait_url) {
      list.push({
        key: "opening",
        turnNumber: 0,
        imageUrl: activeRun.opening_portrait_url,
        kind: "portrait",
        backgroundUrl: runBackground,
        portraitUrl: activeRun.opening_portrait_url,
        portraitStatus: null,
        sceneUrl: null,
        userInput: null,
        inputKind: null,
        narrative: activeRun.opening_narrative,
        location: null,
        sim: activeRun.opening_sim ?? null,
        partnerNote: null,
        partnerUrl: lastPartnerUrl,
        partnerStatus: null,
        partnerInherited: false,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
      });
    }
    for (const turn of activeRun.turns) {
      // 画像の無いターンもBGMは進むため、continue より前に引き継ぐ。
      // 理由はキー更新時だけ取り込み、キーとの食い違いを作らない
      if (turn.bgm) {
        lastBgm = turn.bgm;
        lastBgmReason = turn.bgm_reason ?? null;
      }
      if (!turn.portrait_image_url) continue;
      // 「前の1枚」は前フレーム(立ち絵のある手番)のもの
      const partnerInherited = partnerPortraitInherited(turn, lastPartnerUrl);
      lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
      list.push({
        key: turn.id,
        turnNumber: turn.turn_number,
        imageUrl: turn.portrait_image_url,
        kind: "portrait",
        // romance は現在地・時間帯ごとに背景が変わるため、その手番の1枚を使う
        backgroundUrl: turn.background_image_url ?? runBackground,
        portraitUrl: turn.portrait_image_url,
        portraitStatus: turn.portrait_status,
        sceneUrl: null,
        userInput: turn.user_input,
        inputKind: turn.input_kind,
        narrative: turn.narrative,
        inventory: turn.inventory ?? null,
        worldEvents: turn.world_events_applied ?? [],
        location: turn.location,
        sim: turn.sim ?? null,
        partnerNote: turn.partner_note ?? null,
        partnerUrl: lastPartnerUrl,
        partnerStatus: turn.partner_portrait_status ?? null,
        partnerInherited,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
      });
    }
  }
  return list;
}
