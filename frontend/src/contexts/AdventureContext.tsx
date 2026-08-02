import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import {
  type AdventureCreateRequest,
  type AdventureRun,
  type AdventureSetup,
  type AdventureSetupRequest,
  type AdventureTemplate,
  type AdventureTurn,
  createAdventureRun,
  deleteAdventureRun,
  fetchAdventureRun,
  fetchAdventureRuns,
  fetchAdventureTemplates,
  generateAdventureSetup,
  normalizeAdventureImageUrl,
  streamAdventureImage,
  streamAdventureTurn,
} from "../apis/adventure";

interface AdventureContextValue {
  runs: AdventureRun[];
  templates: AdventureTemplate[];
  activeRun: AdventureRun | null;
  loading: boolean;
  setupGenerating: boolean;
  streaming: boolean;
  phase: string | null;
  error: string | null;
  loadRuns: () => Promise<void>;
  loadTemplates: () => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  generateSetup: (request: AdventureSetupRequest) => Promise<AdventureSetup>;
  createRun: (request: AdventureCreateRequest) => Promise<AdventureRun>;
  removeRun: (runId: string) => Promise<void>;
  submitTurn: (
    input: string,
    inputKind: "choice" | "free_text",
  ) => Promise<void>;
  regenerateImage: () => Promise<void>;
  clearError: () => void;
}

const AdventureContext = createContext<AdventureContextValue | null>(null);

export function AdventureProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<AdventureRun[]>([]);
  const [templates, setTemplates] = useState<AdventureTemplate[]>([]);
  const [activeRun, setActiveRun] = useState<AdventureRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [setupGenerating, setSetupGenerating] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [phase, setPhase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRuns(await fetchAdventureRuns());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    setError(null);
    try {
      setTemplates(await fetchAdventureTemplates());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    setLoading(true);
    setError(null);
    try {
      setActiveRun(await fetchAdventureRun(runId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setLoading(false);
    }
  }, []);

  const generateSetup = useCallback(async (request: AdventureSetupRequest) => {
    setSetupGenerating(true);
    setError(null);
    try {
      return await generateAdventureSetup(request);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setSetupGenerating(false);
    }
  }, []);

  const createRun = useCallback(async (request: AdventureCreateRequest) => {
    setLoading(true);
    setError(null);
    try {
      const created = await createAdventureRun(request);
      setActiveRun(created);
      setRuns((current) => [created, ...current]);
      return created;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setLoading(false);
    }
  }, []);

  const removeRun = useCallback(async (runId: string) => {
    setError(null);
    try {
      await deleteAdventureRun(runId);
      setRuns((current) => current.filter((run) => run.id !== runId));
      setActiveRun((current) => (current?.id === runId ? null : current));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    }
  }, []);

  const submitTurn = useCallback(
    async (input: string, inputKind: "choice" | "free_text") => {
      if (!activeRun || streaming) return;
      const runId = activeRun.id;
      setStreaming(true);
      setPhase("judging");
      setError(null);
      try {
        await streamAdventureTurn(
          runId,
          {
            client_turn_id: crypto.randomUUID(),
            user_input: input,
            input_kind: inputKind,
          },
          (event) => {
            if (event.type === "status") {
              setPhase(String(event.data.phase ?? ""));
            } else if (event.type === "turn") {
              const turn = event.data as unknown as AdventureTurn;
              setActiveRun((current) =>
                current
                  ? {
                      ...current,
                      turns: [...current.turns, turn],
                      choices: turn.choices,
                      turn_count: turn.turn_number,
                      remaining_turns:
                        turn.remaining_turns ?? current.remaining_turns,
                      clues: turn.clues ?? current.clues,
                      status: turn.run_status ?? current.status,
                      ending_title: turn.ending_title ?? current.ending_title,
                      ending_summary:
                        turn.ending_summary ?? current.ending_summary,
                    }
                  : current,
              );
            } else if (event.type === "image") {
              const imageUrl = normalizeAdventureImageUrl(event.data.image_url);
              if (imageUrl) {
                setActiveRun((current) =>
                  current
                    ? { ...current, current_image_url: imageUrl }
                    : current,
                );
              }
            } else if (event.type === "error") {
              setError(
                String(event.data.message ?? "Adventure request failed"),
              );
            }
          },
        );
        setActiveRun(await fetchAdventureRun(runId));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        setStreaming(false);
        setPhase(null);
      }
    },
    [activeRun, streaming],
  );

  const regenerateImage = useCallback(async () => {
    if (!activeRun || streaming) return;
    setStreaming(true);
    setPhase("image_generation");
    setError(null);
    try {
      await streamAdventureImage(activeRun.id, (event) => {
        if (event.type === "status") {
          setPhase(String(event.data.phase ?? ""));
        } else if (event.type === "image") {
          const imageUrl = normalizeAdventureImageUrl(event.data.image_url);
          if (imageUrl) {
            setActiveRun((current) =>
              current ? { ...current, current_image_url: imageUrl } : current,
            );
          }
        } else if (event.type === "error") {
          setError(String(event.data.message ?? "Image generation failed"));
        }
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setStreaming(false);
      setPhase(null);
    }
  }, [activeRun, streaming]);

  const value = useMemo<AdventureContextValue>(
    () => ({
      runs,
      templates,
      activeRun,
      loading,
      setupGenerating,
      streaming,
      phase,
      error,
      loadRuns,
      loadTemplates,
      loadRun,
      generateSetup,
      createRun,
      removeRun,
      submitTurn,
      regenerateImage,
      clearError: () => setError(null),
    }),
    [
      runs,
      templates,
      activeRun,
      loading,
      setupGenerating,
      streaming,
      phase,
      error,
      loadRuns,
      loadTemplates,
      loadRun,
      generateSetup,
      createRun,
      removeRun,
      submitTurn,
      regenerateImage,
    ],
  );

  return (
    <AdventureContext.Provider value={value}>
      {children}
    </AdventureContext.Provider>
  );
}

export function useAdventure(): AdventureContextValue {
  const context = useContext(AdventureContext);
  if (!context) {
    throw new Error("useAdventure must be used within AdventureProvider");
  }
  return context;
}
