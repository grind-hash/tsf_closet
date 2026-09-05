import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type {
  AdventureBgmKey,
  AdventureInputKind,
  AdventureStatus,
} from "../../apis/adventure";
import { canActOnRun } from "../../apis/adventure";
import { fetchAnlasBalance } from "../../apis/anlas";
import {
  PROTAGONIST_DOCK_STORAGE_KEY,
  REALITY_DECLARATION_PATTERN,
} from "../../constants/adventure";
import {
  type AvatarExpressionKey,
  type AvatarGestureKey,
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "../../constants/companionAvatar";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
import {
  useAdventure,
  useAdventureStreamingNarrative,
} from "../../contexts/AdventureContext";
import { useNotification } from "../../contexts/NotificationContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { useAdventureDrawPreferences } from "../../hooks/useAdventureDrawPreferences";
import { useAdventureFrameNavigation } from "../../hooks/useAdventureFrameNavigation";
import { useAdventureNarration } from "../../hooks/useAdventureNarration";
import { useAdventureSpeechInput } from "../../hooks/useAdventureSpeechInput";
import { useAdventureStagePortraits } from "../../hooks/useAdventureStagePortraits";
import { usePersistedState } from "../../hooks/usePersistedState";
import {
  type TimedProgressSegment,
  useTimedProgress,
} from "../../hooks/useTimedProgress";
import type { AnlasBalance } from "../../types";
import { estimateAdventureAnlas } from "../../utils/adventureAnlasEstimate";
import {
  joinForSpeech,
  partnerLines,
  stripStageDirections,
  stripTalkHeader,
} from "../../utils/adventureDialogue";
import { formatAnlasEstimate } from "../../utils/adventureFormat";
import { frameDaySlot } from "../../utils/adventureFrames";
import { buildAdventureSceneView } from "../../utils/adventureSceneView";
import {
  ADVENTURE_PROGRESS_BUDGET_MS,
  type AdventureTurnImageSettings,
} from "../../utils/adventureTurnTimeEstimate";
import {
  textToVoiceSegments,
  turnVoiceKey,
} from "../../utils/adventureVoiceSegments";
import MainLayout from "../layout/MainLayout";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import AdventureAttributeModal from "./AdventureAttributeModal";
import AdventureFramePreviewModal from "./AdventureFramePreviewModal";
import AdventureGiftShopModal from "./AdventureGiftShopModal";
import AdventureHud, { type AdventureHudPanel } from "./AdventureHud";
import AdventureImagePromptModal from "./AdventureImagePromptModal";
import AdventureImageSettingsPopover from "./AdventureImageSettingsPopover";
import AdventureLogDrawer from "./AdventureLogDrawer";
import AdventureMessageBox, {
  type AdventureActionMode,
} from "./AdventureMessageBox";
import AdventurePromptPreviewModal from "./AdventurePromptPreviewModal";
import AdventureProtagonistDock from "./AdventureProtagonistDock";
import AdventureResultOverlay from "./AdventureResultOverlay";
import AdventureSpeechStyleModal from "./AdventureSpeechStyleModal";
import AdventureStage from "./AdventureStage";

// Adventure のプレイ画面。run の読込・送信・キーボード操作・モーダルの開閉を束ね、
// 描画は HUD / ステージ / メッセージ窓 / ログ / プレビューの各コンポーネントに任せる。

export default function AdventurePlay({ runId }: { runId: string }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const {
    activeRun,
    loading,
    streaming,
    phase,
    phaseStep,
    pendingUserInput,
    narrativeSettled,
    talking,
    submitTalk,
    error,
    loadRun,
    submitTurn,
    pendingAnlasTurn,
    confirmPendingAnlasTurn,
    cancelPendingAnlasTurn,
    pendingUsageWarnTurn,
    confirmPendingUsageWarnTurn,
    cancelPendingUsageWarnTurn,
    regenerateImage,
    updateSettings,
    rewindRun,
    clearError,
    companionAvatarFailed,
    setCompanionAvatarFailed,
  } = useAdventure();
  const streamingNarrative = useAdventureStreamingNarrative();
  const { showNotification } = useNotification();
  const {
    state: settingsState,
    setAnlasBalance: setGlobalAnlasBalance,
    effectiveNovelaiImageModel,
  } = useSettings();
  const respectClothingLayers = settingsState.respectClothingLayers;
  const [input, setInput] = useState("");
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  // romance 専用モーダル(ギフトショップ・属性付与)
  const [giftShopOpen, setGiftShopOpen] = useState(false);
  const [attributeModalOpen, setAttributeModalOpen] = useState(false);
  const [speechModalOpen, setSpeechModalOpen] = useState(false);
  const [imageSettingsOpen, setImageSettingsOpen] = useState(false);
  const [bgmSettingsOpen, setBgmSettingsOpen] = useState(false);
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [messageWindowHidden, setMessageWindowHidden] = useState(false);
  const [hudPanel, setHudPanel] = useState<AdventureHudPanel | null>(null);
  const [protagonistDockOpen, setProtagonistDockOpen] =
    usePersistedState<boolean>(PROTAGONIST_DOCK_STORAGE_KEY, false);
  const {
    drawPortraitEveryTurn,
    setDrawPortraitEveryTurn,
    drawPartnerEveryTurn,
    setDrawPartnerEveryTurn,
  } = useAdventureDrawPreferences();
  // romance の行動パネル: 行動(手番を消費) / トーク(手番を消費しない会話)
  const [actionMode, setActionMode] = useState<AdventureActionMode>("act");
  const [resultDismissed, setResultDismissed] = useState(false);
  const [anlasBalance, setAnlasBalance] = useState<AnlasBalance | null>(null);

  const handleAnlasCancel = useCallback(() => {
    // 自由入力(手入力の現実改変宣言を含む)のキャンセルは入力欄へ戻し、
    // 打ち直しを不要にする
    if (
      pendingAnlasTurn?.inputKind === "free_text" ||
      pendingAnlasTurn?.inputKind === "reality_alter"
    ) {
      setInput(pendingAnlasTurn.input);
    }
    cancelPendingAnlasTurn();
  }, [pendingAnlasTurn, cancelPendingAnlasTurn]);

  const handleUsageWarnCancel = useCallback(() => {
    if (
      pendingUsageWarnTurn?.inputKind === "free_text" ||
      pendingUsageWarnTurn?.inputKind === "reality_alter"
    ) {
      setInput(pendingUsageWarnTurn.input);
    }
    cancelPendingUsageWarnTurn();
  }, [pendingUsageWarnTurn, cancelPendingUsageWarnTurn]);

  useEffect(() => {
    void loadRun(runId).catch(() => navigate("/adventure"));
  }, [loadRun, navigate, runId]);

  // リザルトモーダルの表示制御。エピローグ中の run を開き直しても再表示せず、
  // 「進行中→終了」への遷移(巻き戻し後の再エンディング含む)と、エピローグ中の
  // 逆転(エンディング差し替え)のときだけ改めて表示する
  const prevRunStateRef = useRef<{
    id: string | null;
    status: AdventureStatus | null;
    endingTitle: string | null;
  }>({ id: null, status: null, endingTitle: null });
  useEffect(() => {
    if (!activeRun) return;
    const prev = prevRunStateRef.current;
    if (prev.id !== activeRun.id) {
      setResultDismissed(Boolean(activeRun.epilogue));
    } else if (prev.status === "active" && activeRun.status !== "active") {
      setResultDismissed(false);
    } else if (
      activeRun.epilogue &&
      prev.endingTitle !== null &&
      activeRun.ending_title !== null &&
      prev.endingTitle !== activeRun.ending_title
    ) {
      setResultDismissed(false);
    }
    prevRunStateRef.current = {
      id: activeRun.id,
      status: activeRun.status,
      endingTitle: activeRun.ending_title,
    };
  }, [activeRun]);

  // 精密参照ONのrunではAnlasを消費するため残高を表示する。
  // streamingがfalseへ戻るたび(=各ストリーム完了後)に再取得する。
  // Anlasを消費するのはNovelAIプロバイダーのときだけ
  const usePreciseReference = activeRun?.use_precise_reference ?? false;
  // run 単位のモデル上書きを含めた実効モデルでV5判定する。
  // ギアの表示・精密参照の可否・利用上限表示の出し分けに使う
  const runIsV5 =
    settingsState.imageProvider === "novelai" &&
    isV5ImageModel(
      activeRun?.image_model_override ?? effectiveNovelaiImageModel,
    );
  // V5実効時は毎生成で利用上限が減るため、精密参照OFFでも残高/上限を追跡する
  const anlasApplies =
    (usePreciseReference || runIsV5) &&
    settingsState.imageProvider === "novelai";
  useEffect(() => {
    if (!anlasApplies) {
      setAnlasBalance(null);
      return;
    }
    if (streaming) return;
    let cancelled = false;
    void fetchAnlasBalance().then((balance) => {
      if (!cancelled) {
        setAnlasBalance(balance);
        // 使い切り警告(AdventureContext)が参照するグローバル状態にも反映する
        if (balance) setGlobalAnlasBalance(balance);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [anlasApplies, streaming, setGlobalAnlasBalance]);

  // 衣装レイヤー考慮は Adventure 専用トグルを持たず、設定画面の値を唯一の入力とする。
  // 実行中の run に差分があれば次回生成へ反映されるよう同期する。
  useEffect(() => {
    if (!activeRun) return;
    if (activeRun.respect_clothing_layers === respectClothingLayers) return;
    void updateSettings({
      use_precise_reference: activeRun.use_precise_reference,
      enable_composite_scene: activeRun.enable_composite_scene,
      respect_clothing_layers: respectClothingLayers,
    }).catch(() => undefined);
  }, [activeRun, respectClothingLayers, updateSettings]);

  const {
    frames,
    selectedFrameIndex,
    setSelectedFrameIndex,
    isViewingPast,
    effectiveIndex,
    selectedFrame,
    latestFrame,
    goToFrame,
    lightboxIndex,
    lightboxView,
    setLightboxView,
    lightboxFrame,
    openLightboxFrame,
    closeLightbox,
  } = useAdventureFrameNavigation(activeRun);

  // 表示中フレームのBGMキーと選曲理由。過去フレーム閲覧中はその手番に追随し、
  // 最新表示中は画像未生成ターン(フレーム化されない)も含めて turns を直読みする。
  // BGM切替は SSE の turn イベント(ナラティブ確定)時点で起きる
  const currentBgm = useMemo<{
    key: AdventureBgmKey;
    reason: string | null;
  } | null>(() => {
    if (!activeRun) return null;
    if (selectedFrameIndex !== null) {
      const frame = frames[selectedFrameIndex];
      return {
        key: frame?.bgm ?? "daily",
        reason: frame?.bgmReason ?? null,
      };
    }
    for (let i = activeRun.turns.length - 1; i >= 0; i--) {
      const turn = activeRun.turns[i];
      if (turn?.bgm) {
        return { key: turn.bgm, reason: turn.bgm_reason ?? null };
      }
    }
    // 旧runはキー欠落のため daily に倒す
    return {
      key: activeRun.opening_bgm ?? "daily",
      reason: activeRun.opening_bgm_reason ?? null,
    };
  }, [activeRun, frames, selectedFrameIndex]);
  const {
    muted: bgmMuted,
    volume: bgmVolume,
    autoplayBlocked: bgmAutoplayBlocked,
    setMuted: setBgmMuted,
    setVolume: setBgmVolume,
    setDucked: setBgmDucked,
  } = useAdventureBgm(currentBgm?.key ?? null);

  // run が変わったら行動モードへ戻す
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeRun.id の変化を検知して行動モードへ戻すための依存
  useEffect(() => {
    setActionMode("act");
  }, [activeRun?.id]);

  const isRomancePreset = activeRun?.preset === "romance";
  // 対面会話モード: 主人公立ち絵と合成シーンの工程は走らない
  const companionActive = isRomancePreset && Boolean(activeRun?.companion_mode);
  // 対面会話モードで 3D モデルを表示中は攻略対象の立ち絵を毎ターン描かない
  const avatarActive =
    companionActive &&
    Boolean(activeRun?.companion_avatar_url) &&
    !companionAvatarFailed;
  // 3D モデル表示中はステージを覆わない(モデルが暗く隠れるため)。進捗は本文の
  // カーソルと行動パネルの進捗行で示し、読み上げ可能なら本文の確定
  // (narrative_done)で判定を待たずに喋り始める
  const quietStage = avatarActive;

  // セリフ読み上げ(AivisSpeech)。設定画面の TTS が有効なときだけ動く
  const voice = useAdventureNarration({
    available: settingsState.ttsEnabled,
    speakerId:
      settingsState.ttsStyleId?.trim() ||
      settingsState.ttsSpeakerId?.trim() ||
      null,
    engineDir: settingsState.ttsEngineDir,
    useGpu: settingsState.ttsUseGpu,
    activeRun,
    streamingNarrative,
    narrativeSettled,
    pendingUserInput,
    earlyVoiceAllowed: quietStage,
  });
  const voiceCanSpeak = voice.canSpeak;
  const voicePlaying = voice.status === "playing";
  useEffect(() => {
    setBgmDucked(voicePlaying);
  }, [voicePlaying, setBgmDucked]);
  // 身振りキーのラッチ。逐次給餌でキューが一時枯渇すると currentKey が
  // key→null→key と揺れるため、ストリーム中は最後の非 null キーを保持して
  // 同じ身振りの再再生を防ぐ(値の設定は avatarGestureKey の算出直後)
  const latchedGestureKeyRef = useRef<string | null>(null);

  const submit = useCallback(
    (
      value: string,
      kind: AdventureInputKind,
      options?: { giftId?: string },
    ) => {
      const trimmed = value.trim();
      if (!trimmed || streaming || talking || !canActOnRun(activeRun)) return;
      setInput("");
      // 「現実改変：〜」はサーバ側でも検出されるが、送信種別も合わせておく
      const effectiveKind =
        kind === "free_text" && REALITY_DECLARATION_PATTERN.test(trimmed)
          ? "reality_alter"
          : kind;
      void submitTurn(trimmed, effectiveKind, options);
    },
    [activeRun, streaming, talking, submitTurn],
  );

  // トークモードの送信。手番は消費しない
  const submitTalkMessage = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed || streaming || talking || !canActOnRun(activeRun)) return;
      setInput("");
      void submitTalk(trimmed);
    },
    [activeRun, streaming, talking, submitTalk],
  );

  // 音声入力(トークモード)
  const talkModeActive = Boolean(activeRun?.sim) && actionMode === "talk";
  const speechInput = useAdventureSpeechInput({
    language: i18n.language ?? "",
    input,
    setInput,
    onSubmit: submitTalkMessage,
    active: talkModeActive,
    voiceStatus: voice.status,
    stopVoice: voice.stop,
  });

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const inField = Boolean(target?.closest("input, textarea, select"));
      if (event.key === "Escape") {
        // 常設の自由入力欄からショートカット層へ戻る唯一の手段
        if (inField) {
          target?.blur();
          return;
        }
        if (pendingAnlasTurn) {
          handleAnlasCancel();
          return;
        }
        setLogOpen(false);
        setImageSettingsOpen(false);
        setBgmSettingsOpen(false);
        setHudPanel(null);
        setMessageWindowHidden(false);
        return;
      }
      if (inField) return;
      if (event.key === "l" || event.key === "L") {
        setLogOpen((current) => !current);
        return;
      }
      if (event.key === "h" || event.key === "H") {
        setMessageWindowHidden((current) => !current);
        return;
      }
      if (event.key === "m" || event.key === "M") {
        setBgmMuted(!bgmMuted);
        return;
      }
      // Anlas確認ダイアログ表示中は数字キー送信で保留中の送信を上書きしない。
      // 過去フレーム閲覧中は行動UIを非表示にしているため送信もしない。
      // トークモード中は選択肢を出していないため数字キーも効かせない
      if (
        logOpen ||
        pendingAnlasTurn ||
        selectedFrameIndex !== null ||
        actionMode === "talk"
      ) {
        return;
      }
      const choice = (activeRun?.choices ?? []).filter((item) =>
        item.label.trim(),
      )[Number(event.key) - 1];
      if (choice) submit(choice.label, "choice");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [
    activeRun?.choices,
    logOpen,
    submit,
    pendingAnlasTurn,
    handleAnlasCancel,
    selectedFrameIndex,
    bgmMuted,
    setBgmMuted,
    actionMode,
  ]);

  const {
    stagePortraitUrl,
    stagePartnerUrl,
    currentPortraitUrl,
    currentPartnerDockUrl,
  } = useAdventureStagePortraits(activeRun, frames, selectedFrameIndex);
  const toggleProtagonistDock = useCallback(() => {
    setProtagonistDockOpen((current) => !current);
  }, [setProtagonistDockOpen]);

  // 実進捗が取れないため、サブ工程statusと見なし所要時間で進捗バーを描く。
  // narrativeフェーズはテキスト自体が進捗になるため対象外(スピナー維持)。
  const enableCompositeScene = activeRun?.enable_composite_scene ?? false;
  const progressSegments = useMemo<TimedProgressSegment[] | null>(() => {
    if (!streaming || phase === null || phase === "narrative") return null;
    if (pendingUserInput !== null) {
      const segments: TimedProgressSegment[] = [
        {
          key: "clue_check",
          budgetMs: ADVENTURE_PROGRESS_BUDGET_MS.clue_check,
        },
      ];
      // 立ち絵の毎ターン生成OFFの間はバックエンドが該当の生成をスキップするため
      // 工程表示も揃える。順序は主人公→攻略対象→合成シーンの直列生成に対応する
      if (drawPortraitEveryTurn && !companionActive) {
        segments.push({
          key: "portrait",
          budgetMs: ADVENTURE_PROGRESS_BUDGET_MS.portrait,
        });
      }
      if (isRomancePreset && drawPartnerEveryTurn && !avatarActive) {
        segments.push({
          key: "partner",
          budgetMs: ADVENTURE_PROGRESS_BUDGET_MS.partner,
        });
      }
      if (enableCompositeScene && !companionActive) {
        segments.push({
          key: "composite",
          budgetMs: ADVENTURE_PROGRESS_BUDGET_MS.composite,
        });
      }
      return segments;
    }
    if (phase === "image_generation") {
      return [
        {
          key: "image_single",
          budgetMs: ADVENTURE_PROGRESS_BUDGET_MS.image_single,
        },
      ];
    }
    return null;
  }, [
    streaming,
    phase,
    pendingUserInput,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn,
    enableCompositeScene,
    isRomancePreset,
    companionActive,
    avatarActive,
  ]);
  const progressActiveKey = useMemo(() => {
    if (!progressSegments) return null;
    if (pendingUserInput !== null) {
      if (phase === "clue_check") return "clue_check";
      if (phase === "image_generation") {
        return phaseStep?.step ?? (companionActive ? "partner" : "portrait");
      }
      return null;
    }
    return phase === "image_generation" ? "image_single" : null;
  }, [progressSegments, pendingUserInput, phase, phaseStep, companionActive]);
  const stageProgress = useTimedProgress(progressSegments, progressActiveKey);

  if (loading || !activeRun || activeRun.id !== runId) {
    return (
      <MainLayout>
        <div className="adventure-loading">{t("adventure.loading")}</div>
      </MainLayout>
    );
  }

  const isStageLoading = streaming && phase !== null;
  // quietStage(3D モデル表示中)ではステージのオーバーレイと減光を出さず、
  // 判定・画像工程の進捗は行動パネルに出す(本文が流れている間はカーソルだけ)
  const showStageOverlay = isStageLoading && !quietStage;
  const controlsProgressVisible =
    quietStage &&
    isStageLoading &&
    (pendingUserInput === null || narrativeSettled);
  const phaseLabel = phaseStep
    ? t(`adventure.phaseStep.${phaseStep.step}`)
    : t(`adventure.phase.${phase ?? "narrative"}`);
  // 対面会話モード(romance): 背景の上に攻略対象の立ち絵だけを置く
  const isCompanion =
    activeRun.preset === "romance" && Boolean(activeRun.companion_mode);
  const isCompositeMode = activeRun.enable_composite_scene && !isCompanion;
  // 生成時間の見積もりと「テキストのみ」告知は同じ設定から導く
  const playImageSettings: AdventureTurnImageSettings = {
    preset: activeRun.preset,
    enableCompositeScene: activeRun.enable_composite_scene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn: drawPartnerEveryTurn && !avatarActive,
    companionMode: isCompanion,
  };
  const scene = buildAdventureSceneView({
    activeRun,
    selectedFrame,
    latestFrame,
    isViewingPast,
    streamingNarrative,
    pendingUserInput,
    actionMode,
    t,
  });
  const {
    sim,
    partnerName,
    talkMode,
    lastPartnerTalk,
    activeNarrative,
    isStreamingNarrative,
  } = scene;
  // 攻略対象の立ち絵を据え置いた手番の案内。立ち絵をステージに出している
  // (合成でなく 3D モデルも非表示)ときだけ表示中フレームに追随し、
  // 新しい手番のストリーム中は前手番の案内を出さない
  const partnerPortraitNote =
    isRomancePreset &&
    !isCompositeMode &&
    !avatarActive &&
    !streaming &&
    selectedFrame !== undefined &&
    selectedFrame.turnNumber > 0 &&
    selectedFrame.partnerInherited
      ? selectedFrame
      : null;
  // 対面会話モードの背景は生成済みの1枚だけ。無ければ無地のステージにし、
  // 主人公の開始画像(current_image_url)を背景に敷かない
  const backgroundUrl = isCompanion
    ? (activeRun.background_image_url ?? null)
    : (activeRun.background_image_url ?? activeRun.current_image_url);
  const displayedImageUrl = isCompanion
    ? isViewingPast
      ? (selectedFrame?.backgroundUrl ?? backgroundUrl)
      : backgroundUrl
    : isCompositeMode
      ? isViewingPast
        ? (selectedFrame?.imageUrl ?? activeRun.current_image_url)
        : activeRun.current_image_url
      : backgroundUrl;

  const turnRatio =
    activeRun.max_turns > 0
      ? Math.round((activeRun.remaining_turns / activeRun.max_turns) * 100)
      : 0;
  // HUD は「今ステージに映っている場面の枠」を出す。過去フレーム閲覧中は
  // そのフレームの枠に追従させ、ライトボックスの表示と一致させる。
  // 次に行動する枠(sim.day/slot)は tooltip 側で補う。
  const stageFrame = isViewingPast ? selectedFrame : latestFrame;
  const stageDaySlot = frameDaySlot(stageFrame) ?? {
    day: sim?.day ?? 1,
    slot: sim?.slot ?? "day",
  };
  const stagePortraitFailed =
    !isCompanion && stageFrame?.portraitStatus === "failed";
  // 🔊 の再読み上げ対象。トーク中は最新の返答、それ以外は表示中フレームのセリフ
  const voiceReplayText =
    talkMode && lastPartnerTalk
      ? stripStageDirections(stripTalkHeader(lastPartnerTalk.text))
      : joinForSpeech(partnerLines(activeNarrative, partnerName));
  const frameReplayKey = `frame:${selectedFrame?.key ?? "latest"}`;
  // 本文ストリーム中の手番は先読み(読み上げ(0))と同じキーにし、🔊 が先読みの
  // 再生中表示と停止を兼ねるようにする
  const voiceReplayKey =
    talkMode && lastPartnerTalk
      ? `talk:${lastPartnerTalk.id}`
      : isStreamingNarrative
        ? turnVoiceKey(activeRun.id, activeRun.turn_count + 1)
        : frameReplayKey;
  const voiceReplayActive =
    voice.currentKey === voiceReplayKey && voice.status !== "idle";
  const toggleVoiceReplay = () => {
    if (voiceReplayActive) {
      voice.stop();
      return;
    }
    voice.speakSegments(
      textToVoiceSegments(voiceReplayText, voiceReplayKey),
      voiceReplayKey,
    );
  };
  // 3D モデルの表情・身振り。トーク中は最新の返答、それ以外は表示中フレームの値
  const avatarExpression: AvatarExpressionKey | null =
    talkMode && lastPartnerTalk
      ? normalizeAvatarExpression(lastPartnerTalk.expression)
      : (selectedFrame?.partnerExpression ?? null);
  const avatarGesture: AvatarGestureKey | null =
    talkMode && lastPartnerTalk
      ? normalizeAvatarGesture(lastPartnerTalk.gesture)
      : (selectedFrame?.partnerGesture ?? null);
  // 身振りの再生トリガ。読み上げ可能なら声の開始(到着・先読み・🔊再生)に合わせ、
  // 読み上げ不可ならセリフ/フレームの切り替わりで再生する。
  // 先読み中は表示中フレームがまだ前の手番なので、手番のキーはフレームの手番と
  // 一致した時点(turn 到着でフレームが増えたとき)に初めて再生し、前の手番の
  // 身振りを誤って再生しない
  const frameTurnVoiceKey = selectedFrame
    ? turnVoiceKey(activeRun.id, selectedFrame.turnNumber)
    : null;
  const voiceBusy = voice.status === "loading" || voice.status === "playing";
  const avatarGestureKey = voiceCanSpeak
    ? voiceBusy && voice.currentKey
      ? voice.currentKey.startsWith("turn:") &&
        voice.currentKey !== frameTurnVoiceKey
        ? null
        : voice.currentKey
      : null
    : talkMode && lastPartnerTalk
      ? `talk:${lastPartnerTalk.id}`
      : frameReplayKey;
  // ストリーム中の一時枯渇(key→null→key)で同じ身振りが再再生されないよう、
  // ストリーム中だけ最後の非 null キーを効かせる。ストリーム外では素通しにし、
  // 🔊 での再読み上げ(null→同じキー)による再再生は従来どおり残す
  if (avatarGestureKey !== null) {
    latchedGestureKeyRef.current = avatarGestureKey;
  } else if (!streaming) {
    latchedGestureKeyRef.current = null;
  }
  const effectiveAvatarGestureKey =
    avatarGestureKey ?? (streaming ? latchedGestureKeyRef.current : null);
  const avatarUrl = activeRun.companion_avatar_url ?? null;
  const showAvatar =
    isCompanion && Boolean(avatarUrl) && !companionAvatarFailed;
  // CompanionAvatarStage は onError を ref で持つため、関数の同一性は不要
  const handleAvatarError = (caught: unknown) => {
    console.warn("3Dモデルの読込に失敗しました", caught);
    setCompanionAvatarFailed(true);
    showNotification(
      "warning",
      t("adventure.avatar.loadFailedTitle"),
      t("adventure.avatar.loadFailed"),
    );
  };
  // 進行中に加え、終了後でもエピローグ移行済みなら操作パネルを出す
  const canAct = canActOnRun(activeRun);
  const isEpilogue = Boolean(activeRun.epilogue);
  // 表示中フレームがエピローグ期か(HUD の Day 表示切替に使う)。
  // 最新表示中は run 全体の状態に従う(移行直後はエンド前のフレームが最新のため)
  const stageEpilogue = isViewingPast
    ? Boolean(selectedFrame?.sim?.epilogue)
    : isEpilogue;
  // 巻き戻しは「選んだ手番の結果を残し、それ以降を削除」する。
  // 手番0(開幕)へは開幕スナップショットを持つ run だけ戻れる
  const rewindTarget = isViewingPast ? selectedFrame : undefined;
  const canRewindHere = Boolean(
    rewindTarget &&
      rewindTarget.turnNumber < activeRun.turn_count &&
      (rewindTarget.turnNumber > 0 || activeRun.can_rewind_to_opening) &&
      !streaming,
  );
  const requestRewind = (turnNumber: number) => {
    if (streaming) return;
    const removed = activeRun.turn_count - turnNumber;
    const confirmed = window.confirm(
      t("adventure.turnStrip.rewindConfirm", {
        turn: turnNumber + 1,
        count: removed,
      }),
    );
    if (!confirmed) return;
    setSelectedFrameIndex(null);
    closeLightbox();
    void rewindRun(turnNumber);
  };

  return (
    <MainLayout>
      <div className={`adventure-play${sim ? " adventure-play--romance" : ""}`}>
        {error && (
          <button
            type="button"
            className="adventure-error"
            onClick={clearError}
          >
            {error}
          </button>
        )}

        <div className="adventure-play__body">
          <AdventureHud
            scene={scene}
            hudPanel={hudPanel}
            onToggleHudPanel={(panel) =>
              setHudPanel((current) => (current === panel ? null : panel))
            }
            onCloseHudPanel={() => setHudPanel(null)}
            currentBgm={currentBgm}
            stageDaySlot={stageDaySlot}
            stageEpilogue={stageEpilogue}
            isEpilogue={isEpilogue}
            isCompanion={isCompanion}
            turnRatio={turnRatio}
            anlasBalance={anlasBalance}
            runIsV5={runIsV5}
            viewingPast={isViewingPast}
            protagonistDockOpen={protagonistDockOpen}
            protagonistThumbUrl={currentPortraitUrl}
            onToggleProtagonistDock={toggleProtagonistDock}
            onOpenSpeechStyle={() => setSpeechModalOpen(true)}
            onOpenAttributes={() => setAttributeModalOpen(true)}
          />

          {/*
            登場人物と主人公ドックは同じ左レールに積む。別々の絶対配置にすると
            ドックの高さ次第で重なるため、レール内で上下に振り分ける。
          */}
          <div className="adventure-left-rail" aria-hidden={false}>
            {scene.cast.length > 0 && (
              <ul className="adventure-cast" aria-label={t("adventure.cast")}>
                {scene.cast.map((member) => (
                  <li key={member.name}>
                    <strong>{member.name}</strong>
                    {member.action && <span>{member.action}</span>}
                  </li>
                ))}
              </ul>
            )}
            {protagonistDockOpen && (
              <AdventureProtagonistDock
                onClose={toggleProtagonistDock}
                portraitUrl={currentPortraitUrl}
                partnerUrl={currentPartnerDockUrl}
                partnerClothing={scene.partnerClothing}
                framesAvailable={frames.length > 0}
                onOpenPortrait={() =>
                  openLightboxFrame(frames.length - 1, "portrait")
                }
                onOpenPartner={() =>
                  openLightboxFrame(frames.length - 1, "partner")
                }
              />
            )}
          </div>
          <AdventureStage
            imageUrl={displayedImageUrl}
            portraitUrl={stagePortraitUrl}
            partnerUrl={stagePartnerUrl}
            isCompositeMode={isCompositeMode}
            isCompanion={isCompanion}
            avatar={{
              show: showAvatar,
              url: avatarUrl,
              expression: avatarExpression,
              gesture: avatarGesture,
              gestureKey: effectiveAvatarGestureKey,
              getVoiceLevel: voice.getLevel,
              getVisemeFrame: voice.getMouthFrame,
              onError: handleAvatarError,
            }}
            showOverlay={showStageOverlay}
            isStageLoading={isStageLoading}
            progressRatio={
              progressSegments && progressActiveKey ? stageProgress : null
            }
            phaseLabel={phaseLabel}
            viewingPast={isViewingPast}
            onBackToLatest={() => setSelectedFrameIndex(null)}
            canRewindHere={canRewindHere}
            onRewind={() => {
              if (rewindTarget) requestRewind(rewindTarget.turnNumber);
            }}
            portraitFailed={stagePortraitFailed}
            lightboxDisabled={frames.length === 0}
            onOpenLightbox={() => openLightboxFrame(effectiveIndex)}
            onRegenerate={() => {
              // 対面会話モードでは合成シーンを使わないため、
              // 攻略対象の立ち絵だけを描き直す
              if (isCompanion) {
                void regenerateImage({
                  redraw_from_reference: true,
                  target: "partner",
                });
                return;
              }
              setPromptModalOpen(true);
            }}
            imageSettingsOpen={imageSettingsOpen}
            onToggleImageSettings={() => {
              setBgmSettingsOpen(false);
              setImageSettingsOpen((current) => !current);
            }}
            bgmControl={{
              muted: bgmMuted,
              volume: bgmVolume,
              autoplayBlocked: bgmAutoplayBlocked,
              open: bgmSettingsOpen,
              onToggleOpen: () => {
                setImageSettingsOpen(false);
                setBgmSettingsOpen((current) => !current);
              },
              onMutedChange: setBgmMuted,
              onVolumeChange: setBgmVolume,
              voice: {
                available: settingsState.ttsEnabled,
                enabled: voice.enabled,
                volume: voice.volume,
                speed: voice.speed,
                status: voice.status,
                onEnabledChange: voice.setEnabled,
                onVolumeChange: voice.setVolume,
                onSpeedChange: voice.setSpeed,
                onStop: voice.stop,
              },
            }}
          >
            <AdventureImageSettingsPopover
              imageSettings={playImageSettings}
              runIsV5={runIsV5}
              isCompanion={isCompanion}
              drawPortraitEveryTurn={drawPortraitEveryTurn}
              onDrawPortraitEveryTurnChange={setDrawPortraitEveryTurn}
              drawPartnerEveryTurn={drawPartnerEveryTurn}
              onDrawPartnerEveryTurnChange={setDrawPartnerEveryTurn}
              onOpenPromptPreview={() => {
                setImageSettingsOpen(false);
                setPromptPreviewOpen(true);
              }}
            />
          </AdventureStage>

          {messageWindowHidden && (
            <button
              type="button"
              className={`adventure-window-restore${
                sim ? " adventure-window-restore--romance" : ""
              }`}
              onClick={() => setMessageWindowHidden(false)}
              title={t("adventure.window.showHint")}
            >
              {t("adventure.window.show")}
            </button>
          )}

          <AdventureMessageBox
            scene={scene}
            hidden={messageWindowHidden}
            onHide={() => setMessageWindowHidden(true)}
            onOpenLog={() => setLogOpen(true)}
            voiceReplay={{
              canSpeak: voice.canSpeak,
              text: voiceReplayText,
              active: voiceReplayActive,
              onToggle: toggleVoiceReplay,
            }}
            partnerPortraitNote={partnerPortraitNote}
            isStageLoading={isStageLoading}
            quietStage={quietStage}
            controlsProgressVisible={controlsProgressVisible}
            phaseLabel={phaseLabel}
            viewingPast={isViewingPast}
            canAct={canAct}
            actionMode={actionMode}
            onActionModeChange={setActionMode}
            input={input}
            onInputChange={setInput}
            onSubmit={submit}
            onSubmitTalk={submitTalkMessage}
            speech={{
              supported: speechInput.supported,
              listening: speechInput.listening,
              autoSend: speechInput.prefs.autoSend,
              error: speechInput.error,
              onToggleListening: () => {
                if (speechInput.listening) {
                  speechInput.stopListening();
                  return;
                }
                speechInput.startListening();
              },
              onToggleAutoSend: speechInput.toggleAutoSend,
            }}
            onOpenGiftShop={() => setGiftShopOpen(true)}
            onOpenAttributes={() => setAttributeModalOpen(true)}
          />
        </div>
      </div>

      <AdventureResultOverlay
        dismissed={resultDismissed}
        onDismiss={() => setResultDismissed(true)}
        onReadLog={() => {
          setResultDismissed(true);
          setLogOpen(true);
        }}
        isCompositeMode={isCompositeMode}
        isEpilogue={isEpilogue}
        completedMilestones={scene.completedMilestones}
      />

      <AdventureLogDrawer
        open={logOpen}
        onClose={() => setLogOpen(false)}
        frames={frames}
        selectedFrameIndex={selectedFrameIndex}
        onGoToFrame={goToFrame}
      />

      <AdventureFramePreviewModal
        frames={frames}
        lightboxIndex={lightboxIndex}
        lightboxFrame={lightboxFrame}
        view={lightboxView}
        onViewChange={setLightboxView}
        onNavigate={(index) => openLightboxFrame(index)}
        onClose={closeLightbox}
        onRewind={requestRewind}
        sim={sim}
        isCompanion={isCompanion}
      />

      <AdventurePromptPreviewModal
        isOpen={promptPreviewOpen}
        onClose={() => setPromptPreviewOpen(false)}
      />

      <AdventureImagePromptModal
        isOpen={promptModalOpen}
        prompt={activeRun.current_image_prompt}
        onClose={() => setPromptModalOpen(false)}
        onSubmit={(options) => {
          setPromptModalOpen(false);
          void regenerateImage(options);
        }}
      />

      <AdventureGiftShopModal
        isOpen={giftShopOpen}
        onClose={() => setGiftShopOpen(false)}
      />

      <AdventureAttributeModal
        isOpen={attributeModalOpen}
        onClose={() => setAttributeModalOpen(false)}
      />

      <AdventureSpeechStyleModal
        isOpen={speechModalOpen}
        onClose={() => setSpeechModalOpen(false)}
      />

      {/* Anlas cost confirmation dialog (romance with precise references) */}
      <AnlasConfirmDialog
        open={pendingAnlasTurn !== null}
        body={t("adventure.anlasWarnBody", {
          estimate: formatAnlasEstimate(
            t,
            estimateAdventureAnlas({
              kind: "turn",
              preset: activeRun?.preset ?? "romance",
              enableCompositeScene: activeRun?.enable_composite_scene ?? false,
            }),
          ),
        })}
        onConfirm={confirmPendingAnlasTurn}
        onCancel={handleAnlasCancel}
      />

      {/* V5 利用上限使い切り警告ダイアログ */}
      <AnlasConfirmDialog
        open={pendingUsageWarnTurn !== null}
        body={t("adventure.v5UsageExhaustedBody")}
        onConfirm={confirmPendingUsageWarnTurn}
        onCancel={handleUsageWarnCancel}
      />
    </MainLayout>
  );
}
