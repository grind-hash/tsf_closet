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
  clearHakoniwaTransform,
  createHakoniwaWorld,
  deleteHakoniwaCustomRule,
  deleteHakoniwaWorld,
  fetchHakoniwaCatalog,
  fetchHakoniwaWorld,
  fetchHakoniwaWorlds,
  generateHakoniwaAvatar,
  generateHakoniwaSceneImage,
  greetHakoniwaResident,
  type HakoniwaCatalog,
  type HakoniwaCharacterEntry,
  type HakoniwaEvent,
  type HakoniwaResidentChange,
  type HakoniwaResidentInput,
  type HakoniwaWorld,
  type HakoniwaWorldSummary,
  placeHakoniwaFurniture,
  reapplyHakoniwaTransform,
  removeHakoniwaResident,
  setHakoniwaFavorite,
  toggleHakoniwaRule,
  transformHakoniwaResident,
  updateHakoniwaCustomRule,
  updateHakoniwaResident,
  updateHakoniwaSettings,
} from "../apis/hakoniwa";
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
  | "avatar"
  | "settings"
  | "furniture"
  | "scene"
  | null;

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
] as const;
type HakoniwaErrorCode = (typeof HAKONIWA_ERROR_CODES)[number];

function isKnownErrorCode(code: string): code is HakoniwaErrorCode {
  return (HAKONIWA_ERROR_CODES as readonly string[]).includes(code);
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
  createWorld: (
    name: string,
    presetIds: string[],
    characters: HakoniwaCharacterEntry[],
  ) => Promise<HakoniwaWorld | null>;
  deleteWorld: (worldId: string) => Promise<void>;
  advanceDay: () => Promise<void>;
  toggleRule: (cardId: string, active: boolean) => Promise<void>;
  saveCustomRule: (
    rule: { name: string; text: string },
    ruleId?: string,
  ) => Promise<boolean>;
  deleteCustomRule: (ruleId: string) => Promise<void>;
  saveResident: (
    input: HakoniwaResidentInput,
    residentId?: string,
  ) => Promise<boolean>;
  addCharacterResident: (entry: HakoniwaCharacterEntry) => Promise<boolean>;
  removeResident: (residentId: string) => Promise<void>;
  greet: (residentId: string) => Promise<void>;
  dismissGreeting: () => void;
  transform: (residentId: string, instruction: string) => void;
  clearTransform: (residentId: string) => Promise<void>;
  reapplyTransform: (residentId: string, image: string) => Promise<void>;
  generateAvatar: (residentId: string, variant: "base" | "dress") => void;
  setFavorite: (eventId: string, favorite: boolean) => Promise<void>;
  setImageModel: (imageModel: string) => Promise<void>;
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
  const { showNotification } = useNotification();
  const [catalog, setCatalog] = useState<HakoniwaCatalog | null>(null);
  const [worlds, setWorlds] = useState<HakoniwaWorldSummary[]>([]);
  const [world, setWorld] = useState<HakoniwaWorld | null>(null);
  const [busy, setBusy] = useState<HakoniwaBusy>(null);
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
  const [error, setError] = useState<string | null>(null);
  const [pendingUsageTask, setPendingUsageTask] = useState<(() => void) | null>(
    null,
  );
  const greetingKey = useRef(0);
  const language = settingsState.language;
  const worldId = world?.id ?? null;

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

  const applyWorld = useCallback((next: HakoniwaWorld) => {
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
  }, []);

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
        setWorld(loaded);
        return loaded;
      }),
    [language, run],
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
  }, []);

  const createWorld = useCallback(
    (name: string, presetIds: string[], characters: HakoniwaCharacterEntry[]) =>
      run("create", async () => {
        const created = await createHakoniwaWorld({
          name,
          preset_ids: presetIds,
          characters,
          language,
        });
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
    [language, run],
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
  const closeAdv = useCallback(() => setAdvEventId(null), []);

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

  const toggleRule = useCallback(
    async (cardId: string, active: boolean) => {
      if (!worldId) return;
      const updated = await run("rule", () =>
        toggleHakoniwaRule(worldId, cardId, active, language),
      );
      if (updated) applyWorld(updated);
    },
    [applyWorld, language, run, worldId],
  );

  const saveCustomRule = useCallback(
    async (rule: { name: string; text: string }, ruleId?: string) => {
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
      recordCost(result.cost_usd);
      if (result.tag_expansion_failed) {
        showNotification(
          "warning",
          t("hakoniwa.residents.tagExpansionFailedTitle"),
          t("hakoniwa.residents.tagExpansionFailed"),
        );
      }
      return true;
    },
    [applyWorld, recordCost, showNotification, t],
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
  const guardImageGeneration = useCallback(
    (task: () => void) => {
      const usage = settingsState.anlasBalance?.usage;
      const exhausted =
        usage != null && (usage.percent <= 0 || usage.isNegative);
      const v5 =
        settingsState.imageProvider === "novelai" &&
        world != null &&
        isV5ImageModel(world.image_model_effective);
      if (
        v5 &&
        exhausted &&
        !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
      ) {
        setPendingUsageTask(() => task);
        return;
      }
      task();
    },
    [settingsState.anlasBalance, settingsState.imageProvider, world],
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
        updateHakoniwaSettings(worldId, imageModel, language),
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
      deleteWorld,
      advanceDay,
      toggleRule,
      saveCustomRule,
      deleteCustomRule,
      saveResident,
      addCharacterResident,
      removeResident,
      greet,
      dismissGreeting,
      transform,
      clearTransform,
      reapplyTransform,
      generateAvatar,
      setFavorite,
      setImageModel,
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
      deleteWorld,
      advanceDay,
      toggleRule,
      saveCustomRule,
      deleteCustomRule,
      saveResident,
      addCharacterResident,
      removeResident,
      greet,
      dismissGreeting,
      transform,
      clearTransform,
      reapplyTransform,
      generateAvatar,
      setFavorite,
      setImageModel,
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
