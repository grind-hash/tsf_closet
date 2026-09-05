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
  type AdventureSettingsUpdateRequest,
  type AdventureSetup,
  type AdventureSetupRequest,
  type AdventureTalkEntry,
  type AdventureTemplate,
  type AdventureTurn,
  type AdventureTurnOptions,
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
  streamAdventureTalk,
  streamAdventureTurn,
  updateAdventureRealityRules,
  updateAdventureRunSettings,
} from "../apis/adventure";
import {
  type AvatarModel,
  avatarModelFileUrl,
  listAvatarModels,
} from "../apis/avatars";
import {
  isV5ImageModel,
  V5_USAGE_WARN_SUPPRESSED_KEY,
} from "../constants/novelaiImageModels";
import {
  clearLastAdventureRunId,
  readLastAdventureRunId,
  saveLastAdventureRunId,
} from "../utils/adventureLastRun";
import {
  readStorage,
  readStorageFlag,
  writeStorageFlag,
} from "../utils/storage";
import { useSettings } from "./SettingsContext";

export type AdventurePhase = "narrative" | "clue_check" | "image_generation";

// 立ち絵を毎ターン描くかのブラウザ単位設定(主人公/攻略対象で個別)。
// トグルUIは AdventureScreen 側にあり、送信経路(選択肢・自由入力・ギフト・
// 属性付与)が分散しても漏れないよう submitTurn で一元的にリクエストへ反映する
export const DRAW_PORTRAIT_STORAGE_KEY = "adventure_draw_portrait_every_turn";
export const DRAW_PARTNER_STORAGE_KEY = "adventure_draw_partner_every_turn";

// 精密参照ONの画像生成(run開始・romanceのターン送信)はAnlasを消費するため、
// 実行前に確認ダイアログを挟む。抑止はブラウザセッション単位(sessionStorage)
export const ANLAS_WARN_SUPPRESSED_KEY = "adventure_anlas_warn_suppressed";

// V5 利用上限使い切り後の生成はAnlasを消費するため警告する。
// 抑止キーは通常ゲーム側 / Prompt Expander と共有(ブラウザセッション単位)。
// 定数本体は constants/novelaiImageModels.ts にあり、互換のため再エクスポートする
export { V5_USAGE_WARN_SUPPRESSED_KEY };

function readDrawEveryTurn(storageKey: string): boolean {
  return readStorage("local", storageKey) !== "false";
}

export function readDrawPortraitEveryTurn(): boolean {
  return readDrawEveryTurn(DRAW_PORTRAIT_STORAGE_KEY);
}

export function readDrawPartnerEveryTurn(): boolean {
  return readDrawEveryTurn(DRAW_PARTNER_STORAGE_KEY);
}

// 攻略対象(partner)は romance で主人公の次に描かれる工程。捨てると進捗バーが
// 主人公工程に張り付き、対面会話モード(主人公工程なし)では 0% のままになる
export type AdventureImageStep = "portrait" | "partner" | "composite";

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
  pendingUserInput: string | null;
  /** 手番ストリームの本文(narrative_done)が確定したか。ストリーム終了で false に戻る */
  narrativeSettled: boolean;
  error: string | null;
  loadRuns: () => Promise<void>;
  loadTemplates: () => Promise<void>;
  /** 直前に開いた/作成した run の ID（localStorage に永続化。削除・消失時は null） */
  lastRunId: string | null;
  loadRun: (runId: string) => Promise<void>;
  generateSetup: (request: AdventureSetupRequest) => Promise<AdventureSetup>;
  createRun: (request: AdventureCreateRequest) => Promise<AdventureRun>;
  removeRun: (runId: string) => Promise<void>;
  submitTurn: (
    input: string,
    inputKind: AdventureInputKind,
    options?: AdventureTurnOptions,
  ) => Promise<void>;
  /** トークモード(romance)。手番を消費せず攻略対象と会話する */
  talking: boolean;
  /** ストリーミング中の攻略対象の返答(途中経過) */
  talkDraft: string;
  /** 送信済みでまだ talk_log に載っていない自分のメッセージ */
  pendingTalkInput: string | null;
  /** 返答の確定後に攻略対象のエントリを返す(読み上げのトリガに使う)。失敗時は null */
  submitTalk: (text: string) => Promise<AdventureTalkEntry | null>;
  /** Anlas確認ダイアログ待ちのターン送信(romanceで精密参照ON時のみ) */
  pendingAnlasTurn: {
    input: string;
    inputKind: AdventureInputKind;
    options?: AdventureTurnOptions;
  } | null;
  confirmPendingAnlasTurn: (suppressUntilBrowserClose: boolean) => void;
  cancelPendingAnlasTurn: () => void;
  /** V5利用上限使い切り警告の確認待ちターン送信 */
  pendingUsageWarnTurn: {
    input: string;
    inputKind: AdventureInputKind;
    options?: AdventureTurnOptions;
  } | null;
  confirmPendingUsageWarnTurn: (suppressUntilBrowserClose: boolean) => void;
  cancelPendingUsageWarnTurn: () => void;
  regenerateImage: (options?: AdventureImageRegenerateOptions) => Promise<void>;
  regenerateChoices: () => Promise<void>;
  /** 指定手番の完了時点まで巻き戻す(以降のターンは削除) */
  rewindRun: (turnNumber: number) => Promise<void>;
  /** 終了済み run をエピローグ(継続プレイ)へ移行する */
  startEpilogue: () => Promise<void>;
  updateSettings: (settings: AdventureSettingsUpdateRequest) => Promise<void>;
  /** 付与済みの現実改変ルールを丸ごと置き換える(手番は消費しない) */
  updateRealityRules: (rules: string[]) => Promise<void>;
  clearError: () => void;
  /** 登録済みの 3D モデル(VRM)。セットアップと⚙ポップオーバーの選択肢 */
  avatarModels: AvatarModel[];
  refreshAvatarModels: () => Promise<void>;
  /**
   * 対面会話モードの 3D モデルの読込に失敗したか。true の間は立ち絵へ戻し、
   * 手番の攻略対象立ち絵も従来どおり生成する。run 切替でリセット
   */
  companionAvatarFailed: boolean;
  setCompanionAvatarFailed: (failed: boolean) => void;
}

const AdventureContext = createContext<AdventureContextValue | null>(null);
const AdventureStreamingNarrativeContext = createContext<string>("");

function parsePhaseStep(
  data: Record<string, unknown>,
): AdventurePhaseStep | null {
  const step = data.step;
  if (step !== "portrait" && step !== "partner" && step !== "composite") {
    return null;
  }
  return {
    step,
    index: Number(data.step_index ?? 1),
    count: Number(data.step_count ?? 1),
  };
}

export function AdventureProvider({ children }: { children: ReactNode }) {
  // API料金(OpenRouter)の累計加算と、Anlas確認のプロバイダー判定に使う
  const {
    state: settingsState,
    addTotalCost,
    effectiveNovelaiImageModel,
  } = useSettings();
  const imageProvider = settingsState.imageProvider;
  const anlasUsage = settingsState.anlasBalance?.usage ?? null;
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
  const [narrativeSettled, setNarrativeSettled] = useState(false);
  const [talking, setTalking] = useState(false);
  const [talkDraft, setTalkDraft] = useState("");
  const [pendingTalkInput, setPendingTalkInput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 直前に開いた/作成した run。Hub の再開バナーと SideMenu の導線が参照する
  const [lastRunId, setLastRunId] = useState<string | null>(() =>
    readLastAdventureRunId(),
  );

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
      // 開いた run を「直前のシナリオ」として覚える
      saveLastAdventureRunId(runId);
      setLastRunId(runId);
    } catch (caught) {
      // 削除済み等で開けない run を指し続けないよう、一致する保存 ID は消す
      clearLastAdventureRunId(runId);
      setLastRunId((current) => (current === runId ? null : current));
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    } finally {
      setLoading(false);
    }
  }, []);

  const generateSetup = useCallback(
    async (request: AdventureSetupRequest) => {
      setSetupGenerating(true);
      setError(null);
      try {
        const setup = await generateAdventureSetup(request);
        if (setup.cost_usd) {
          addTotalCost(setup.cost_usd);
        }
        return setup;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        throw caught;
      } finally {
        setSetupGenerating(false);
      }
    },
    [addTotalCost],
  );

  const createRun = useCallback(
    async (request: AdventureCreateRequest) => {
      setLoading(true);
      setError(null);
      try {
        const created = await createAdventureRun(request);
        if (created.cost_usd) {
          addTotalCost(created.cost_usd);
        }
        setActiveRun(created);
        setRuns((current) => [created, ...current]);
        saveLastAdventureRunId(created.id);
        setLastRunId(created.id);
        return created;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        throw caught;
      } finally {
        setLoading(false);
      }
    },
    [addTotalCost],
  );

  const removeRun = useCallback(async (runId: string) => {
    setError(null);
    try {
      await deleteAdventureRun(runId);
      setRuns((current) => current.filter((run) => run.id !== runId));
      setActiveRun((current) => (current?.id === runId ? null : current));
      clearLastAdventureRunId(runId);
      setLastRunId((current) => (current === runId ? null : current));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      throw caught;
    }
  }, []);

  const [pendingAnlasTurn, setPendingAnlasTurn] = useState<{
    input: string;
    inputKind: AdventureInputKind;
    options?: AdventureTurnOptions;
  } | null>(null);
  const [pendingUsageWarnTurn, setPendingUsageWarnTurn] = useState<{
    input: string;
    inputKind: AdventureInputKind;
    options?: AdventureTurnOptions;
  } | null>(null);

  const [avatarModels, setAvatarModels] = useState<AvatarModel[]>([]);
  const [companionAvatarFailed, setCompanionAvatarFailed] = useState(false);

  const refreshAvatarModels = useCallback(async () => {
    try {
      setAvatarModels(await listAvatarModels());
    } catch (caught) {
      // 一覧が取れなくてもプレイは続けられる(選択肢が空になるだけ)
      console.warn("3Dモデル一覧の取得に失敗しました", caught);
    }
  }, []);

  useEffect(() => {
    void refreshAvatarModels();
  }, [refreshAvatarModels]);

  // 確認待ちの送信を別の run へ持ち越さない
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeRun.id の変化を検知して保留をクリアするための依存
  useEffect(() => {
    setPendingAnlasTurn(null);
    setPendingUsageWarnTurn(null);
    setTalkDraft("");
    setPendingTalkInput(null);
  }, [activeRun?.id]);

  // 3D モデルの読込失敗は run の切替と割り当ての変更(手動・着替え)でやり直す
  // biome-ignore lint/correctness/useExhaustiveDependencies: run と割り当ての変化を検知して失敗状態を戻すための依存
  useEffect(() => {
    setCompanionAvatarFailed(false);
  }, [activeRun?.id, activeRun?.companion_avatar_id]);

  const performSubmitTurn = useCallback(
    async (
      input: string,
      inputKind: AdventureInputKind,
      options?: AdventureTurnOptions,
    ) => {
      if (!activeRun || streaming || talking) return;
      const runId = activeRun.id;
      // 立ち絵の毎ターン生成OFFは、合成モード・精密参照の有無に関わらず効く
      const generatePortrait = readDrawPortraitEveryTurn();
      // 対面会話モードで 3D モデルを表示中は攻略対象の立ち絵を描き直さない
      // (開幕分はフォールバック用に残る)。読込失敗中は従来どおり描く
      const avatarActive =
        activeRun.preset === "romance" &&
        activeRun.companion_mode &&
        Boolean(activeRun.companion_avatar_id) &&
        !companionAvatarFailed;
      const generatePartnerPortrait =
        readDrawPartnerEveryTurn() && !avatarActive;
      setStreaming(true);
      setPhase("narrative");
      setPhaseStep(null);
      setStreamingNarrative("");
      setPendingUserInput(input);
      setNarrativeSettled(false);
      setError(null);
      try {
        await streamAdventureTurn(
          runId,
          {
            client_turn_id: crypto.randomUUID(),
            user_input: input,
            input_kind: inputKind,
            ...(options?.giftId ? { gift_id: options.giftId } : {}),
            ...(options?.itemAction ? { item_action: options.itemAction } : {}),
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
              // turn 到着まで保持する(先読み読み上げ済みの判定に使う)
              setNarrativeSettled(true);
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
                      // 持ち物もターン確定と同時に更新する(OFF の run は undefined)
                      inventory: turn.inventory ?? current.inventory,
                      // 着替え(衣装差分の切替)は turn 到着と同時にモデルを差し替える。
                      // 未設定(null)は据え置き(解除は設定変更だけが行う)
                      ...(turn.companion_avatar_id &&
                      turn.companion_avatar_id !== current.companion_avatar_id
                        ? {
                            companion_avatar_id: turn.companion_avatar_id,
                            companion_avatar_url: avatarModelFileUrl(
                              turn.companion_avatar_id,
                            ),
                          }
                        : {}),
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
            } else if (event.type === "cost") {
              // OpenRouter利用時のみ配信される。累計はSettingsContextで共有
              const cost = Number(event.data.cost_usd);
              if (Number.isFinite(cost) && cost > 0) {
                addTotalCost(cost);
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
        setNarrativeSettled(false);
      }
    },
    [activeRun, streaming, talking, addTotalCost, companionAvatarFailed],
  );

  // トークモード: 手番・好感度・画像を一切動かさず、talk_log だけを伸ばす。
  // 次の手番の fetchAdventureRun でサーバ側と同期されるため再取得はしない
  const submitTalk = useCallback(
    async (text: string): Promise<AdventureTalkEntry | null> => {
      if (!activeRun || streaming || talking || !canActOnRun(activeRun)) {
        return null;
      }
      const runId = activeRun.id;
      const message = text.trim();
      if (!message) return null;
      setTalking(true);
      setTalkDraft("");
      setPendingTalkInput(message);
      setError(null);
      let partnerEntry: AdventureTalkEntry | null = null;
      try {
        await streamAdventureTalk(runId, { user_input: message }, (event) => {
          if (event.type === "talk_chunk") {
            const chunk = String(event.data.chunk ?? "");
            if (chunk) {
              setTalkDraft((current) =>
                current ? current + chunk : chunk.replace(/^\s+/, ""),
              );
            }
          } else if (event.type === "talk_done") {
            const userEntry = event.data.user_entry as
              | AdventureTalkEntry
              | undefined;
            const partner = event.data.partner_entry as
              | AdventureTalkEntry
              | undefined;
            const entries = [userEntry, partner].filter(
              (entry): entry is AdventureTalkEntry => Boolean(entry?.id),
            );
            partnerEntry = partner?.id ? partner : null;
            setPendingTalkInput(null);
            setTalkDraft("");
            setActiveRun((current) =>
              current && current.id === runId
                ? {
                    ...current,
                    talk_log: [...(current.talk_log ?? []), ...entries],
                  }
                : current,
            );
          } else if (event.type === "cost") {
            const cost = Number(event.data.cost_usd);
            if (Number.isFinite(cost) && cost > 0) {
              addTotalCost(cost);
            }
          } else if (event.type === "error") {
            setError(String(event.data.message ?? "Talk failed"));
          }
        });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        setTalking(false);
        setTalkDraft("");
        setPendingTalkInput(null);
      }
      return partnerEntry;
    },
    [activeRun, streaming, talking, addTotalCost],
  );

  // 送信経路(選択肢・自由入力・ギフト・属性付与)が分散しても漏れないよう、
  // Anlas確認ガードもここで一元的に挟む
  const submitTurn = useCallback(
    async (
      input: string,
      inputKind: AdventureInputKind,
      options?: AdventureTurnOptions,
    ) => {
      if (!activeRun || streaming) return;
      // run 単位のモデル上書きを含めた実効モデルで V5 かを判定する
      const isV5ForActiveRun =
        imageProvider === "novelai" &&
        isV5ImageModel(
          activeRun.image_model_override ?? effectiveNovelaiImageModel,
        );
      // V5 利用上限を使い切った状態での生成はAnlasを消費するため警告する
      const usageExhausted =
        anlasUsage != null &&
        (anlasUsage.percent <= 0 || anlasUsage.isNegative);
      if (
        isV5ForActiveRun &&
        usageExhausted &&
        !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
      ) {
        setPendingUsageWarnTurn({ input, inputKind, options });
        return;
      }
      // Anlasを消費するのはNovelAIプロバイダーの精密参照だけ。
      // OpenRouter/セルフホストでは確認ダイアログを出さない
      // (V5実効時は精密参照が使われないため対象外)
      if (
        imageProvider === "novelai" &&
        !isV5ForActiveRun &&
        activeRun.preset === "romance" &&
        activeRun.use_precise_reference &&
        !readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)
      ) {
        setPendingAnlasTurn({ input, inputKind, options });
        return;
      }
      await performSubmitTurn(input, inputKind, options);
    },
    [
      activeRun,
      streaming,
      performSubmitTurn,
      imageProvider,
      effectiveNovelaiImageModel,
      anlasUsage,
    ],
  );

  const confirmPendingAnlasTurn = useCallback(
    (suppressUntilBrowserClose: boolean) => {
      if (!pendingAnlasTurn) return;
      if (suppressUntilBrowserClose) {
        writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
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

  const confirmPendingUsageWarnTurn = useCallback(
    (suppressUntilBrowserClose: boolean) => {
      if (!pendingUsageWarnTurn) return;
      if (suppressUntilBrowserClose) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      const { input, inputKind, options } = pendingUsageWarnTurn;
      setPendingUsageWarnTurn(null);
      void performSubmitTurn(input, inputKind, options);
    },
    [pendingUsageWarnTurn, performSubmitTurn],
  );

  const cancelPendingUsageWarnTurn = useCallback(() => {
    setPendingUsageWarnTurn(null);
  }, []);

  const regenerateImage = useCallback(
    async (options?: AdventureImageRegenerateOptions) => {
      if (!activeRun || streaming || talking) return;
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
          } else if (event.type === "partner_image") {
            // target: "partner" で攻略対象の立ち絵だけを作り直したとき(対面会話)
            const partnerUrl = normalizeAdventureImageUrl(event.data.image_url);
            const regeneratedTurnId = event.data.turn_id;
            if (partnerUrl) {
              setActiveRun((current) =>
                current
                  ? {
                      ...current,
                      partner_portrait_url: partnerUrl,
                      partner_portrait_status: "generated",
                      // 再取得しないため、据え置きの案内もここで消す
                      turns: current.turns.map((turn) =>
                        turn.id === regeneratedTurnId
                          ? {
                              ...turn,
                              partner_portrait_url: partnerUrl,
                              partner_portrait_status: "generated",
                            }
                          : turn,
                      ),
                    }
                  : current,
              );
            }
          } else if (event.type === "cost") {
            const cost = Number(event.data.cost_usd);
            if (Number.isFinite(cost) && cost > 0) {
              addTotalCost(cost);
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
    [activeRun, streaming, talking, addTotalCost],
  );

  const regenerateChoices = useCallback(async () => {
    if (!activeRun || streaming || !canActOnRun(activeRun)) return;
    const runId = activeRun.id;
    setStreaming(true);
    setPhase("clue_check");
    setError(null);
    try {
      const result = await regenerateAdventureChoices(runId);
      if (result.cost_usd) {
        addTotalCost(result.cost_usd);
      }
      setActiveRun((current) =>
        current && current.id === runId
          ? { ...current, choices: result.choices }
          : current,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setStreaming(false);
      setPhase(null);
    }
  }, [activeRun, streaming, addTotalCost]);

  const updateSettings = useCallback(
    async (settings: AdventureSettingsUpdateRequest) => {
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
                  companion_mode: updated.companion_mode,
                  companion_avatar_id: updated.companion_avatar_id,
                  companion_avatar_url: updated.companion_avatar_url,
                  image_model_override: updated.image_model_override,
                  player_speech_style: updated.player_speech_style,
                  player_speech_custom: updated.player_speech_custom,
                  sim: updated.sim,
                  inventory_enabled: updated.inventory_enabled,
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

  const updateRealityRules = useCallback(
    async (rules: string[]) => {
      if (!activeRun) return;
      const runId = activeRun.id;
      setError(null);
      try {
        const updated = await updateAdventureRealityRules(runId, rules);
        // このエンドポイントが変えるのは reality_rules だけ。run 全体を
        // 差し込むと、ストリームで先に入った画像URL等を古い値へ巻き戻す
        setActiveRun((current) =>
          current && current.id === runId
            ? { ...current, reality_rules: updated.reality_rules ?? [] }
            : current,
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
      lastRunId,
      loading,
      setupGenerating,
      streaming,
      phase,
      phaseStep,
      pendingUserInput,
      narrativeSettled,
      talking,
      talkDraft,
      pendingTalkInput,
      submitTalk,
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
      pendingUsageWarnTurn,
      confirmPendingUsageWarnTurn,
      cancelPendingUsageWarnTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
      updateRealityRules,
      rewindRun,
      startEpilogue,
      clearError: () => setError(null),
      avatarModels,
      refreshAvatarModels,
      companionAvatarFailed,
      setCompanionAvatarFailed,
    }),
    [
      runs,
      templates,
      activeRun,
      lastRunId,
      loading,
      setupGenerating,
      streaming,
      phase,
      phaseStep,
      pendingUserInput,
      narrativeSettled,
      talking,
      talkDraft,
      pendingTalkInput,
      submitTalk,
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
      pendingUsageWarnTurn,
      confirmPendingUsageWarnTurn,
      cancelPendingUsageWarnTurn,
      regenerateImage,
      regenerateChoices,
      updateSettings,
      updateRealityRules,
      rewindRun,
      startEpilogue,
      avatarModels,
      refreshAvatarModels,
      companionAvatarFailed,
    ],
  );

  return (
    <AdventureContext.Provider value={value}>
      <AdventureStreamingNarrativeContext.Provider value={streamingNarrative}>
        {children}
      </AdventureStreamingNarrativeContext.Provider>
    </AdventureContext.Provider>
  );
}

/**
 * ストリーミング中の本文。トークンごとに更新されるため本体の Context から分け、
 * 本文を表示しない消費者（モーダル・持ち物パネル等）が毎トークン再描画されないようにする
 */
export function useAdventureStreamingNarrative(): string {
  return useContext(AdventureStreamingNarrativeContext);
}

export function useAdventure(): AdventureContextValue {
  const context = useContext(AdventureContext);
  if (!context) {
    throw new Error("useAdventure must be used within AdventureProvider");
  }
  return context;
}
