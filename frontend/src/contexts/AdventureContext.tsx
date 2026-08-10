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
  type AdventureImageRegenerateOptions,
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
  regenerateAdventureChoices,
  streamAdventureImage,
  streamAdventureTurn,
  updateAdventureRunSettings,
} from "../apis/adventure";

export type AdventurePhase = "narrative" | "clue_check" | "image_generation";

interface AdventureContextValue {
  runs: AdventureRun[];
  templates: AdventureTemplate[];
  activeRun: AdventureRun | null;
  loading: boolean;
  setupGenerating: boolean;
  streaming: boolean;
  phase: AdventurePhase | null;
  streamingNarrative: string;
  pendingUserInput: string | null;
  error: string | null;
  loadRuns: () => Promise<void>;
  loadTemplates: () => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  generateSetup: (request: AdventureSetupRequest) => Promise<AdventureSetup>;
  createRun: (request: AdventureCreateRequest) => Promise<AdventureRun>;
  removeRun: (runId: string) => Promise<void>;
  submitTurn: (
    input: string,
    inputKind: "choice" | "free_text" | "reality_alter",
  ) => Promise<void>;
  regenerateImage: (options?: AdventureImageRegenerateOptions) => Promise<void>;
  regenerateChoices: () => Promise<void>;
  updateSettings: (settings: {
    use_precise_reference: boolean;
    enable_composite_scene: boolean;
  }) => Promise<void>;
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
  const [phase, setPhase] = useState<AdventurePhase | null>(null);
  const [streamingNarrative, setStreamingNarrative] = useState("");
  const [pendingUserInput, setPendingUserInput] = useState<string | null>(null);
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
    async (
      input: string,
      inputKind: "choice" | "free_text" | "reality_alter",
    ) => {
      if (!activeRun || streaming) return;
      const runId = activeRun.id;
      setStreaming(true);
      setPhase("narrative");
      setStreamingNarrative("");
      setPendingUserInput(input);
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
              setPhase((event.data.phase as AdventurePhase) ?? null);
            } else if (event.type === "narrative_chunk") {
              const chunk = String(event.data.chunk ?? "");
              if (chunk) setStreamingNarrative((current) => current + chunk);
            } else if (event.type === "narrative_done") {
              setStreamingNarrative(String(event.data.narrative ?? ""));
            } else if (event.type === "turn") {
              const turn = event.data as unknown as AdventureTurn;
              setStreamingNarrative("");
              setPendingUserInput(null);
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
                      completed_milestones:
                        turn.completed_milestones ??
                        current.completed_milestones,
                      visual_state: turn.visual_state ?? current.visual_state,
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
            } else if (event.type === "portrait_image") {
              const portraitUrl = normalizeAdventureImageUrl(
                event.data.image_url,
              );
              if (portraitUrl) {
                setActiveRun((current) =>
                  current
                    ? { ...current, portrait_image_url: portraitUrl }
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
        setStreamingNarrative("");
        setPendingUserInput(null);
      }
    },
    [activeRun, streaming],
  );

  const regenerateImage = useCallback(
    async (options?: AdventureImageRegenerateOptions) => {
      if (!activeRun || streaming) return;
      setStreaming(true);
      setPhase("image_generation");
      setError(null);
      try {
        await streamAdventureImage(activeRun.id, options ?? null, (event) => {
          if (event.type === "status") {
            setPhase((event.data.phase as AdventurePhase) ?? null);
          } else if (event.type === "image") {
            const imageUrl = normalizeAdventureImageUrl(event.data.image_url);
            if (imageUrl) {
              setActiveRun((current) =>
                current
                  ? {
                      ...current,
                      current_image_url: imageUrl,
                      current_image_prompt: options
                        ? {
                            scene_tags: options.scene_tags,
                            player_tags: options.player_tags,
                            npc_tags: options.npc_tags,
                          }
                        : current.current_image_prompt,
                    }
                  : current,
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
    },
    [activeRun, streaming],
  );

  const regenerateChoices = useCallback(async () => {
    if (!activeRun || streaming || activeRun.status !== "active") return;
    const runId = activeRun.id;
    setStreaming(true);
    setPhase("clue_check");
    setError(null);
    try {
      const choices = await regenerateAdventureChoices(runId);
      setActiveRun((current) =>
        current && current.id === runId ? { ...current, choices } : current,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setStreaming(false);
      setPhase(null);
    }
  }, [activeRun, streaming]);

  const updateSettings = useCallback(
    async (settings: {
      use_precise_reference: boolean;
      enable_composite_scene: boolean;
    }) => {
      if (!activeRun) return;
      const runId = activeRun.id;
      setError(null);
      try {
        const updated = await updateAdventureRunSettings(runId, settings);
        setActiveRun((current) =>
          current && current.id === runId
            ? { ...current, ...updated, turns: current.turns }
            : current,
        );
        setRuns((current) =>
          current.map((run) =>
            run.id === runId
              ? {
                  ...run,
                  use_precise_reference: updated.use_precise_reference,
                  enable_composite_scene: updated.enable_composite_scene,
                }
              : run,
          ),
        );
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        throw caught;
      }
    },
    [activeRun],
  );

  const value = useMemo<AdventureContextValue>(
    () => ({
      runs,
      templates,
      activeRun,
      loading,
      setupGenerating,
      streaming,
      phase,
      streamingNarrative,
      pendingUserInput,
      error,
      loadRuns,
      loadTemplates,
      loadRun,
      generateSetup,
      createRun,
      removeRun,
      submitTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
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
      streamingNarrative,
      pendingUserInput,
      error,
      loadRuns,
      loadTemplates,
      loadRun,
      generateSetup,
      createRun,
      removeRun,
      submitTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
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
