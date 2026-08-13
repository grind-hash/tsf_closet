import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  type AdventureCreateRequest,
  type AdventureImageRegenerateOptions,
  type AdventureInputKind,
  type AdventureRun,
  type AdventureSetup,
  type AdventureSetupRequest,
  type AdventureTemplate,
  type AdventureTurn,
  canActOnRun,
  createAdventureRun,
  deleteAdventureRun,
  fetchAdventureRun,
  fetchAdventureRuns,
  fetchAdventureTemplates,
  generateAdventureSetup,
  normalizeAdventureImageUrl,
  regenerateAdventureChoices,
  rewindAdventureRun,
  startAdventureEpilogue,
  streamAdventureImage,
  streamAdventureTurn,
  updateAdventureRunSettings,
} from "../apis/adventure";

export type AdventurePhase = "narrative" | "clue_check" | "image_generation";

// 立ち絵を毎ターン描くかのブラウザ単位設定(主人公/攻略対象で個別)。
// トグルUIは AdventureScreen 側にあり、送信経路(選択肢・自由入力・ギフト・
// 属性付与)が分散しても漏れないよう submitTurn で一元的にリクエストへ反映する
export const DRAW_PORTRAIT_STORAGE_KEY = "adventure_draw_portrait_every_turn";
export const DRAW_PARTNER_STORAGE_KEY = "adventure_draw_partner_every_turn";

// 精密参照ONの画像生成(run開始・romanceのターン送信)はAnlasを消費するため、
// 実行前に確認ダイアログを挟む。抑止はブラウザセッション単位(sessionStorage)
export const ANLAS_WARN_SUPPRESSED_KEY = "adventure_anlas_warn_suppressed";

function readDrawEveryTurn(storageKey: string): boolean {
  try {
    return localStorage.getItem(storageKey) !== "false";
  } catch {
    return true;
  }
}

export function readDrawPortraitEveryTurn(): boolean {
  return readDrawEveryTurn(DRAW_PORTRAIT_STORAGE_KEY);
}

export function readDrawPartnerEveryTurn(): boolean {
  return readDrawEveryTurn(DRAW_PARTNER_STORAGE_KEY);
}

export type AdventureImageStep = "portrait" | "composite";

export interface AdventurePhaseStep {
  step: AdventureImageStep;
  index: number;
  count: number;
}

interface AdventureContextValue {
  runs: AdventureRun[];
  templates: AdventureTemplate[];
  activeRun: AdventureRun | null;
  loading: boolean;
  setupGenerating: boolean;
  streaming: boolean;
  phase: AdventurePhase | null;
  phaseStep: AdventurePhaseStep | null;
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
    inputKind: AdventureInputKind,
    options?: { giftId?: string },
  ) => Promise<void>;
  /** Anlas確認ダイアログ待ちのターン送信(romanceで精密参照ON時のみ) */
  pendingAnlasTurn: {
    input: string;
    inputKind: AdventureInputKind;
    options?: { giftId?: string };
  } | null;
  confirmPendingAnlasTurn: (suppressUntilBrowserClose: boolean) => void;
  cancelPendingAnlasTurn: () => void;
  regenerateImage: (options?: AdventureImageRegenerateOptions) => Promise<void>;
  regenerateChoices: () => Promise<void>;
  /** 指定手番の完了時点まで巻き戻す(以降のターンは削除) */
  rewindRun: (turnNumber: number) => Promise<void>;
  /** 終了済み run をエピローグ(継続プレイ)へ移行する */
  startEpilogue: () => Promise<void>;
  updateSettings: (settings: {
    use_precise_reference: boolean;
    enable_composite_scene: boolean;
    respect_clothing_layers?: boolean;
  }) => Promise<void>;
  clearError: () => void;
}

const AdventureContext = createContext<AdventureContextValue | null>(null);

function parsePhaseStep(
  data: Record<string, unknown>,
): AdventurePhaseStep | null {
  const step = data.step;
  if (step !== "portrait" && step !== "composite") return null;
  return {
    step,
    index: Number(data.step_index ?? 1),
    count: Number(data.step_count ?? 1),
  };
}

export function AdventureProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<AdventureRun[]>([]);
  const [templates, setTemplates] = useState<AdventureTemplate[]>([]);
  const [activeRun, setActiveRun] = useState<AdventureRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [setupGenerating, setSetupGenerating] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [phase, setPhase] = useState<AdventurePhase | null>(null);
  const [phaseStep, setPhaseStep] = useState<AdventurePhaseStep | null>(null);
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

  const [pendingAnlasTurn, setPendingAnlasTurn] = useState<{
    input: string;
    inputKind: AdventureInputKind;
    options?: { giftId?: string };
  } | null>(null);

  // 確認待ちの送信を別の run へ持ち越さない
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeRun.id の変化を検知して保留をクリアするための依存
  useEffect(() => {
    setPendingAnlasTurn(null);
  }, [activeRun?.id]);

  const performSubmitTurn = useCallback(
    async (
      input: string,
      inputKind: AdventureInputKind,
      options?: { giftId?: string },
    ) => {
      if (!activeRun || streaming) return;
      const runId = activeRun.id;
      // 立ち絵の毎ターン生成OFFは、精密参照OFFかつ非合成モードのときだけ効く
      const forcePortrait =
        Boolean(activeRun.use_precise_reference) ||
        Boolean(activeRun.enable_composite_scene);
      const generatePortrait = readDrawPortraitEveryTurn() || forcePortrait;
      const generatePartnerPortrait =
        readDrawPartnerEveryTurn() || forcePortrait;
      setStreaming(true);
      setPhase("narrative");
      setPhaseStep(null);
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
            ...(options?.giftId ? { gift_id: options.giftId } : {}),
            ...(generatePortrait ? {} : { generate_portrait: false }),
            ...(generatePartnerPortrait
              ? {}
              : { generate_partner_portrait: false }),
          },
          (event) => {
            if (event.type === "status") {
              setPhase((event.data.phase as AdventurePhase) ?? null);
              setPhaseStep(parsePhaseStep(event.data));
            } else if (event.type === "narrative_chunk") {
              const chunk = String(event.data.chunk ?? "");
              if (chunk) {
                // narrative_done はstrip済み全文を送るため、蓄積が空の間だけ
                // 先頭空白を除去してストリーム表示との差分をなくす
                setStreamingNarrative((current) =>
                  current ? current + chunk : chunk.replace(/^\s+/, ""),
                );
              }
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
                      // romance の好感度ゲージはターン確定と同時に動かす。
                      // 最終整合はストリーム後の run 全再取得が担う
                      sim: turn.sim ?? current.sim,
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
            } else if (event.type === "partner_image") {
              // romance の攻略対象立ち絵(非合成モードのみ配信される)
              const partnerUrl = normalizeAdventureImageUrl(
                event.data.image_url,
              );
              if (partnerUrl) {
                setActiveRun((current) =>
                  current
                    ? { ...current, partner_portrait_url: partnerUrl }
                    : current,
                );
              }
            } else if (event.type === "background_image") {
              // romance は現在地・時間帯が変わると背景を作り直す
              const backgroundUrl = normalizeAdventureImageUrl(
                event.data.image_url,
              );
              if (backgroundUrl) {
                setActiveRun((current) =>
                  current
                    ? { ...current, background_image_url: backgroundUrl }
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
        setPhaseStep(null);
        setStreamingNarrative("");
        setPendingUserInput(null);
      }
    },
    [activeRun, streaming],
  );

  // 送信経路(選択肢・自由入力・ギフト・属性付与)が分散しても漏れないよう、
  // Anlas確認ガードもここで一元的に挟む
  const submitTurn = useCallback(
    async (
      input: string,
      inputKind: AdventureInputKind,
      options?: { giftId?: string },
    ) => {
      if (!activeRun || streaming) return;
      if (
        activeRun.preset === "romance" &&
        activeRun.use_precise_reference &&
        sessionStorage.getItem(ANLAS_WARN_SUPPRESSED_KEY) !== "true"
      ) {
        setPendingAnlasTurn({ input, inputKind, options });
        return;
      }
      await performSubmitTurn(input, inputKind, options);
    },
    [activeRun, streaming, performSubmitTurn],
  );

  const confirmPendingAnlasTurn = useCallback(
    (suppressUntilBrowserClose: boolean) => {
      if (!pendingAnlasTurn) return;
      if (suppressUntilBrowserClose) {
        sessionStorage.setItem(ANLAS_WARN_SUPPRESSED_KEY, "true");
      }
      const { input, inputKind, options } = pendingAnlasTurn;
      setPendingAnlasTurn(null);
      void performSubmitTurn(input, inputKind, options);
    },
    [pendingAnlasTurn, performSubmitTurn],
  );

  const cancelPendingAnlasTurn = useCallback(() => {
    setPendingAnlasTurn(null);
  }, []);

  const regenerateImage = useCallback(
    async (options?: AdventureImageRegenerateOptions) => {
      if (!activeRun || streaming) return;
      setStreaming(true);
      setPhase("image_generation");
      setPhaseStep(null);
      setError(null);
      try {
        await streamAdventureImage(activeRun.id, options ?? null, (event) => {
          if (event.type === "status") {
            setPhase((event.data.phase as AdventurePhase) ?? null);
            setPhaseStep(parsePhaseStep(event.data));
          } else if (event.type === "image") {
            const imageUrl = normalizeAdventureImageUrl(event.data.image_url);
            if (imageUrl) {
              setActiveRun((current) =>
                current
                  ? {
                      ...current,
                      current_image_url: imageUrl,
                      // タグを省略した再生成ではサーバが組み直すため、
                      // 手元のプロンプト表示は据え置く
                      current_image_prompt:
                        options?.scene_tags !== undefined &&
                        options.player_tags !== undefined
                          ? {
                              scene_tags: options.scene_tags,
                              player_tags: options.player_tags,
                              npc_tags: options.npc_tags ?? [],
                            }
                          : current.current_image_prompt,
                    }
                  : current,
              );
            }
          } else if (event.type === "portrait_image") {
            // target: "portrait" で立ち絵だけを作り直したとき。
            // 該当ターンの失敗表示も同時に解除する
            const portraitUrl = normalizeAdventureImageUrl(
              event.data.image_url,
            );
            const regeneratedTurnId = event.data.turn_id;
            if (portraitUrl) {
              setActiveRun((current) =>
                current
                  ? {
                      ...current,
                      portrait_image_url: portraitUrl,
                      turns: current.turns.map((turn) =>
                        turn.id === regeneratedTurnId
                          ? {
                              ...turn,
                              portrait_image_url: portraitUrl,
                              portrait_status: "completed",
                            }
                          : turn,
                      ),
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
        setPhaseStep(null);
      }
    },
    [activeRun, streaming],
  );

  const regenerateChoices = useCallback(async () => {
    if (!activeRun || streaming || !canActOnRun(activeRun)) return;
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
      respect_clothing_layers?: boolean;
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
                  respect_clothing_layers: updated.respect_clothing_layers,
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

  const rewindRun = useCallback(
    async (turnNumber: number) => {
      if (!activeRun || streaming) return;
      const runId = activeRun.id;
      setError(null);
      try {
        const updated = await rewindAdventureRun(runId, turnNumber);
        // turns 配列が縮むため部分マージせず丸ごと差し替える
        setActiveRun((current) =>
          current && current.id === runId ? updated : current,
        );
        setRuns((current) =>
          current.map((run) =>
            run.id === runId
              ? {
                  ...run,
                  status: updated.status,
                  turn_count: updated.turn_count,
                  remaining_turns: updated.remaining_turns,
                  updated_at: updated.updated_at,
                }
              : run,
          ),
        );
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        throw caught;
      }
    },
    [activeRun, streaming],
  );

  const startEpilogue = useCallback(async () => {
    if (!activeRun || streaming) return;
    const runId = activeRun.id;
    setError(null);
    try {
      const updated = await startAdventureEpilogue(runId);
      setActiveRun((current) =>
        current && current.id === runId ? updated : current,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
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
      phaseStep,
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
      pendingAnlasTurn,
      confirmPendingAnlasTurn,
      cancelPendingAnlasTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
      rewindRun,
      startEpilogue,
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
      phaseStep,
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
      pendingAnlasTurn,
      confirmPendingAnlasTurn,
      cancelPendingAnlasTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
      rewindRun,
      startEpilogue,
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
