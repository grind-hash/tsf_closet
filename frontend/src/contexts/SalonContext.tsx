/**
 * SalonContext - サロン経営モードの状態(サロン一覧・開いているサロン・操作中の表示)。
 *
 * 接客中のお客様はふつうのゲームセッションなので、画像・心境・依頼の状態は
 * GameContext が持つ。ここでは来店と経営(予約・会計・週の締め)だけを扱う。
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import {
  buySalonExtraTurn,
  checkoutSalonVisit,
  closeSalonWeek,
  createSalonRun,
  declineSalonVisit,
  deleteSalonRun,
  fetchSalonRun,
  fetchSalonRuns,
  type SalonCloseWeek,
  type SalonDifficulty,
  type SalonRun,
  type SalonVisit,
  type SalonVisitStart,
  startSalonVisit,
  updateSalonRunSettings,
} from "../apis/salon";
import { useChat } from "./ChatContext";
import { useGame } from "./GameContext";
import { useNotification } from "./NotificationContext";
import { useSettings } from "./SettingsContext";

/** 処理中の操作。ボタンの無効化とスピナーの表示に使う */
export type SalonBusy =
  | "load"
  | "create"
  | "delete"
  | "decline"
  | "close"
  | "start"
  | "checkout"
  | "settings"
  | "extra"
  | null;

interface SalonContextValue {
  runs: SalonRun[];
  activeRun: SalonRun | null;
  busy: SalonBusy;
  error: string | null;
  clearError: () => void;
  loadRuns: () => Promise<void>;
  openRun: (runId: string) => Promise<SalonRun | null>;
  /** 開店する。sensitive は過激施術の初期値(開店後もオーナー室で切り替えられる) */
  createRun: (
    name: string,
    difficulty: SalonDifficulty,
    sensitive: boolean,
  ) => Promise<SalonRun | null>;
  deleteRun: (runId: string) => Promise<void>;
  /** 開いているサロンの設定(過激施術)を変える */
  updateRunSettings: (settings: { sensitive: boolean }) => Promise<void>;
  declineVisit: (visitId: string) => Promise<void>;
  closeWeek: () => Promise<SalonCloseWeek | null>;
  /** 接客を始める(接客中なら戻る)。ゲームのセッションを差し替え、開始の応答を返す */
  startVisit: (
    runId: string,
    visitId: string,
  ) => Promise<SalonVisitStart | null>;
  /** 資金を払って施術を1手足す。依頼の手数を差し替え、成功したら true */
  buyExtraTurn: (visitId: string) => Promise<boolean>;
  /** 会計する。ゲームのセッションを手放し、会計後の来店を返す */
  checkoutVisit: (visitId: string) => Promise<SalonVisit | null>;
}

const SalonContext = createContext<SalonContextValue | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function SalonProvider({ children }: { children: ReactNode }) {
  const { state: settingsState, addTotalCost } = useSettings();
  const { restoreSessionById, clearSession, applyRequestView } = useGame();
  const { clearMessages, setInputText } = useChat();
  const { showAchievementNotification } = useNotification();
  const [runs, setRuns] = useState<SalonRun[]>([]);
  const [activeRun, setActiveRun] = useState<SalonRun | null>(null);
  const [busy, setBusy] = useState<SalonBusy>(null);
  const [error, setError] = useState<string | null>(null);
  const language = settingsState.language;

  /** 操作を1つずつ実行し、失敗はメッセージにして null を返す */
  const run = useCallback(
    async <T,>(kind: SalonBusy, task: () => Promise<T>): Promise<T | null> => {
      setBusy(kind);
      setError(null);
      try {
        return await task();
      } catch (caught) {
        setError(errorMessage(caught));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const loadRuns = useCallback(async () => {
    const loaded = await run("load", fetchSalonRuns);
    if (loaded) setRuns(loaded);
  }, [run]);

  const openRun = useCallback(
    (runId: string) =>
      run("load", async () => {
        const loaded = await fetchSalonRun(runId);
        setActiveRun(loaded);
        return loaded;
      }),
    [run],
  );

  const createRun = useCallback(
    (name: string, difficulty: SalonDifficulty, sensitive: boolean) =>
      run("create", async () => {
        const created = await createSalonRun(name, difficulty, sensitive);
        setRuns((current) => [created, ...current]);
        setActiveRun(created);
        return created;
      }),
    [run],
  );

  const deleteRun = useCallback(
    async (runId: string) => {
      await run("delete", async () => {
        await deleteSalonRun(runId);
        setRuns((current) => current.filter((item) => item.id !== runId));
        setActiveRun((current) => (current?.id === runId ? null : current));
      });
    },
    [run],
  );

  const updateRunSettings = useCallback(
    async (settings: { sensitive: boolean }) => {
      if (!activeRun) return;
      const updated = await run("settings", () =>
        updateSalonRunSettings(activeRun.id, settings),
      );
      if (!updated) return;
      setActiveRun(updated);
      setRuns((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
    [activeRun, run],
  );

  const declineVisit = useCallback(
    async (visitId: string) => {
      if (!activeRun) return;
      const updated = await run("decline", () =>
        declineSalonVisit(activeRun.id, visitId),
      );
      if (updated) setActiveRun(updated);
    },
    [activeRun, run],
  );

  const closeWeek = useCallback(async () => {
    if (!activeRun) return null;
    const result = await run("close", () => closeSalonWeek(activeRun.id));
    if (!result) return null;
    setActiveRun(result.run);
    for (const item of result.achievements) {
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
    return result;
  }, [activeRun, run, showAchievementNotification]);

  const startVisit = useCallback(
    (runId: string, visitId: string) =>
      run("start", async () => {
        const result = await startSalonVisit(runId, visitId, language);
        if (result.cost_usd) addTotalCost(result.cost_usd);
        // 通常のプレイ画面の会話や下書きを、お客様の接客に持ち込まない
        clearMessages();
        setInputText("");
        if (!(await restoreSessionById(result.session_id))) {
          throw new Error("お客様のセッションを開けませんでした");
        }
        setActiveRun(result.run);
        return result;
      }),
    [
      addTotalCost,
      clearMessages,
      language,
      restoreSessionById,
      run,
      setInputText,
    ],
  );

  const buyExtraTurn = useCallback(
    async (visitId: string) => {
      if (!activeRun) return false;
      const result = await run("extra", () =>
        buySalonExtraTurn(activeRun.id, visitId),
      );
      if (!result) return false;
      setActiveRun(result.run);
      if (result.request) applyRequestView(result.request);
      return true;
    },
    [activeRun, applyRequestView, run],
  );

  const checkoutVisit = useCallback(
    (visitId: string) => {
      const current = activeRun;
      if (!current) return Promise.resolve(null);
      return run("checkout", async () => {
        const result = await checkoutSalonVisit(current.id, visitId, language);
        if (result.cost_usd) addTotalCost(result.cost_usd);
        setActiveRun(result.run);
        // バックエンドも会計でセッションのアクティブを外す
        clearSession();
        clearMessages();
        return result.visit;
      });
    },
    [activeRun, addTotalCost, clearMessages, clearSession, language, run],
  );

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<SalonContextValue>(
    () => ({
      runs,
      activeRun,
      busy,
      error,
      clearError,
      loadRuns,
      openRun,
      createRun,
      deleteRun,
      updateRunSettings,
      declineVisit,
      closeWeek,
      startVisit,
      buyExtraTurn,
      checkoutVisit,
    }),
    [
      runs,
      activeRun,
      busy,
      error,
      clearError,
      loadRuns,
      openRun,
      createRun,
      deleteRun,
      updateRunSettings,
      declineVisit,
      closeWeek,
      startVisit,
      buyExtraTurn,
      checkoutVisit,
    ],
  );

  return (
    <SalonContext.Provider value={value}>{children}</SalonContext.Provider>
  );
}

export function useSalon(): SalonContextValue {
  const context = useContext(SalonContext);
  if (!context) {
    throw new Error("useSalon must be used within SalonProvider");
  }
  return context;
}
