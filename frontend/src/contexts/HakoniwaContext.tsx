/**
 * HakoniwaContext - AI箱庭モードの状態(世界の一覧・開いている世界・再生待ちの出来事)。
 *
 * API 呼び出しと状態更新はここのアクションで完結させ、画面は useHakoniwa() から読む。
 * 画像を生成する操作は、V5 の利用上限を使い切っているとき(Anlas を消費する)に確認を挟む。
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { fetchAnlasBalance } from "../apis/anlas";
import {
  addHakoniwaCharacterResident,
  addHakoniwaCustomRule,
  addHakoniwaResident,
  advanceHakoniwaDay,
  alterHakoniwaReality,
  applyHakoniwaEventLook,
  chatHakoniwaResident,
  clearHakoniwaTransform,
  continueHakoniwaEvent,
  createHakoniwaDirectedEvent,
  createHakoniwaWorld,
  deleteHakoniwaCustomRule,
  deleteHakoniwaWorld,
  fetchHakoniwaCatalog,
  fetchHakoniwaChat,
  fetchHakoniwaWorld,
  fetchHakoniwaWorlds,
  generateHakoniwaAvatar,
  generateHakoniwaComboLook,
  generateHakoniwaMemoLook,
  generateHakoniwaRandomResidents,
  generateHakoniwaRuleLook,
  generateHakoniwaSceneImage,
  greetHakoniwaResident,
  type HakoniwaCatalog,
  type HakoniwaCharacterEntry,
  type HakoniwaChatEntry,
  type HakoniwaCustomRuleInput,
  type HakoniwaDirectedEventInput,
  type HakoniwaEvent,
  type HakoniwaInterventionChoice,
  type HakoniwaRandomResident,
  type HakoniwaResidentChange,
  type HakoniwaResidentInput,
  type HakoniwaResidentTagsInput,
  type HakoniwaRuleLookTagsInput,
  type HakoniwaRuleReaction,
  type HakoniwaTheme,
  type HakoniwaTouchPart,
  type HakoniwaWorld,
  type HakoniwaWorldSummary,
  makeHakoniwaResidentTags,
  makeHakoniwaRuleLookTags,
  placeHakoniwaFurniture,
  planHakoniwaEventLooks,
  planHakoniwaMemoLook,
  reapplyHakoniwaTransform,
  removeHakoniwaReality,
  removeHakoniwaResident,
  setHakoniwaFavorite,
  setHakoniwaIntervention,
  toggleHakoniwaRule,
  touchHakoniwaResident,
  transformHakoniwaResident,
  updateHakoniwaCustomRule,
  updateHakoniwaResident,
  updateHakoniwaSettings,
} from "../apis/hakoniwa";
import { reactionScenes } from "../components/hakoniwa/reactionScenes";
import {
  isV5ImageModel,
  V5_USAGE_WARN_SUPPRESSED_KEY,
} from "../constants/novelaiImageModels";
import { ApiError } from "../utils/http";
import { readStorageFlag, writeStorageFlag } from "../utils/storage";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

/** 処理中の操作。ボタンの無効化とスピナーの表示に使う */
export type HakoniwaBusy =
  | "load"
  | "create"
  | "delete"
  | "day"
  | "rule"
  | "resident"
  | "transform"
  | "reality"
  | "event"
  | "avatar"
  | "settings"
  | "furniture"
  | "scene"
  | "look"
  | "touch"
  | "chat"
  | "random"
  | null;

/** タグを作った結果。失敗したら error に画面に出す文言が入る */
export type HakoniwaTagsOutcome =
  | { tags: string; error: null }
  | { tags: null; error: string };

/** 世界を作るときの入力 */
export interface HakoniwaCreateInput {
  name: string;
  presetIds: string[];
  characters: HakoniwaCharacterEntry[];
  dissonanceEnabled: boolean;
  /** おまかせの住民(作成画面で組んだ定義) */
  customResidents: HakoniwaRandomResident[];
  /** 実験テーマ(テーマ無しは null) */
  theme: HakoniwaTheme | null;
}

/** 立ち絵の無い住民をまとめて生成している進み具合 */
export interface HakoniwaAvatarBatch {
  done: number;
  total: number;
}

/** 掟の姿・複合の姿・メモの姿を1人ずつ生成している進み具合 */
export interface HakoniwaLookProgress {
  /** 掟の id か "combo" */
  target: string;
  done: number;
  total: number;
}

/**
 * 出来事を起こしている間の段階。文章(writing) → 姿が変わったかの確認(planning) →
 * 立ち絵(portraits。done / total は終わった人数と変わる人数) → 場面の絵(scene)
 */
export interface HakoniwaEventProgress {
  phase: "writing" | "planning" | "portraits" | "scene";
  done: number;
  total: number;
}

/** 右パネルのタブ */
export type HakoniwaPanelTab =
  | "chronicle"
  | "residents"
  | "rules"
  | "furniture"
  | "settings";

/** 画面に訳を持つエラーコード(それ以外はバックエンドの文言を出す) */
export const HAKONIWA_ERROR_CODES = [
  "world_not_found",
  "resident_not_found",
  "too_few_residents",
  "too_many_residents",
  "too_many_rules",
  "too_many_custom_rules",
  "duplicate_resident",
  "gender_required",
  "image_not_found",
  "image_generation_failed",
  "tag_conversion_failed",
  "empty_name",
  "invalid_image_model",
  "event_not_found",
  "no_participants",
  "area_not_found",
  "invalid_slot",
  "furniture_not_found",
  "tags_failed",
  "tags_required",
  "look_source_empty",
  "rule_has_no_look",
  "no_combo",
  "invalid_rule_appearance",
  "invalid_world_memo",
  "invalid_player_name",
  "invalid_intervention",
  "invalid_touch_part",
  "empty_message",
  "invalid_message",
  "invalid_theme",
  "invalid_count",
  "invalid_tags",
  "too_many_tags",
  "tags_gender_mismatch",
  "invalid_event_text",
  "invalid_event_scope",
  "event_partners_required",
  "event_too_many_partners",
  "event_room_empty",
  "event_generation_failed",
  "invalid_location",
  "event_not_today",
  "event_cast_gone",
  "event_look_failed",
  "event_look_not_planned",
  "invalid_reality_text",
  "too_many_realities",
  "reality_not_found",
  "memo_look_failed",
  "no_memo_look",
] as const;
type HakoniwaErrorCode = (typeof HAKONIWA_ERROR_CODES)[number];

function isKnownErrorCode(code: string): code is HakoniwaErrorCode {
  return (HAKONIWA_ERROR_CODES as readonly string[]).includes(code);
}

export interface HakoniwaTouchReaction {
  residentId: string;
  part: HakoniwaTouchPart;
  text: string;
  /** 同じ部位に続けて触れたときも出し直すための番号 */
  key: number;
}

export interface HakoniwaGreetingBubble {
  residentId: string;
  text: string;
  /** 同じ住民に続けて話しかけたときも吹き出しを出し直すための番号 */
  key: number;
}

interface HakoniwaContextValue {
  catalog: HakoniwaCatalog | null;
  worlds: HakoniwaWorldSummary[];
  world: HakoniwaWorld | null;
  busy: HakoniwaBusy;
  /** 一言を待っている住民 */
  greetingResidentId: string | null;
  greeting: HakoniwaGreetingBubble | null;
  /** 部屋で再生を待つ出来事(1日進める・変身の結果) */
  playbackQueue: HakoniwaEvent[];
  /** 選んでいる住民(部屋の足元の輪と、住民タブの詳細) */
  selectedResidentId: string | null;
  selectResident: (residentId: string | null) => void;
  panelTab: HakoniwaPanelTab;
  setPanelTab: (tab: HakoniwaPanelTab) => void;
  error: string | null;
  clearError: () => void;
  /** V5 の利用上限を使い切った状態で画像を生成する前の確認 */
  usageConfirmOpen: boolean;
  confirmUsage: (doNotShowAgain: boolean) => void;
  cancelUsage: () => void;
  loadCatalog: () => Promise<void>;
  loadWorlds: () => Promise<void>;
  openWorld: (worldId: string) => Promise<HakoniwaWorld | null>;
  closeWorld: () => void;
  createWorld: (input: HakoniwaCreateInput) => Promise<HakoniwaWorld | null>;
  /** おまかせの住民を組む。excludeNames と名前を重ねない。失敗したら null */
  randomResidents: (
    count: number,
    excludeNames: string[],
  ) => Promise<HakoniwaRandomResident[] | null>;
  /** 実験テーマを変える(null でテーマ無し) */
  setExperimentTheme: (theme: HakoniwaTheme | null) => Promise<boolean>;
  /** 立ち絵の無い住民の通常の姿を、1人ずつ順に生成する */
  generateMissingAvatars: () => void;
  avatarBatch: HakoniwaAvatarBatch | null;
  deleteWorld: (worldId: string) => Promise<void>;
  advanceDay: () => Promise<void>;
  toggleRule: (cardId: string, active: boolean) => Promise<void>;
  saveCustomRule: (
    rule: HakoniwaCustomRuleInput,
    ruleId?: string,
  ) => Promise<boolean>;
  /**
   * 掟の姿(ruleId)・複合の姿("combo")・メモの姿("memo")を住民の人数分、1人ずつ生成する。
   * residentIds を渡すと、その住民の姿だけを描き直す
   */
  generateLook: (
    target: string,
    regenerate: boolean,
    residentIds?: string[],
  ) => void;
  /** 世界のメモが姿に関わるかを確かめ直し、関わるならまだの住民の姿を生成する */
  applyMemoLook: (worldId: string) => Promise<void>;
  /** 生成中の掟の姿("combo" は複合の姿) */
  lookTarget: string | null;
  /** 生成中の姿の進み具合(1人ずつ呼ぶので、終わった人数) */
  lookProgress: HakoniwaLookProgress | null;
  deleteCustomRule: (ruleId: string) => Promise<void>;
  saveResident: (
    input: HakoniwaResidentInput,
    residentId?: string,
  ) => Promise<boolean>;
  /** 掟の見た目のタグを作る(保存はしない。フォームの欄に入れる) */
  makeRuleLookTags: (
    input: HakoniwaRuleLookTagsInput,
  ) => Promise<HakoniwaTagsOutcome>;
  /** 住民の姿のタグを作る(保存はしない。フォームの欄に入れる) */
  makeResidentTags: (
    input: HakoniwaResidentTagsInput,
  ) => Promise<HakoniwaTagsOutcome>;
  addCharacterResident: (entry: HakoniwaCharacterEntry) => Promise<boolean>;
  removeResident: (residentId: string) => Promise<void>;
  greet: (residentId: string) => Promise<void>;
  dismissGreeting: () => void;
  transform: (residentId: string, instruction: string) => void;
  /** 住民の改変(その住民の常識を書き換える)。changeLook なら姿も生成する */
  alterReality: (
    residentId: string,
    instruction: string,
    changeLook: boolean,
  ) => void;
  removeReality: (residentId: string, realityId: string) => Promise<void>;
  /**
   * 書き手の指示で出来事を起こし、できた場面を ADV で開く。
   * changeLook なら、出来事の結果として姿が変わった住民の立ち絵も生成し、
   * 全部できてから開く(立ち絵の生成に失敗しても場面は開き、エラーを出す)
   */
  directEvent: (
    residentId: string,
    input: HakoniwaDirectedEventInput,
    changeLook: boolean,
  ) => void;
  /** 出来事を起こしている間の段階(上端の進み具合の表示に使う) */
  eventProgress: HakoniwaEventProgress | null;
  /**
   * 今日の出来事の続きを指示して起こし、できた場面を ADV で開く
   * (参加者と場所は元の場面のまま)。
   * withSceneImage なら続きの場面の絵も生成し、絵ができてから開く
   * (絵の生成に失敗しても場面は開き、エラーを出す)
   */
  continueEvent: (
    eventId: string,
    instruction: string,
    withSceneImage: boolean,
  ) => void;
  clearTransform: (residentId: string) => Promise<void>;
  reapplyTransform: (residentId: string, image: string) => Promise<void>;
  generateAvatar: (residentId: string, variant: "base" | "dress") => void;
  setFavorite: (eventId: string, favorite: boolean) => Promise<void>;
  setImageModel: (imageModel: string) => Promise<void>;
  /** 世界の違和感(住民が書き換えに気づいていく)を使うか */
  setDissonanceEnabled: (enabled: boolean) => Promise<void>;
  /** この世界のチャットと日次の出来事でWeb検索を使うか */
  setWebSearchEnabled: (enabled: boolean) => Promise<void>;
  /** 世界のメモ(全生成に最優先の指示として載せる) */
  setWorldMemo: (memo: string) => Promise<boolean>;
  /** 住民がプレイヤーを呼ぶときの名前(空なら名前で呼ばない) */
  setPlayerName: (name: string) => Promise<boolean>;
  /** 次の「1日進める」で効かせる介入 */
  setIntervention: (choice: HakoniwaInterventionChoice) => Promise<void>;
  /** 立ち絵に触れたときの住民の一言(拡大表示に出す) */
  touchReaction: HakoniwaTouchReaction | null;
  touchResident: (residentId: string, part: HakoniwaTouchPart) => Promise<void>;
  clearTouchReaction: () => void;
  /** 会話している住民と、その会話の履歴 */
  chatResidentId: string | null;
  chatHistory: HakoniwaChatEntry[];
  openChat: (residentId: string) => void;
  /** 会話を閉じる(会話からの変身の出来事は、閉じたあと部屋で再生する) */
  closeChat: () => void;
  /** 送れたら true(画像の確認待ちも含む) */
  sendChat: (message: string) => Promise<boolean>;
  /** 再生を終えた出来事を待ち行列から外す */
  finishPlayback: () => void;
  /** 年代記の出来事を部屋でもう一度再生する */
  replayEvent: (event: HakoniwaEvent) => void;
  /** 再生を待つ出来事をすべて飛ばす */
  clearPlayback: () => void;
  /** 部屋に表示している場所(エリア id) */
  viewAreaId: string;
  setViewAreaId: (areaId: string) => void;
  placeFurniture: (
    areaId: string,
    slot: number,
    furnitureId: string | null,
  ) => Promise<void>;
  /** 出来事の場面絵を生成する(V5 の利用上限を使い切っていれば確認を出す) */
  generateSceneImage: (eventId: string) => void;
  /** 1日のまとめのカードを出しているか(再生が終わったら出す) */
  digestVisible: boolean;
  showDigest: () => void;
  hideDigest: () => void;
  /** ADV で見ている出来事 */
  advEventId: string | null;
  openAdv: (eventId: string) => void;
  closeAdv: () => void;
}

const HakoniwaContext = createContext<HakoniwaContextValue | null>(null);

export function HakoniwaProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { state: settingsState, addTotalCost, setAnlasBalance } = useSettings();
  const { showAchievementNotification, showNotification } = useNotification();

  /** 応答で新しく達成した観察記録(実績)を知らせる */
  const announceAchievements = useCallback(
    (next: HakoniwaWorld) => {
      for (const item of next.new_achievements ?? []) {
        showAchievementNotification({
          id: item.achievement_id,
          name: item.name,
          description: item.description,
          icon: item.icon,
          category: item.category,
          condition_type: "",
          condition_target: "",
          condition_value: 0,
          is_hidden: false,
        });
      }
    },
    [showAchievementNotification],
  );
  const [catalog, setCatalog] = useState<HakoniwaCatalog | null>(null);
  const [worlds, setWorlds] = useState<HakoniwaWorldSummary[]>([]);
  const [world, setWorld] = useState<HakoniwaWorld | null>(null);
  const [busy, setBusy] = useState<HakoniwaBusy>(null);
  const [lookTarget, setLookTarget] = useState<string | null>(null);
  const [lookProgress, setLookProgress] = useState<HakoniwaLookProgress | null>(
    null,
  );
  const [eventProgress, setEventProgress] =
    useState<HakoniwaEventProgress | null>(null);
  const [touchReaction, setTouchReaction] =
    useState<HakoniwaTouchReaction | null>(null);
  const [chatResidentId, setChatResidentId] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<HakoniwaChatEntry[]>([]);
  const [chatEvents, setChatEvents] = useState<HakoniwaEvent[]>([]);
  const [greetingResidentId, setGreetingResidentId] = useState<string | null>(
    null,
  );
  const [greeting, setGreeting] = useState<HakoniwaGreetingBubble | null>(null);
  const [playbackQueue, setPlaybackQueue] = useState<HakoniwaEvent[]>([]);
  const [selectedResidentId, setSelectedResidentId] = useState<string | null>(
    null,
  );
  const [panelTab, setPanelTab] = useState<HakoniwaPanelTab>("chronicle");
  const [viewAreaId, setViewAreaId] = useState("living");
  const [digestPending, setDigestPending] = useState(false);
  const [digestVisible, setDigestVisible] = useState(false);
  const [advEventId, setAdvEventId] = useState<string | null>(null);
  // ADV を閉じたあとに部屋で再生する出来事(指示した出来事に続く対面など)
  const [advFollowUps, setAdvFollowUps] = useState<HakoniwaEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingUsageTask, setPendingUsageTask] = useState<(() => void) | null>(
    null,
  );
  const greetingKey = useRef(0);
  const language = settingsState.language;
  const worldId = world?.id ?? null;
  // 1人ずつ続ける生成の途中で世界を切り替えたら止めるための、いま開いている世界
  const currentWorldIdRef = useRef<string | null>(worldId);
  useEffect(() => {
    currentWorldIdRef.current = worldId;
  }, [worldId]);

  const errorText = useCallback(
    (caught: unknown): string => {
      if (caught instanceof ApiError && caught.code) {
        const code = caught.code;
        if (isKnownErrorCode(code)) return t(`hakoniwa.errors.${code}`);
      }
      return caught instanceof Error ? caught.message : String(caught);
    },
    [t],
  );

  const recordCost = useCallback(
    (cost: number | null | undefined) => {
      if (cost) addTotalCost(cost);
    },
    [addTotalCost],
  );

  /** 操作を1つずつ実行し、失敗はメッセージにして null を返す */
  const run = useCallback(
    async <T,>(
      kind: HakoniwaBusy,
      task: () => Promise<T>,
    ): Promise<T | null> => {
      setBusy(kind);
      setError(null);
      try {
        return await task();
      } catch (caught) {
        setError(errorText(caught));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [errorText],
  );

  const applyWorld = useCallback(
    (next: HakoniwaWorld) => {
      announceAchievements(next);
      setWorld(next);
      setWorlds((current) =>
        current.map((item) =>
          item.id === next.id
            ? {
                ...item,
                name: next.name,
                day: next.day,
                resident_count: next.residents.length,
                event_count: next.events.length,
                updated_at: next.updated_at,
              }
            : item,
        ),
      );
    },
    [announceAchievements],
  );

  const loadCatalog = useCallback(async () => {
    const loaded = await run("load", () => fetchHakoniwaCatalog(language));
    if (loaded) setCatalog(loaded);
  }, [language, run]);

  const loadWorlds = useCallback(async () => {
    const loaded = await run("load", () => fetchHakoniwaWorlds(language));
    if (loaded) setWorlds(loaded);
  }, [language, run]);

  const openWorld = useCallback(
    (id: string) =>
      run("load", async () => {
        const loaded = await fetchHakoniwaWorld(id, language);
        announceAchievements(loaded);
        setWorld(loaded);
        return loaded;
      }),
    [announceAchievements, language, run],
  );

  // 言語を切り替えたら、プリセット住民の名前などを読み直す
  const loadedLanguage = useRef(language);
  useEffect(() => {
    if (loadedLanguage.current === language) return;
    loadedLanguage.current = language;
    if (worldId) {
      void fetchHakoniwaWorld(worldId, language)
        .then(setWorld)
        .catch(() => {});
    }
    void fetchHakoniwaCatalog(language)
      .then(setCatalog)
      .catch(() => {});
  }, [language, worldId]);

  const closeWorld = useCallback(() => {
    setWorld(null);
    setPlaybackQueue([]);
    setGreeting(null);
    setSelectedResidentId(null);
    setViewAreaId("living");
    setDigestPending(false);
    setDigestVisible(false);
    setAdvEventId(null);
    setAdvFollowUps([]);
    setTouchReaction(null);
    setChatResidentId(null);
    setChatHistory([]);
    setChatEvents([]);
  }, []);

  const createWorld = useCallback(
    (input: HakoniwaCreateInput) =>
      run("create", async () => {
        const created = await createHakoniwaWorld({
          name: input.name,
          preset_ids: input.presetIds,
          characters: input.characters,
          language,
          dissonance_enabled: input.dissonanceEnabled,
          custom_residents: input.customResidents,
          experiment_theme: input.theme,
        });
        announceAchievements(created);
        setWorld(created);
        setWorlds((current) => [
          {
            id: created.id,
            name: created.name,
            day: created.day,
            resident_count: created.residents.length,
            event_count: 0,
            created_at: created.created_at,
            updated_at: created.updated_at,
            residents: created.residents.map((resident) => ({
              id: resident.id,
              name: resident.name,
              avatar_url: resident.display_avatar_url,
            })),
          },
          ...current,
        ]);
        return created;
      }),
    [announceAchievements, language, run],
  );

  const deleteWorld = useCallback(
    async (id: string) => {
      await run("delete", async () => {
        await deleteHakoniwaWorld(id);
        setWorlds((current) => current.filter((item) => item.id !== id));
        setWorld((current) => (current?.id === id ? null : current));
      });
    },
    [run],
  );

  const advanceDay = useCallback(async () => {
    if (!worldId) return;
    const result = await run("day", () =>
      advanceHakoniwaDay(worldId, language),
    );
    if (!result) return;
    applyWorld(result.world);
    recordCost(result.cost_usd);
    setGreeting(null);
    setDigestVisible(false);
    setDigestPending(Boolean(result.digest));
    setPlaybackQueue((current) => [...current, ...result.new_events]);
  }, [applyWorld, language, recordCost, run, worldId]);

  // その日の出来事を見終わったら、まとめのカードを出す
  useEffect(() => {
    if (digestPending && playbackQueue.length === 0) {
      setDigestPending(false);
      setDigestVisible(true);
    }
  }, [digestPending, playbackQueue.length]);

  const showDigest = useCallback(() => setDigestVisible(true), []);
  const hideDigest = useCallback(() => setDigestVisible(false), []);
  const openAdv = useCallback((eventId: string) => setAdvEventId(eventId), []);
  const closeAdv = useCallback(() => {
    setAdvEventId(null);
    if (advFollowUps.length === 0) return;
    setPlaybackQueue((current) => [...current, ...advFollowUps]);
    setAdvFollowUps([]);
  }, [advFollowUps]);

  const placeFurniture = useCallback(
    async (areaId: string, slot: number, furnitureId: string | null) => {
      if (!worldId) return;
      const updated = await run("furniture", () =>
        placeHakoniwaFurniture(worldId, areaId, slot, furnitureId, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const reactionSeq = useRef(0);
  /**
   * 掟の切り替え直後の反応を、再生の列に入れられる一時の場面にする(年代記には無い)。
   * 話し手が別々の場所にいるときは場所ごとに場面を分け、見ている場所の場面を最後にする
   * (同じ場面に入れると、よその場所の住民が再生の間だけ部屋に現れてしまう)。
   */
  const reactionEvents = useCallback(
    (
      reaction: HakoniwaRuleReaction,
      current: HakoniwaWorld,
      viewArea: string,
    ): HakoniwaEvent[] => {
      if (reaction.lines.length === 0) return [];
      reactionSeq.current += 1;
      const seq = reactionSeq.current;
      const rule =
        current.rule_cards.find((card) => card.id === reaction.card_id)?.name ??
        reaction.card_id;
      const residentAreas = new Map(
        current.residents.map((resident) => [
          resident.id,
          resident.current_area,
        ]),
      );
      const scenes = reactionScenes(
        reaction.lines,
        residentAreas,
        viewArea,
        reaction.area ?? viewArea,
      );
      return scenes.map((scene, index) => ({
        id: `reaction-${seq}-${index}`,
        day: current.day,
        title: t("hakoniwa.ruleReaction.title", { rule }),
        narration: t(
          reaction.active
            ? "hakoniwa.ruleReaction.started"
            : "hakoniwa.ruleReaction.ended",
          { rule },
        ),
        lines: scene.lines.map((line) => ({
          speaker: line.resident_id,
          text: line.text,
        })),
        participants: [...new Set(scene.lines.map((line) => line.resident_id))],
        mood_delta: {},
        affinity_delta: 0,
        source: "template",
        kind: "reaction",
        favorite: false,
        area: scene.area,
      }));
    },
    [t],
  );

  const toggleRule = useCallback(
    async (cardId: string, active: boolean) => {
      if (!worldId) return;
      const result = await run("rule", () =>
        toggleHakoniwaRule(worldId, cardId, active, language, viewAreaId),
      );
      if (!result) return;
      applyWorld(result.world);
      recordCost(result.cost_usd);
      // 切り替え直後の住民の反応を、年代記に入らない一時の場面として先に再生する。
      // 書き換えが重なって対面が起きたら、その出来事を続けて再生する
      const reactions = result.reaction
        ? reactionEvents(result.reaction, result.world, viewAreaId)
        : [];
      if (reactions.length > 0 || result.new_events.length > 0) {
        setPlaybackQueue((current) => [
          ...current,
          ...reactions,
          ...result.new_events,
        ]);
      }
    },
    [
      applyWorld,
      language,
      reactionEvents,
      recordCost,
      run,
      viewAreaId,
      worldId,
    ],
  );

  const saveCustomRule = useCallback(
    async (rule: HakoniwaCustomRuleInput, ruleId?: string) => {
      if (!worldId) return false;
      const updated = await run("rule", () =>
        ruleId
          ? updateHakoniwaCustomRule(worldId, ruleId, rule, language)
          : addHakoniwaCustomRule(worldId, rule, language),
      );
      if (!updated) return false;
      applyWorld(updated);
      return true;
    },
    [applyWorld, language, run, worldId],
  );

  const deleteCustomRule = useCallback(
    async (ruleId: string) => {
      if (!worldId) return;
      const updated = await run("rule", () =>
        deleteHakoniwaCustomRule(worldId, ruleId, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const applyResidentChange = useCallback(
    (result: HakoniwaResidentChange | null) => {
      if (!result) return false;
      applyWorld(result.world);
      return true;
    },
    [applyWorld],
  );

  /** タグを作る API を呼び、料金を記録する(フォームの中で使うので busy は変えない) */
  const makeTags = useCallback(
    async (
      task: () => Promise<{ tags: string; cost_usd: number | null }>,
    ): Promise<HakoniwaTagsOutcome> => {
      try {
        const result = await task();
        recordCost(result.cost_usd);
        return { tags: result.tags, error: null };
      } catch (caught) {
        return { tags: null, error: errorText(caught) };
      }
    },
    [errorText, recordCost],
  );

  const makeRuleLookTags = useCallback(
    (input: HakoniwaRuleLookTagsInput) =>
      makeTags(() => makeHakoniwaRuleLookTags(input, language)),
    [language, makeTags],
  );

  const makeResidentTags = useCallback(
    (input: HakoniwaResidentTagsInput) =>
      makeTags(() => makeHakoniwaResidentTags(input, language)),
    [language, makeTags],
  );

  const saveResident = useCallback(
    async (input: HakoniwaResidentInput, residentId?: string) => {
      if (!worldId) return false;
      const result = await run("resident", () =>
        residentId
          ? updateHakoniwaResident(worldId, residentId, input, language)
          : addHakoniwaResident(worldId, input, language),
      );
      return applyResidentChange(result);
    },
    [applyResidentChange, language, run, worldId],
  );

  const addCharacterResident = useCallback(
    async (entry: HakoniwaCharacterEntry) => {
      if (!worldId) return false;
      const result = await run("resident", () =>
        addHakoniwaCharacterResident(worldId, entry, language),
      );
      return applyResidentChange(result);
    },
    [applyResidentChange, language, run, worldId],
  );

  const removeResident = useCallback(
    async (residentId: string) => {
      if (!worldId) return;
      const updated = await run("resident", () =>
        removeHakoniwaResident(worldId, residentId, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const greet = useCallback(
    async (residentId: string) => {
      if (!worldId) return;
      setGreetingResidentId(residentId);
      try {
        const result = await greetHakoniwaResident(
          worldId,
          residentId,
          language,
        );
        recordCost(result.cost_usd);
        greetingKey.current += 1;
        setGreeting({
          residentId,
          text: result.text,
          key: greetingKey.current,
        });
      } catch (caught) {
        setError(errorText(caught));
      } finally {
        setGreetingResidentId((current) =>
          current === residentId ? null : current,
        );
      }
    },
    [errorText, language, recordCost, worldId],
  );

  const dismissGreeting = useCallback(() => setGreeting(null), []);

  const refreshUsage = useCallback(() => {
    if (settingsState.imageProvider !== "novelai") return;
    void fetchAnlasBalance().then((balance) => {
      if (balance) setAnlasBalance(balance);
    });
  }, [setAnlasBalance, settingsState.imageProvider]);

  /**
   * 画像を生成する操作を実行する。V5 の利用上限を使い切っていると Anlas を消費する
   * ため、抑止されていなければ先に確認を出す。
   */
  const usageNeedsConfirm = useCallback(() => {
    const usage = settingsState.anlasBalance?.usage;
    const exhausted = usage != null && (usage.percent <= 0 || usage.isNegative);
    const v5 =
      settingsState.imageProvider === "novelai" &&
      world != null &&
      isV5ImageModel(world.image_model_effective);
    return (
      v5 &&
      exhausted &&
      !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
    );
  }, [settingsState.anlasBalance, settingsState.imageProvider, world]);

  const guardImageGeneration = useCallback(
    (task: () => void) => {
      if (usageNeedsConfirm()) {
        setPendingUsageTask(() => task);
        return;
      }
      task();
    },
    [usageNeedsConfirm],
  );

  const confirmUsage = useCallback(
    (doNotShowAgain: boolean) => {
      if (doNotShowAgain) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      const task = pendingUsageTask;
      setPendingUsageTask(null);
      task?.();
    },
    [pendingUsageTask],
  );

  const cancelUsage = useCallback(() => setPendingUsageTask(null), []);

  const transform = useCallback(
    (residentId: string, instruction: string) => {
      if (!worldId) return;
      guardImageGeneration(() => {
        void (async () => {
          const result = await run("transform", () =>
            transformHakoniwaResident(
              worldId,
              residentId,
              instruction,
              language,
            ),
          );
          if (!result) return;
          applyWorld(result.world);
          recordCost(result.cost_usd);
          refreshUsage();
          setGreeting(null);
          setPlaybackQueue((current) => [...current, ...result.new_events]);
        })();
      });
    },
    [
      applyWorld,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      worldId,
    ],
  );

  const alterReality = useCallback(
    (residentId: string, instruction: string, changeLook: boolean) => {
      if (!worldId) return;
      const task = () => {
        void (async () => {
          const result = await run("reality", () =>
            alterHakoniwaReality(
              worldId,
              residentId,
              instruction,
              changeLook,
              language,
            ),
          );
          if (!result) return;
          applyWorld(result.world);
          recordCost(result.cost_usd);
          if (changeLook) refreshUsage();
          setGreeting(null);
          setPlaybackQueue((current) => [...current, ...result.new_events]);
        })();
      };
      // 姿を変えないときは画像を作らないので、利用上限の確認は要らない
      if (changeLook) guardImageGeneration(task);
      else task();
    },
    [
      applyWorld,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      worldId,
    ],
  );

  const removeReality = useCallback(
    async (residentId: string, realityId: string) => {
      if (!worldId) return;
      const updated = await run("reality", () =>
        removeHakoniwaReality(worldId, residentId, realityId, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  /**
   * 出来事の結果として姿が変わった住民の立ち絵を、1人ずつ生成する。
   * 先に全員ぶんの変化を決めてから描く(服の交換は、相手の出来事の前の姿が要る)。
   * 失敗しても出来事の文章はできているので、知らせて戻る。このあと開く ADV は
   * 開いた時点で画面のエラーの帯を消すため、結果は通知で出す
   */
  const changeEventLooks = useCallback(
    async (startWorldId: string, eventId: string) => {
      try {
        setEventProgress({ phase: "planning", done: 0, total: 0 });
        const plan = await planHakoniwaEventLooks(
          startWorldId,
          eventId,
          language,
        );
        applyWorld(plan.world);
        recordCost(plan.cost_usd);
        const total = plan.changes.length;
        if (total === 0) {
          showNotification("info", t("hakoniwa.panel.eventLookNone"));
          return;
        }
        let failed = 0;
        for (const [index, change] of plan.changes.entries()) {
          if (currentWorldIdRef.current !== startWorldId) return;
          setEventProgress({ phase: "portraits", done: index, total });
          try {
            const drawn = await applyHakoniwaEventLook(
              startWorldId,
              eventId,
              change.resident_id,
              language,
            );
            if (currentWorldIdRef.current !== startWorldId) return;
            applyWorld(drawn.world);
            recordCost(drawn.cost_usd);
          } catch (caught) {
            failed += 1;
            // 画像の失敗以外(出来事や住民が消えたなど)は、次の住民でも同じになるので止める
            const code = caught instanceof ApiError ? caught.code : null;
            if (code !== "image_generation_failed") {
              showNotification(
                "warning",
                t("hakoniwa.panel.eventLookFailed"),
                errorText(caught),
              );
              return;
            }
          }
        }
        if (failed > 0) {
          showNotification(
            "warning",
            t("hakoniwa.panel.eventLookFailed"),
            t("hakoniwa.panel.eventLookPartial", { count: failed }),
          );
        }
      } catch (caught) {
        showNotification(
          "warning",
          t("hakoniwa.panel.eventLookFailed"),
          errorText(caught),
        );
      } finally {
        refreshUsage();
      }
    },
    [
      applyWorld,
      errorText,
      language,
      recordCost,
      refreshUsage,
      showNotification,
      t,
    ],
  );

  const directEvent = useCallback(
    (
      residentId: string,
      input: HakoniwaDirectedEventInput,
      changeLook: boolean,
    ) => {
      if (!worldId) return;
      const task = () => {
        void (async () => {
          // 文章と立ち絵を1つの操作として busy を保ち、全部できてから場面を開く
          const result = await run("event", async () => {
            setEventProgress({ phase: "writing", done: 0, total: 0 });
            try {
              const created = await createHakoniwaDirectedEvent(
                worldId,
                residentId,
                input,
                language,
              );
              applyWorld(created.world);
              recordCost(created.cost_usd);
              const scene = created.new_events[0];
              if (changeLook && scene) {
                await changeEventLooks(worldId, scene.id);
              }
              return created;
            } finally {
              setEventProgress(null);
            }
          });
          if (!result) return;
          setGreeting(null);
          const [scene, ...followUps] = result.new_events;
          if (!scene) return;
          setAdvFollowUps((current) => [...current, ...followUps]);
          setAdvEventId(scene.id);
        })();
      };
      // 立ち絵を作らないときは画像を作らないので、利用上限の確認は要らない
      if (changeLook) guardImageGeneration(task);
      else task();
    },
    [
      applyWorld,
      changeEventLooks,
      guardImageGeneration,
      language,
      recordCost,
      run,
      worldId,
    ],
  );

  const continueEvent = useCallback(
    (eventId: string, instruction: string, withSceneImage: boolean) => {
      if (!worldId) return;
      const task = () => {
        void (async () => {
          // 文章と絵を1つの操作として busy を保ち、絵ができるまで前の場面を見せておく
          const result = await run("event", async () => {
            setEventProgress({ phase: "writing", done: 0, total: 0 });
            try {
              const continued = await continueHakoniwaEvent(
                worldId,
                eventId,
                instruction,
                language,
              );
              applyWorld(continued.world);
              recordCost(continued.cost_usd);
              const scene = continued.new_events[0];
              if (!withSceneImage || !scene) return continued;
              setEventProgress({ phase: "scene", done: 0, total: 0 });
              try {
                const drawn = await generateHakoniwaSceneImage(
                  worldId,
                  scene.id,
                  language,
                );
                applyWorld(drawn.world);
                recordCost(drawn.cost_usd);
                refreshUsage();
              } catch (caught) {
                // 続きの文章はできているので、絵が無いまま場面を開いてエラーを出す
                setError(errorText(caught));
              }
              return continued;
            } finally {
              setEventProgress(null);
            }
          });
          if (!result) return;
          const [scene, ...followUps] = result.new_events;
          if (!scene) return;
          setAdvFollowUps((current) => [...current, ...followUps]);
          setAdvEventId(scene.id);
        })();
      };
      if (withSceneImage) guardImageGeneration(task);
      else task();
    },
    [
      applyWorld,
      errorText,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      worldId,
    ],
  );

  const generateAvatar = useCallback(
    (residentId: string, variant: "base" | "dress") => {
      if (!worldId) return;
      guardImageGeneration(() => {
        void (async () => {
          const result = await run("avatar", () =>
            generateHakoniwaAvatar(worldId, residentId, variant, language),
          );
          if (!result) return;
          applyWorld(result.world);
          recordCost(result.cost_usd);
          refreshUsage();
        })();
      });
    },
    [
      applyWorld,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      worldId,
    ],
  );

  const randomResidents = useCallback(
    async (count: number, excludeNames: string[]) => {
      const result = await run("random", () =>
        generateHakoniwaRandomResidents(count, excludeNames, language),
      );
      if (!result) return null;
      recordCost(result.cost_usd);
      return result.residents;
    },
    [language, recordCost, run],
  );

  const setExperimentTheme = useCallback(
    async (theme: HakoniwaTheme | null) => {
      if (!worldId) return false;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(
          worldId,
          { experiment_theme: theme ?? { preset_id: null, text: "" } },
          language,
        ),
      );
      if (!updated) return false;
      applyWorld(updated);
      return true;
    },
    [applyWorld, language, run, worldId],
  );

  const [avatarBatch, setAvatarBatch] = useState<HakoniwaAvatarBatch | null>(
    null,
  );
  const generateMissingAvatars = useCallback(() => {
    if (!worldId || !world) return;
    const targets = world.residents
      .filter((resident) => !resident.avatar_url)
      .map((resident) => resident.id);
    if (targets.length === 0) return;
    guardImageGeneration(() => {
      void (async () => {
        // 画像生成は並列にしない(NovelAI は同時に呼ぶと 429 になる)
        setAvatarBatch({ done: 0, total: targets.length });
        for (const [index, residentId] of targets.entries()) {
          const result = await run("avatar", () =>
            generateHakoniwaAvatar(worldId, residentId, "base", language),
          );
          if (!result) break;
          applyWorld(result.world);
          recordCost(result.cost_usd);
          setAvatarBatch({ done: index + 1, total: targets.length });
        }
        setAvatarBatch(null);
        refreshUsage();
      })();
    });
  }, [
    applyWorld,
    guardImageGeneration,
    language,
    recordCost,
    refreshUsage,
    run,
    world,
    worldId,
  ]);

  const setIntervention = useCallback(
    async (choice: HakoniwaInterventionChoice) => {
      if (!worldId) return;
      const updated = await run("settings", () =>
        setHakoniwaIntervention(worldId, choice, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const touchResident = useCallback(
    async (residentId: string, part: HakoniwaTouchPart) => {
      if (!worldId) return;
      const result = await run("touch", () =>
        touchHakoniwaResident(worldId, residentId, part, language),
      );
      if (!result) return;
      applyWorld(result.world);
      recordCost(result.cost_usd);
      setTouchReaction((current) => ({
        residentId,
        part,
        text: result.text,
        key: (current?.key ?? 0) + 1,
      }));
    },
    [applyWorld, language, recordCost, run, worldId],
  );

  const clearTouchReaction = useCallback(() => setTouchReaction(null), []);

  const openChat = useCallback(
    (residentId: string) => {
      if (!worldId) return;
      setChatResidentId(residentId);
      setChatHistory([]);
      void fetchHakoniwaChat(worldId, residentId)
        .then(setChatHistory)
        .catch((caught: unknown) => setError(errorText(caught)));
    },
    [errorText, worldId],
  );

  const closeChat = useCallback(() => {
    setChatResidentId(null);
    setChatHistory([]);
    // 会話の中で変身したら、その出来事を部屋で再生する
    if (chatEvents.length > 0) {
      setPlaybackQueue((current) => [...current, ...chatEvents]);
      setChatEvents([]);
    }
  }, [chatEvents]);

  const sendChat = useCallback(
    async (message: string) => {
      if (!worldId || !chatResidentId) return false;
      const residentId = chatResidentId;
      const send = async (confirmed?: string): Promise<boolean> => {
        const result = await run("chat", () =>
          chatHakoniwaResident(
            worldId,
            residentId,
            {
              message,
              allow_image: confirmed !== undefined || !usageNeedsConfirm(),
              confirmed_instruction: confirmed,
            },
            language,
          ),
        );
        if (!result) return false;
        if (result.alteration.needs_confirmation) {
          // 変身の指示だった: V5 の利用上限の確認を出してから送り直す
          const instruction = result.alteration.instruction || message;
          guardImageGeneration(() => {
            void send(instruction);
          });
          return true;
        }
        if (result.world) applyWorld(result.world);
        setChatHistory(result.history);
        recordCost(result.cost_usd);
        if (result.new_events.length > 0) {
          refreshUsage();
          setChatEvents((current) => [...current, ...result.new_events]);
        }
        return true;
      };
      return send();
    },
    [
      applyWorld,
      chatResidentId,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      usageNeedsConfirm,
      worldId,
    ],
  );

  /**
   * 掟の姿・複合の姿・メモの姿を、source の世界の状態をもとに1人ずつ生成する。
   * onlyResidentIds を渡すと、その住民の姿だけを描き直す
   */
  const runLookGeneration = useCallback(
    (
      source: HakoniwaWorld,
      target: string,
      requestedRegenerate: boolean,
      onlyResidentIds?: string[],
    ) => {
      const startWorldId = source.id;
      const status =
        target === "combo"
          ? source.combo_look
          : target === "memo"
            ? source.memo_look
            : source.rule_cards.find((card) => card.id === target)?.look;
      // 選んだ住民は生成済みでも描き直す
      const regenerate = requestedRegenerate || onlyResidentIds !== undefined;
      // 選んだ住民だけ、描き直しは全員、それ以外はまだ(または見た目を変える前)の住民だけ
      const residentIds = onlyResidentIds
        ? source.residents
            .map((resident) => resident.id)
            .filter((id) => onlyResidentIds.includes(id))
        : regenerate
          ? source.residents.map((resident) => resident.id)
          : (status?.pending ?? []);
      if (residentIds.length === 0) return;
      guardImageGeneration(() => {
        void (async () => {
          const total = residentIds.length;
          setLookTarget(target);
          setLookProgress({ target, done: 0, total });
          setBusy("look");
          setError(null);
          let generated = 0;
          let failed = 0;
          let lastError: string | null = null;
          try {
            // 1人ずつ呼び、そのたびに保存された世界を映して進み具合を出す
            for (const [index, residentId] of residentIds.entries()) {
              if (currentWorldIdRef.current !== startWorldId) break;
              try {
                const result =
                  target === "combo"
                    ? await generateHakoniwaComboLook(
                        startWorldId,
                        regenerate,
                        language,
                        residentId,
                      )
                    : target === "memo"
                      ? await generateHakoniwaMemoLook(
                          startWorldId,
                          regenerate,
                          language,
                          residentId,
                        )
                      : await generateHakoniwaRuleLook(
                          startWorldId,
                          target,
                          regenerate,
                          language,
                          residentId,
                        );
                if (currentWorldIdRef.current !== startWorldId) break;
                applyWorld(result.world);
                recordCost(result.cost_usd);
                generated += result.generated;
                failed += result.failed;
              } catch (caught) {
                failed += 1;
                lastError = errorText(caught);
                // 画像の失敗以外(掟が消えた・設定の不足など)は、次の住民でも同じになるので止める
                const code = caught instanceof ApiError ? caught.code : null;
                if (code !== "image_generation_failed") break;
              }
              setLookProgress({ target, done: index + 1, total });
            }
          } finally {
            setBusy(null);
            setLookTarget(null);
            setLookProgress(null);
            refreshUsage();
          }
          if (failed > 0) {
            setError(
              generated > 0 || !lastError
                ? t("hakoniwa.rules.lookPartial", { count: failed })
                : lastError,
            );
          }
        })();
      });
    },
    [
      applyWorld,
      errorText,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      t,
    ],
  );

  const generateLook = useCallback(
    (target: string, regenerate: boolean, residentIds?: string[]) => {
      if (world) runLookGeneration(world, target, regenerate, residentIds);
    },
    [runLookGeneration, world],
  );

  /**
   * いまの世界のメモが住民全員の姿を変えるかを確かめ、変えるなら、まだの住民の姿を
   * 1人ずつ生成する(同じメモで確かめ済みならバックエンドは LLM を呼ばない)
   */
  const applyMemoLook = useCallback(
    async (targetWorldId: string) => {
      setLookTarget("memo");
      const planned = await run("look", () =>
        planHakoniwaMemoLook(targetWorldId, language),
      );
      setLookTarget(null);
      if (!planned) return;
      applyWorld(planned.world);
      recordCost(planned.cost_usd);
      if (planned.changes_look) runLookGeneration(planned.world, "memo", false);
    },
    [applyWorld, language, recordCost, run, runLookGeneration],
  );

  const setWorldMemo = useCallback(
    async (memo: string) => {
      if (!worldId) return false;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(worldId, { world_memo: memo }, language),
      );
      if (!updated) return false;
      applyWorld(updated);
      // メモは世界の現実なので、姿に関わる内容なら住民全員の姿も描き直す
      if (!updated.memo_look_planned) await applyMemoLook(worldId);
      return true;
    },
    [applyMemoLook, applyWorld, language, run, worldId],
  );

  const setPlayerName = useCallback(
    async (name: string) => {
      if (!worldId) return false;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(worldId, { player_name: name }, language),
      );
      if (!updated) return false;
      applyWorld(updated);
      return true;
    },
    [applyWorld, language, run, worldId],
  );

  const generateSceneImage = useCallback(
    (eventId: string) => {
      if (!worldId) return;
      guardImageGeneration(() => {
        void (async () => {
          const result = await run("scene", () =>
            generateHakoniwaSceneImage(worldId, eventId, language),
          );
          if (!result) return;
          applyWorld(result.world);
          recordCost(result.cost_usd);
          refreshUsage();
        })();
      });
    },
    [
      applyWorld,
      guardImageGeneration,
      language,
      recordCost,
      refreshUsage,
      run,
      worldId,
    ],
  );

  const clearTransform = useCallback(
    async (residentId: string) => {
      if (!worldId) return;
      const updated = await run("transform", () =>
        clearHakoniwaTransform(worldId, residentId, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const reapplyTransform = useCallback(
    async (residentId: string, image: string) => {
      if (!worldId) return;
      const updated = await run("transform", () =>
        reapplyHakoniwaTransform(worldId, residentId, image, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const setFavorite = useCallback(
    async (eventId: string, favorite: boolean) => {
      if (!worldId) return;
      try {
        applyWorld(
          await setHakoniwaFavorite(worldId, eventId, favorite, language),
        );
      } catch (caught) {
        setError(errorText(caught));
      }
    },
    [applyWorld, errorText, language, worldId],
  );

  const setImageModel = useCallback(
    async (imageModel: string) => {
      if (!worldId) return;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(worldId, { image_model: imageModel }, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const setWebSearchEnabled = useCallback(
    async (enabled: boolean) => {
      if (!worldId) return;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(
          worldId,
          { web_search_enabled: enabled },
          language,
        ),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const setDissonanceEnabled = useCallback(
    async (enabled: boolean) => {
      if (!worldId) return;
      const updated = await run("settings", () =>
        updateHakoniwaSettings(
          worldId,
          { dissonance_enabled: enabled },
          language,
        ),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const finishPlayback = useCallback(() => {
    setPlaybackQueue((current) => current.slice(1));
  }, []);

  const replayEvent = useCallback((event: HakoniwaEvent) => {
    setGreeting(null);
    setPlaybackQueue((current) => [...current, event]);
  }, []);

  const clearPlayback = useCallback(() => setPlaybackQueue([]), []);

  const selectResident = useCallback(
    (residentId: string | null) => setSelectedResidentId(residentId),
    [],
  );

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<HakoniwaContextValue>(
    () => ({
      catalog,
      worlds,
      world,
      busy,
      greetingResidentId,
      greeting,
      playbackQueue,
      selectedResidentId,
      selectResident,
      panelTab,
      setPanelTab,
      error,
      clearError,
      usageConfirmOpen: pendingUsageTask !== null,
      confirmUsage,
      cancelUsage,
      loadCatalog,
      loadWorlds,
      openWorld,
      closeWorld,
      createWorld,
      randomResidents,
      setExperimentTheme,
      generateMissingAvatars,
      avatarBatch,
      deleteWorld,
      advanceDay,
      toggleRule,
      saveCustomRule,
      generateLook,
      applyMemoLook,
      lookTarget,
      lookProgress,
      deleteCustomRule,
      saveResident,
      makeRuleLookTags,
      makeResidentTags,
      addCharacterResident,
      removeResident,
      greet,
      dismissGreeting,
      transform,
      alterReality,
      removeReality,
      directEvent,
      eventProgress,
      continueEvent,
      clearTransform,
      reapplyTransform,
      generateAvatar,
      setFavorite,
      setImageModel,
      setDissonanceEnabled,
      setWebSearchEnabled,
      setWorldMemo,
      setPlayerName,
      setIntervention,
      touchReaction,
      touchResident,
      clearTouchReaction,
      chatResidentId,
      chatHistory,
      openChat,
      closeChat,
      sendChat,
      finishPlayback,
      replayEvent,
      clearPlayback,
      viewAreaId,
      setViewAreaId,
      placeFurniture,
      generateSceneImage,
      digestVisible,
      showDigest,
      hideDigest,
      advEventId,
      openAdv,
      closeAdv,
    }),
    [
      catalog,
      worlds,
      world,
      busy,
      greetingResidentId,
      greeting,
      playbackQueue,
      selectedResidentId,
      selectResident,
      panelTab,
      error,
      clearError,
      pendingUsageTask,
      confirmUsage,
      cancelUsage,
      loadCatalog,
      loadWorlds,
      openWorld,
      closeWorld,
      createWorld,
      randomResidents,
      setExperimentTheme,
      generateMissingAvatars,
      avatarBatch,
      deleteWorld,
      advanceDay,
      toggleRule,
      saveCustomRule,
      generateLook,
      applyMemoLook,
      lookTarget,
      lookProgress,
      deleteCustomRule,
      saveResident,
      makeRuleLookTags,
      makeResidentTags,
      addCharacterResident,
      removeResident,
      greet,
      dismissGreeting,
      transform,
      alterReality,
      removeReality,
      directEvent,
      eventProgress,
      continueEvent,
      clearTransform,
      reapplyTransform,
      generateAvatar,
      setFavorite,
      setImageModel,
      setDissonanceEnabled,
      setWebSearchEnabled,
      setWorldMemo,
      setPlayerName,
      setIntervention,
      touchReaction,
      touchResident,
      clearTouchReaction,
      chatResidentId,
      chatHistory,
      openChat,
      closeChat,
      sendChat,
      finishPlayback,
      replayEvent,
      clearPlayback,
      viewAreaId,
      placeFurniture,
      generateSceneImage,
      digestVisible,
      showDigest,
      hideDigest,
      advEventId,
      openAdv,
      closeAdv,
    ],
  );

  return (
    <HakoniwaContext.Provider value={value}>
      {children}
    </HakoniwaContext.Provider>
  );
}

export function useHakoniwa(): HakoniwaContextValue {
  const context = useContext(HakoniwaContext);
  if (!context) {
    throw new Error("useHakoniwa must be used within HakoniwaProvider");
  }
  return context;
}
