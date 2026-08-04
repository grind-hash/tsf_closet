import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import {
  type ActionResult,
  type AdvanceDayResult,
  advanceDay,
  type BloomerCatalog,
  type BloomerRun,
  type CreateRunRequest,
  createBloomerRun,
  deleteBloomerRun,
  equipOutfit,
  fetchBloomerCatalog,
  fetchBloomerRun,
  fetchBloomerRuns,
  performAction,
  resolveMilestone,
  streamBloomerImage,
} from "../apis/bloomer";
import { useSettings } from "./SettingsContext";

interface BloomerContextValue {
  runs: BloomerRun[];
  activeRun: BloomerRun | null;
  catalog: BloomerCatalog | null;
  loading: boolean;
  actionLoading: boolean;
  imageGenerating: boolean;
  error: string | null;
  lastAdvance: AdvanceDayResult | null;
  lastActionResult: ActionResult | null;

  loadRuns: () => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  loadCatalog: () => Promise<void>;
  createRun: (req: CreateRunRequest) => Promise<BloomerRun>;
  removeRun: (runId: string) => Promise<void>;
  backToHub: () => void;
  doAction: (
    actionKey: string,
    userText?: string,
  ) => Promise<ActionResult | null>;
  doAdvanceDay: () => Promise<AdvanceDayResult>;
  doMilestone: (choiceKey: string) => Promise<void>;
  doEquipOutfit: (outfitKey: string) => Promise<void>;
  generateImage: () => Promise<void>;
  clearError: () => void;
}

const BloomerContext = createContext<BloomerContextValue | null>(null);

export function BloomerProvider({ children }: { children: ReactNode }) {
  const { state: settings } = useSettings();
  const language = settings.language ?? "ja";

  const [runs, setRuns] = useState<BloomerRun[]>([]);
  const [activeRun, setActiveRun] = useState<BloomerRun | null>(null);
  const [catalog, setCatalog] = useState<BloomerCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [imageGenerating, setImageGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAdvance, setLastAdvance] = useState<AdvanceDayResult | null>(null);
  const [lastActionResult, setLastActionResult] = useState<ActionResult | null>(
    null,
  );

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRuns(await fetchBloomerRuns());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    setLoading(true);
    setError(null);
    try {
      setActiveRun(await fetchBloomerRun(runId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCatalog = useCallback(async () => {
    try {
      setCatalog(await fetchBloomerCatalog());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const createRun = useCallback(
    async (req: CreateRunRequest): Promise<BloomerRun> => {
      setLoading(true);
      setError(null);
      try {
        const run = await createBloomerRun(req);
        setRuns((prev) => [run, ...prev]);
        setActiveRun(run);
        return run;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        throw e;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const removeRun = useCallback(async (runId: string) => {
    setError(null);
    try {
      await deleteBloomerRun(runId);
      setRuns((prev) => prev.filter((r) => r.id !== runId));
      setActiveRun((prev) => (prev?.id === runId ? null : prev));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const backToHub = useCallback(() => setActiveRun(null), []);

  const doAction = useCallback(
    async (
      actionKey: string,
      userText?: string,
    ): Promise<ActionResult | null> => {
      if (!activeRun) return null;
      setActionLoading(true);
      setError(null);
      setLastActionResult(null);
      try {
        const result = await performAction(activeRun.id, {
          action_key: actionKey,
          language,
          user_text: userText,
        });
        setActiveRun(result.run);
        setLastActionResult(result);
        return result;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return null;
      } finally {
        setActionLoading(false);
      }
    },
    [activeRun, language],
  );

  const doAdvanceDay = useCallback(async (): Promise<AdvanceDayResult> => {
    if (!activeRun) throw new Error("no active run");
    setActionLoading(true);
    setError(null);
    try {
      const result = await advanceDay(activeRun.id, language);
      setActiveRun(result.run);
      setLastAdvance(result);
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      throw e;
    } finally {
      setActionLoading(false);
    }
  }, [activeRun, language]);

  const doMilestone = useCallback(
    async (choiceKey: string) => {
      if (!activeRun) return;
      setActionLoading(true);
      setError(null);
      try {
        const result = await resolveMilestone(
          activeRun.id,
          choiceKey,
          language,
        );
        setActiveRun(result.run);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setActionLoading(false);
      }
    },
    [activeRun, language],
  );

  const doEquipOutfit = useCallback(
    async (outfitKey: string) => {
      if (!activeRun) return;
      setActionLoading(true);
      setError(null);
      try {
        const run = await equipOutfit(activeRun.id, outfitKey);
        setActiveRun(run);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setActionLoading(false);
      }
    },
    [activeRun],
  );

  const generateImage = useCallback(async () => {
    if (!activeRun) return;
    setImageGenerating(true);
    setError(null);
    try {
      await streamBloomerImage(
        activeRun.id,
        language,
        (_base64, imagePath) => {
          setActiveRun((prev) =>
            prev ? { ...prev, current_image_path: imagePath } : prev,
          );
        },
        (msg) => setError(msg),
      );
    } finally {
      setImageGenerating(false);
    }
  }, [activeRun, language]);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo(
    () => ({
      runs,
      activeRun,
      catalog,
      loading,
      actionLoading,
      imageGenerating,
      error,
      lastAdvance,
      lastActionResult,
      loadRuns,
      loadRun,
      loadCatalog,
      createRun,
      removeRun,
      backToHub,
      doAction,
      doAdvanceDay,
      doMilestone,
      doEquipOutfit,
      generateImage,
      clearError,
    }),
    [
      runs,
      activeRun,
      catalog,
      loading,
      actionLoading,
      imageGenerating,
      error,
      lastAdvance,
      lastActionResult,
      loadRuns,
      loadRun,
      loadCatalog,
      createRun,
      removeRun,
      backToHub,
      doAction,
      doAdvanceDay,
      doMilestone,
      doEquipOutfit,
      generateImage,
      clearError,
    ],
  );

  return (
    <BloomerContext.Provider value={value}>{children}</BloomerContext.Provider>
  );
}

export function useBloomer(): BloomerContextValue {
  const ctx = useContext(BloomerContext);
  if (!ctx) throw new Error("useBloomer must be used inside BloomerProvider");
  return ctx;
}
