import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type {
  AdventureNarrationVoice,
  AdventurePreset,
  AdventureRun,
  AdventureSpeechStyle,
} from "../../apis/adventure";
import { canActOnRun } from "../../apis/adventure";
import { fetchGallerySessions } from "../../apis/gallery";
import { fetchPromptExpanderEntry } from "../../apis/promptExpander";
import {
  COMPANION_DEFAULT_TURNS,
  COMPANION_TURN_OPTIONS,
  clampMaxTurns,
  DEFAULT_MAX_TURNS,
  DEFAULT_NARRATION_PRONOUN,
  DEFAULT_SPEECH_STYLE,
  MAX_MAX_TURNS,
  MIN_MAX_TURNS,
  NARRATION_PRONOUN_MAX_LENGTH,
  NARRATION_PRONOUN_SUGGESTIONS,
  NARRATION_VOICES,
  PARTNER_SPEECH_STYLE_MAX_LENGTH,
  PRESETS,
  ROMANCE_DAY_OPTIONS,
  ROMANCE_DEFAULT_DAYS,
  ROMANCE_DEFAULT_PLAYER_ID,
  ROMANCE_MAX_DAYS,
  ROMANCE_MIN_DAYS,
  ROMANCE_PLAYER_NAME_MAX_LENGTH,
  ROMANCE_PLAYER_SESSION_VALUE,
  RUN_FILTERS,
  type RunFilter,
  SCENARIO_CONSTRAINTS_MAX_ITEMS,
  SCENARIO_CONSTRAINTS_MAX_LENGTH,
  SETUP_PREFS_STORAGE_KEY,
  SPEECH_CUSTOM_MAX_LENGTH,
  SPEECH_STYLES,
} from "../../constants/adventure";
import {
  isAdventureImageModelValue,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import {
  ANLAS_WARN_SUPPRESSED_KEY,
  useAdventure,
} from "../../contexts/AdventureContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureDrawPreferences } from "../../hooks/useAdventureDrawPreferences";
import { ROUTES } from "../../routes";
import type { Character, GallerySession } from "../../types";
import { estimateAdventureAnlas } from "../../utils/adventureAnlasEstimate";
import { formatAnlasEstimate, mediaUrl } from "../../utils/adventureFormat";
import {
  type AdventureSetupPrefs,
  normalizeNarrationPronoun,
  normalizeNarrationVoice,
  normalizeSpeechCustom,
  normalizeSpeechStyle,
  readSetupPrefs,
} from "../../utils/adventureSetupPrefs";
import { API_BASE } from "../../utils/api";
import {
  readStorageFlag,
  writeStorage,
  writeStorageFlag,
} from "../../utils/storage";
import MainLayout from "../layout/MainLayout";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import {
  AvatarModelOptions,
  AvatarWardrobeHint,
} from "./AdventureAvatarOptions";
import {
  AdventureImageModelPicker,
  AdventureToggleRow,
  AdventureTurnEstimate,
} from "./AdventureImageOptionRows";
import AdventureScenarioPickerModal from "./AdventureScenarioPickerModal";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
  selectionFromPromptExpanderEntry,
  selectionFromSession,
} from "./AdventureSessionPickerModal";

// Adventure のセットアップ画面（開始素材・シナリオ・オプションの選択と保存済み Run の一覧）。

// 開始セッション/主人公セッションの選択中サマリ。未選択時は選択ボタンだけを出す
function SourceSelectionSummary({
  selection,
  disabled,
  onOpenPicker,
}: {
  selection: AdventureSourceSelection | null;
  disabled: boolean;
  onOpenPicker: () => void;
}) {
  const { t } = useTranslation();
  if (!selection) {
    return (
      <button
        type="button"
        className="adventure-source-summary__change"
        disabled={disabled}
        onClick={onOpenPicker}
      >
        {t("adventure.sourcePicker.select")}
      </button>
    );
  }
  // Prompt Expander 由来はキャラ名を持たないため、出どころのラベルを主見出しにする
  const name =
    selection.origin === "prompt_expander"
      ? t("adventure.sourcePicker.promptExpanderOrigin")
      : (selection.characterName ?? t("adventure.unnamedCharacter"));
  const state = selection.pointLabel ?? t("adventure.currentState");
  return (
    <div
      className="adventure-source-summary"
      role="group"
      aria-label={t("adventure.selectedSourceSummary", { name, state })}
    >
      <span className="adventure-source-summary__thumb">
        <img src={mediaUrl(selection.thumbnailUrl)} alt="" />
      </span>
      <span className="adventure-source-summary__text">
        <strong>{name}</strong>
        <span>{state}</span>
      </span>
      <button
        type="button"
        className="adventure-source-summary__change"
        disabled={disabled}
        onClick={onOpenPicker}
      >
        {t("adventure.sourcePicker.change")}
      </button>
    </div>
  );
}

// 制約テキストエリア(1行1件)を配列へ。生成リクエストと作成リクエストで共用する
function splitConstraintLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

// 保存済みシナリオ一覧の1行。Hub 上部の「中断したシナリオを再開」バナーでも
// 同じ体裁で使うため切り出す(バナーでは削除ボタンを出さない)
function AdventureRunRow({
  run,
  onResume,
  onDelete,
}: {
  run: AdventureRun;
  onResume: () => void;
  onDelete?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <article className="adventure-run-item">
      <img src={run.current_image_url} alt={run.title} />
      <div>
        <div className="adventure-run-item__title-row">
          <strong>{run.title}</strong>
          <span
            className={`adventure-run-badge adventure-run-badge--${run.status}`}
          >
            {t(`adventure.status.${run.status}`)}
          </span>
        </div>
        <p>{run.objective}</p>
        <div className="adventure-run-progress">
          <span className="adventure-run-progress__bar">
            <span
              style={{
                width: `${Math.min(100, (run.turn_count / run.max_turns) * 100)}%`,
              }}
            />
          </span>
          <span className="adventure-run-progress__label">
            {run.turn_count}/{run.max_turns}
          </span>
        </div>
      </div>
      <div className="adventure-run-item__actions">
        <button type="button" onClick={onResume}>
          {t("adventure.resume")}
        </button>
        {onDelete && (
          <button type="button" className="is-danger" onClick={onDelete}>
            {t("adventure.delete")}
          </button>
        )}
      </div>
    </article>
  );
}

export default function AdventureHub() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const replayRunId = (location.state as { replayRunId?: string } | null)
    ?.replayRunId;
  // Prompt Expander のエントリカードからの導線(/adventure?pe_entry=<id>)
  const peEntryParam = new URLSearchParams(location.search).get("pe_entry");
  const {
    runs,
    templates,
    loading,
    setupGenerating,
    error,
    loadRuns,
    loadTemplates,
    generateSetup,
    createRun,
    removeRun,
    clearError,
    lastRunId,
    avatarModels,
  } = useAdventure();
  // 1ページ目のセッション一覧。既定選択と保存済みIDの解決に使う(一覧表示はモーダル側)
  const [sessions, setSessions] = useState<GallerySession[]>([]);
  // 開始セッション(+時点)の選択。送信用IDは下で派生値として取り出す
  const [sourceSelection, setSourceSelection] =
    useState<AdventureSourceSelection | null>(null);
  // 選択モーダルの対象。source=開始セッション、player=romanceの主人公セッション
  const [pickerTarget, setPickerTarget] = useState<"source" | "player" | null>(
    null,
  );
  const [startMode, setStartMode] = useState<"generated" | "authored">(
    "generated",
  );
  const [preset, setPreset] = useState<AdventurePreset>("romance");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedReplayRunId, setSelectedReplayRunId] = useState("");
  const [scenarioPickerOpen, setScenarioPickerOpen] = useState(false);
  const [scenarioPickerTab, setScenarioPickerTab] = useState<
    "authored" | "played"
  >("authored");
  const [scenarioSetting, setScenarioSetting] = useState("");
  const [scenarioObjective, setScenarioObjective] = useState("");
  const [scenarioConstraints, setScenarioConstraints] = useState("");
  // 入力途中の桁削除を許すため文字列で保持し、送信時とblur時にクランプする
  const [scenarioMaxTurns, setScenarioMaxTurns] = useState(
    String(DEFAULT_MAX_TURNS),
  );
  // romance はターン数入力の代わりに日数セレクトを使う
  const [romanceDays, setRomanceDays] = useState(ROMANCE_DEFAULT_DAYS);
  // 対面会話モードは日数の代わりにターン数を選ぶ
  const [companionTurns, setCompanionTurns] = useState<number>(
    COMPANION_DEFAULT_TURNS,
  );
  const [detailsOpen, setDetailsOpen] = useState(false);
  // localStorageの読み出しは初回マウント時の一度だけに限定する
  const [savedSetupPrefs] = useState(readSetupPrefs);
  const [narrationVoice, setNarrationVoice] = useState<AdventureNarrationVoice>(
    () =>
      normalizeNarrationVoice(savedSetupPrefs.narrationVoice) ??
      "second_person",
  );
  const [narrationPronoun, setNarrationPronoun] = useState(
    () =>
      normalizeNarrationPronoun(savedSetupPrefs.narrationPronoun) ??
      DEFAULT_NARRATION_PRONOUN,
  );
  const [speechStyle, setSpeechStyle] = useState<AdventureSpeechStyle>(
    () =>
      normalizeSpeechStyle(savedSetupPrefs.speechStyle) ?? DEFAULT_SPEECH_STYLE,
  );
  const [speechCustom, setSpeechCustom] = useState(
    () => normalizeSpeechCustom(savedSetupPrefs.speechCustom) ?? "",
  );
  // 攻略対象の口調。空欄なら人物像からLLMが決めるため、次回へは引き継がない
  const [partnerSpeechStyle, setPartnerSpeechStyle] = useState("");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [creating, setCreating] = useState(false);
  const { state: settingsState, effectiveNovelaiImageModel } = useSettings();
  // 精密参照は既定OFF。ユーザーが明示的にONした場合のみAnlas追加消費
  const [usePreciseReference, setUsePreciseReference] = useState(false);
  const [startAnlasConfirmOpen, setStartAnlasConfirmOpen] = useState(false);
  // この run 専用のNovelAI画像モデル。"default" はグローバル設定に従う
  const [imageModelChoice, setImageModelChoice] = useState<string>(() => {
    const saved = savedSetupPrefs.imageModel;
    return typeof saved === "string" && isAdventureImageModelValue(saved)
      ? saved
      : "default";
  });
  // モデル選択を反映した実効モデルでV5判定する(精密参照の可否・Anlas確認に効く)
  const setupIsV5 =
    settingsState.imageProvider === "novelai" &&
    isV5ImageModel(
      imageModelChoice === "default"
        ? effectiveNovelaiImageModel
        : imageModelChoice,
    );
  // 前回の選択があればそれを優先し、未保存ならグローバル設定を初期値とする
  const [companionMode, setCompanionMode] = useState(
    () => savedSetupPrefs.companionMode === true,
  );
  const [companionAvatarId, setCompanionAvatarId] = useState(() =>
    typeof savedSetupPrefs.companionAvatarId === "string"
      ? savedSetupPrefs.companionAvatarId
      : "",
  );
  // 持ち物システム(全プリセット)。シナリオの進行方法が大きく変わるため既定 OFF
  const [inventoryEnabled, setInventoryEnabled] = useState(
    () => savedSetupPrefs.inventoryEnabled === true,
  );
  const [enableCompositeScene, setEnableCompositeScene] = useState(() =>
    typeof savedSetupPrefs.enableCompositeScene === "boolean"
      ? savedSetupPrefs.enableCompositeScene
      : settingsState.adventureEnableCompositeScene,
  );
  // プレイ画面と同じブラウザ単位の好み。専用キーで共有する
  const {
    drawPortraitEveryTurn,
    setDrawPortraitEveryTurn,
    drawPartnerEveryTurn,
    setDrawPartnerEveryTurn,
  } = useAdventureDrawPreferences();
  // romance の主人公(自分)。既定は男性キャラ、選択したら次回にも保存する
  const [romancePlayerId, setRomancePlayerId] = useState(() => {
    const saved = savedSetupPrefs.romancePlayerCharacterId;
    return typeof saved === "string" && saved.trim()
      ? saved
      : ROMANCE_DEFAULT_PLAYER_ID;
  });
  const [playerCharacters, setPlayerCharacters] = useState<Character[]>([]);
  // 主人公を「セッションの姿」にする場合の選択。保存済みIDは sessions ロード後に解決する
  const [playerSelection, setPlayerSelection] =
    useState<AdventureSourceSelection | null>(null);
  // romance の主人公の呼び名(攻略対象がセリフで呼ぶ名前)。選択したキャラクターの
  // 名前を既定値として埋め、ユーザーが書き換えた値は選択を変えても保持する
  const [romancePlayerName, setRomancePlayerName] = useState(() => {
    const saved = savedSetupPrefs.romancePlayerName;
    return typeof saved === "string"
      ? saved.slice(0, ROMANCE_PLAYER_NAME_MAX_LENGTH)
      : "";
  });

  // 既存の送信・保存ロジックは選択オブジェクトから派生したIDを参照する
  const sourceSessionId = sourceSelection?.sessionId ?? "";
  const sourceHistoryId = sourceSelection?.historyId;
  const sourcePeEntryId = sourceSelection?.promptExpanderEntryId;
  // 開始元はセッションか Prompt Expander エントリのどちらかがあればよい
  const hasSource = Boolean(sourceSessionId || sourcePeEntryId);
  const romancePlayerSessionId = playerSelection?.sessionId ?? "";
  const romancePlayerHistoryId = playerSelection?.historyId;
  // 呼び名の既定値。テンプレキャラならその名前、セッションの姿なら紐づく主人公名
  const romancePlayerDefaultName =
    romancePlayerId === ROMANCE_PLAYER_SESSION_VALUE
      ? (playerSelection?.characterName ?? "")
      : (playerCharacters.find((character) => character.id === romancePlayerId)
          ?.name ?? "");
  const previousPlayerDefaultNameRef = useRef("");
  useEffect(() => {
    // 候補の読み込み前やセッション未解決の間(既定値が空)は何もしない
    if (!romancePlayerDefaultName) return;
    const previous = previousPlayerDefaultNameRef.current;
    previousPlayerDefaultNameRef.current = romancePlayerDefaultName;
    // 未入力か既定値のままなら新しい既定値へ追従し、書き換え済みなら保持する
    setRomancePlayerName((current) =>
      current.trim() === "" || current === previous
        ? romancePlayerDefaultName
        : current,
    );
  }, [romancePlayerDefaultName]);

  useEffect(() => {
    const prefs: AdventureSetupPrefs = {
      narrationVoice,
      narrationPronoun: narrationPronoun.trim() || DEFAULT_NARRATION_PRONOUN,
      speechStyle,
      speechCustom: speechCustom.trim(),
      enableCompositeScene,
      companionMode,
      companionAvatarId,
      romancePlayerCharacterId: romancePlayerId,
      romancePlayerSessionId,
      romancePlayerName,
      imageModel: imageModelChoice,
      inventoryEnabled,
    };
    try {
      writeStorage("local", SETUP_PREFS_STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // プライベートモード等で保存できなくてもフォーム操作は継続する
    }
  }, [
    narrationVoice,
    narrationPronoun,
    speechStyle,
    speechCustom,
    enableCompositeScene,
    companionMode,
    companionAvatarId,
    romancePlayerId,
    romancePlayerSessionId,
    romancePlayerName,
    imageModelChoice,
    inventoryEnabled,
  ]);

  // セッションの姿モードで未選択の間は、保存済みセッションIDを解決する。
  // 1ページ目に見つからなければ先頭セッションへ倒す(時点は現在の状態)
  useEffect(() => {
    if (romancePlayerId !== ROMANCE_PLAYER_SESSION_VALUE) return;
    if (playerSelection || sessions.length === 0) return;
    const saved = sessions.find(
      (session) =>
        session.session_id === savedSetupPrefs.romancePlayerSessionId,
    );
    setPlayerSelection(selectionFromSession(saved ?? sessions[0]));
  }, [romancePlayerId, sessions, playerSelection, savedSetupPrefs]);

  // 主人公候補は romance を選んだときだけ読み込む
  useEffect(() => {
    if (preset !== "romance" || playerCharacters.length > 0) return;
    let cancelled = false;
    void fetch(`${API_BASE}/game/characters`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { characters?: Character[] } | null) => {
        if (!cancelled && data?.characters) {
          setPlayerCharacters(data.characters);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [preset, playerCharacters.length]);

  useEffect(() => {
    void loadRuns();
    void loadTemplates();
    void fetchGallerySessions(1, 50).then((response) => {
      setSessions(response.sessions);
      const first = response.sessions[0];
      if (first) {
        setSourceSelection((prev) => prev ?? selectionFromSession(first));
      }
    });
  }, [loadRuns, loadTemplates]);

  useEffect(() => {
    if (!replayRunId) return;
    setStartMode("authored");
    setSelectedReplayRunId(replayRunId);
  }, [replayRunId]);

  // ?pe_entry=<id> で開かれたら、そのエントリを開始元に据えてクエリを消す。
  // StrictMode の二重実行と、navigate 後の再実行を ref で抑止する
  const peDeepLinkHandledRef = useRef(false);
  const promptExpanderEnabled = settingsState.experimentalPromptExpanderEnabled;
  useEffect(() => {
    if (!peEntryParam || !promptExpanderEnabled) return;
    if (peDeepLinkHandledRef.current) return;
    peDeepLinkHandledRef.current = true;
    navigate("/adventure", { replace: true });
    void fetchPromptExpanderEntry(peEntryParam)
      .then((entry) => {
        setSourceSelection(selectionFromPromptExpanderEntry(entry));
      })
      .catch((caught: unknown) => {
        // 取得できなければ既定の開始セッション選択に倒す
        console.warn("Failed to load Prompt Expander entry:", caught);
      });
  }, [peEntryParam, promptExpanderEnabled, navigate]);

  const selectedTemplate = templates.find(
    (template) => template.id === selectedTemplateId,
  );
  const selectedReplayRun = runs.find((run) => run.id === selectedReplayRunId);
  const selectedScenario = selectedReplayRun ?? selectedTemplate;
  const selectedScenarioPreset =
    selectedReplayRun?.preset ?? selectedTemplate?.preset;
  // 実際に開始されるプリセット。リプレイ・作品シナリオは選択側が優先される
  const effectivePreset =
    startMode === "authored" ? (selectedScenarioPreset ?? preset) : preset;
  // 生成時間の見積もりと「テキストのみ」告知は同じ設定から導く
  const setupCompanion = effectivePreset === "romance" && companionMode;
  const setupAvatarKnown =
    companionAvatarId !== "" &&
    avatarModels.some((model) => model.id === companionAvatarId);
  const setupImageSettings = {
    preset: effectivePreset,
    enableCompositeScene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn,
    companionMode: setupCompanion,
  };

  // 直前に開いた run を再取得済みの一覧から引く。削除済み・終了済みなら出さない
  const lastRun = useMemo(() => {
    if (!lastRunId) return null;
    const found = runs.find((run) => run.id === lastRunId);
    return found && canActOnRun(found) ? found : null;
  }, [runs, lastRunId]);

  const sortedRuns = useMemo(
    () =>
      [...runs].sort((a, b) => {
        if (a.status === "active" && b.status !== "active") return -1;
        if (b.status === "active" && a.status !== "active") return 1;
        return (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
      }),
    [runs],
  );

  const runCounts = useMemo(() => {
    const counts: Record<RunFilter, number> = {
      all: runs.length,
      active: 0,
      success: 0,
      partial: 0,
      failure: 0,
    };
    for (const run of runs) counts[run.status] += 1;
    return counts;
  }, [runs]);

  const filteredRuns = useMemo(
    () =>
      runFilter === "all"
        ? sortedRuns
        : sortedRuns.filter((run) => run.status === runFilter),
    [sortedRuns, runFilter],
  );

  useEffect(() => {
    if (!scenarioPickerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setScenarioPickerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [scenarioPickerOpen]);

  // ターン数は生成物ではなくユーザーが決めた生成条件なので、ここではリセットしない
  const clearGeneratedSetup = () => {
    setScenarioSetting("");
    setScenarioObjective("");
    setScenarioConstraints("");
  };

  // 開始セッション/時点を選び直したら、生成済みのシナリオ案は破棄する
  const handleSourceSelect = (selection: AdventureSourceSelection) => {
    setSourceSelection(selection);
    clearGeneratedSetup();
    setPickerTarget(null);
  };

  // 主人公側の変更ではシナリオ案を保持する(従来の挙動を踏襲)
  const handlePlayerSelect = (selection: AdventureSourceSelection) => {
    setPlayerSelection(selection);
    setPickerTarget(null);
  };

  const effectiveMaxTurns = clampMaxTurns(
    Number.parseInt(scenarioMaxTurns, 10),
  );
  // romance は日数×2 をターン予算として送る。対面会話モードはターン数そのまま
  const effectiveScenarioTurns =
    preset === "romance"
      ? companionMode
        ? companionTurns
        : romanceDays * 2
      : effectiveMaxTurns;

  const openScenarioPicker = () => {
    setScenarioPickerTab(selectedReplayRunId ? "played" : "authored");
    setScenarioPickerOpen(true);
  };
  // 制約は backend の上限件数を超えると 422 になるため、送信前に件数を見て
  // 開始・生成ボタンを止め、理由を表示する
  const constraintCount = splitConstraintLines(scenarioConstraints).length;
  const tooManyConstraints = constraintCount > SCENARIO_CONSTRAINTS_MAX_ITEMS;

  const handleGenerateSetup = async () => {
    if (!hasSource || tooManyConstraints) return;
    // 入力済みの舞台・ゴール・制約は下書きとして渡し、LLM に意味を保ったまま
    // 仕上げ・補完させる。空の項目はキー自体を送らない
    const draftSetting = scenarioSetting.trim();
    const draftObjective = scenarioObjective.trim();
    const draftConstraints = splitConstraintLines(scenarioConstraints);
    try {
      const generated = await generateSetup({
        source_session_id: sourceSessionId || undefined,
        source_history_id: sourceHistoryId,
        source_prompt_expander_entry_id: sourcePeEntryId,
        preset,
        scenario_max_turns: effectiveScenarioTurns,
        companion_mode: preset === "romance" && companionMode,
        ...(draftSetting ? { scenario_setting: draftSetting } : {}),
        ...(draftObjective ? { scenario_objective: draftObjective } : {}),
        ...(draftConstraints.length > 0
          ? { scenario_constraints: draftConstraints }
          : {}),
      });
      setScenarioSetting(generated.setting);
      setScenarioObjective(generated.objective);
      setScenarioConstraints(generated.constraints.join("\n"));
      setDetailsOpen(true);
    } catch {
      return;
    }
  };

  const startDisabledReason = (): string | null => {
    if (!hasSource) return t("adventure.disabledReason.noSession");
    if (startMode === "generated" && !scenarioObjective.trim())
      return t("adventure.disabledReason.noObjective");
    if (startMode === "generated" && tooManyConstraints)
      return t("adventure.disabledReason.tooManyConstraints", {
        max: SCENARIO_CONSTRAINTS_MAX_ITEMS,
        count: constraintCount,
      });
    if (startMode === "authored" && !selectedScenario)
      return t("adventure.disabledReason.noScenario");
    return null;
  };

  const performCreate = async () => {
    if (!hasSource) return;
    const authoredTemplate =
      startMode === "authored" && !selectedReplayRun ? selectedTemplate : null;
    setCreating(true);
    try {
      const run = await createRun({
        source_session_id: sourceSessionId || undefined,
        source_history_id: sourceHistoryId,
        source_prompt_expander_entry_id: sourcePeEntryId,
        preset: selectedReplayRun?.preset ?? authoredTemplate?.preset ?? preset,
        custom_setup: "",
        scenario_setting: startMode === "generated" ? scenarioSetting : "",
        scenario_objective: startMode === "generated" ? scenarioObjective : "",
        scenario_constraints:
          startMode === "generated"
            ? splitConstraintLines(scenarioConstraints)
            : [],
        scenario_template_id: authoredTemplate?.id,
        replay_run_id: selectedReplayRun?.id,
        scenario_max_turns:
          startMode === "generated" ? effectiveScenarioTurns : undefined,
        narration_voice: narrationVoice,
        narration_pronoun: narrationPronoun.trim() || DEFAULT_NARRATION_PRONOUN,
        player_speech_style: speechStyle,
        player_speech_custom: speechCustom.trim(),
        romance_partner_speech_style:
          effectivePreset === "romance" ? partnerSpeechStyle.trim() : "",
        // V5系モデルは精密参照非対応のため実効値をOFFにする
        use_precise_reference: usePreciseReference && !setupIsV5,
        enable_composite_scene: enableCompositeScene,
        companion_mode: setupCompanion,
        // 持ち物システム。作品シナリオはサーバ側で無視される
        inventory_enabled: startMode === "generated" && inventoryEnabled,
        // 登録済みモデルに限って送る(削除済みの保存値は「なし」に倒す)
        companion_avatar_id:
          setupCompanion && setupAvatarKnown ? companionAvatarId : undefined,
        respect_clothing_layers: settingsState.respectClothingLayers,
        // "default" 選択時は送らず、runはグローバル設定に従う
        image_model:
          imageModelChoice === "default" ? undefined : imageModelChoice,
        romance_player_character_id:
          startMode === "generated" &&
          preset === "romance" &&
          romancePlayerId !== ROMANCE_PLAYER_SESSION_VALUE
            ? romancePlayerId
            : undefined,
        romance_player_session_id:
          startMode === "generated" &&
          preset === "romance" &&
          romancePlayerId === ROMANCE_PLAYER_SESSION_VALUE
            ? romancePlayerSessionId || undefined
            : undefined,
        romance_player_history_id:
          startMode === "generated" &&
          preset === "romance" &&
          romancePlayerId === ROMANCE_PLAYER_SESSION_VALUE
            ? romancePlayerHistoryId
            : undefined,
        // 空欄はサーバ側で選択したキャラクターの名前へ倒す
        romance_player_name:
          startMode === "generated" && preset === "romance"
            ? romancePlayerName.trim() || undefined
            : undefined,
      });
      navigate(`/adventure/${run.id}`);
    } catch {
      return;
    } finally {
      setCreating(false);
    }
  };

  // 精密参照ONの開始はオープニング画像生成からAnlasを消費するため確認を挟む。
  // Anlasを消費するのはNovelAIプロバイダーのときだけ
  const handleCreate = async () => {
    if (!hasSource) return;
    if (
      settingsState.imageProvider === "novelai" &&
      usePreciseReference &&
      !setupIsV5 &&
      !readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)
    ) {
      setStartAnlasConfirmOpen(true);
      return;
    }
    await performCreate();
  };

  const handleStartAnlasConfirm = (suppressUntilBrowserClose: boolean) => {
    if (suppressUntilBrowserClose) {
      writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
    }
    setStartAnlasConfirmOpen(false);
    void performCreate();
  };

  const disabledReason = startDisabledReason();

  return (
    <MainLayout>
      <div className="adventure-hub">
        <header className="adventure-hub__header">
          <div>
            <p className="adventure-eyebrow">TSF Closet</p>
            <h1>{t("adventure.title")}</h1>
          </div>
        </header>

        {lastRun && (
          <section
            className="adventure-continue"
            aria-label={t("adventure.continueLast")}
          >
            <h2>{t("adventure.continueLast")}</h2>
            <AdventureRunRow
              run={lastRun}
              onResume={() => navigate(`/adventure/${lastRun.id}`)}
            />
          </section>
        )}

        {error && (
          <button
            type="button"
            className="adventure-error"
            onClick={clearError}
          >
            {error}
          </button>
        )}

        <section className="adventure-card adventure-card--source">
          <h2>{t("adventure.stepSource")}</h2>
          <p className="adventure-card__hint">
            {t("adventure.stepSourceHint")}
          </p>
          <SourceSelectionSummary
            selection={sourceSelection}
            disabled={setupGenerating || loading}
            onOpenPicker={() => setPickerTarget("source")}
          />
        </section>

        <section className="adventure-card adventure-card--mission">
          <h2>{t("adventure.stepMission")}</h2>
          <p className="adventure-card__hint">
            {t("adventure.stepMissionHint")}
          </p>

          <fieldset className="adventure-start-mode-cards">
            <legend>{t("adventure.startMode")}</legend>
            <div className="adventure-mode-cards">
              <button
                type="button"
                disabled={setupGenerating || loading}
                className={startMode === "generated" ? "is-active" : ""}
                onClick={() => setStartMode("generated")}
                aria-pressed={startMode === "generated"}
              >
                <strong>{t("adventure.startModes.generated")}</strong>
                <span>{t("adventure.startModeHints.generated")}</span>
              </button>
              <button
                type="button"
                disabled={setupGenerating || loading}
                className={startMode === "authored" ? "is-active" : ""}
                onClick={() => {
                  setStartMode("authored");
                  openScenarioPicker();
                }}
                aria-pressed={startMode === "authored"}
              >
                <strong>{t("adventure.startModes.authored")}</strong>
                <span>{t("adventure.startModeHints.authored")}</span>
              </button>
            </div>
          </fieldset>

          {startMode === "generated" ? (
            <>
              <fieldset className="adventure-setup__mission">
                <legend>{t("adventure.preset")}</legend>
                <div className="adventure-preset-cards">
                  {PRESETS.map((value) => (
                    <button
                      type="button"
                      key={value}
                      disabled={setupGenerating || loading}
                      className={preset === value ? "is-active" : ""}
                      onClick={() => {
                        setPreset(value);
                        clearGeneratedSetup();
                        setDetailsOpen(false);
                      }}
                      aria-pressed={preset === value}
                    >
                      <strong>{t(`adventure.presets.${value}`)}</strong>
                      <span>{t(`adventure.presetHints.${value}`)}</span>
                      <small>{t(`adventure.presetExamples.${value}`)}</small>
                    </button>
                  ))}
                </div>
              </fieldset>

              <ol className="adventure-mission-flow">
                <li>{t("adventure.missionFlow.step1")}</li>
                <li>{t("adventure.missionFlow.step2")}</li>
                <li>{t("adventure.missionFlow.step3")}</li>
              </ol>

              <div className="adventure-setup-generator">
                {/* 持ち物システム(全プリセット)。既定 OFF。シナリオの進行方法に大きく影響する */}
                <AdventureToggleRow
                  className="adventure-inventory-toggle"
                  label={t("adventure.inventoryEnable")}
                  hint={t("adventure.inventoryHint")}
                  checked={inventoryEnabled}
                  disabled={setupGenerating || loading || creating}
                  onChange={setInventoryEnabled}
                />
                {/* ヒントは label の外に出す。label 内に入れると入力の
                    アクセシブル名にヒント全文が混ざる */}
                {preset === "romance" ? (
                  <>
                    {/* 対面会話モード(1手番=1往復・昼夜なし)。ON なら日数でなくターン数を選ぶ */}
                    <AdventureToggleRow
                      className="adventure-companion-toggle"
                      label={t("adventure.companionMode")}
                      hint={t("adventure.companionModeHint")}
                      checked={companionMode}
                      disabled={setupGenerating || loading || creating}
                      onChange={setCompanionMode}
                    />
                    {/* 3D モデル(VRM)。対面会話モード OFF でも隠さず、文言で説明する */}
                    <label className="adventure-setup-turns adventure-setup-avatar">
                      <span className="adventure-setup-turns__label">
                        {t("adventure.avatar.selectLabel")}
                      </span>
                      <select
                        value={setupAvatarKnown ? companionAvatarId : ""}
                        disabled={setupGenerating || loading || creating}
                        onChange={(event) =>
                          setCompanionAvatarId(event.target.value)
                        }
                      >
                        <option value="">{t("adventure.avatar.none")}</option>
                        <AvatarModelOptions models={avatarModels} />
                      </select>
                      <span className="adventure-setup-turns__hint">
                        {avatarModels.length === 0 ? (
                          <>
                            {t("adventure.avatar.noModelsHint")}{" "}
                            <Link to={ROUTES.SETTINGS}>
                              {t("adventure.avatar.registerLink")}
                            </Link>
                          </>
                        ) : companionMode ? (
                          t("adventure.avatar.setupHint")
                        ) : (
                          t("adventure.avatar.companionOffHint")
                        )}
                      </span>
                      <AvatarWardrobeHint
                        models={avatarModels}
                        selectedId={setupAvatarKnown ? companionAvatarId : null}
                      />
                    </label>
                    {companionMode ? (
                      <label className="adventure-setup-turns">
                        <span className="adventure-setup-turns__label">
                          {t("adventure.companionTurns")}
                        </span>
                        <select
                          value={companionTurns}
                          disabled={setupGenerating || loading || creating}
                          onChange={(event) =>
                            setCompanionTurns(Number(event.target.value))
                          }
                        >
                          {COMPANION_TURN_OPTIONS.map((turns) => (
                            <option key={turns} value={turns}>
                              {turns}
                            </option>
                          ))}
                        </select>
                        <span className="adventure-setup-turns__unit">
                          {t("adventure.companionTurnsUnit")}
                        </span>
                      </label>
                    ) : (
                      <label className="adventure-setup-turns">
                        <span className="adventure-setup-turns__label">
                          {t("adventure.romance.days")}
                        </span>
                        <select
                          value={romanceDays}
                          disabled={setupGenerating || loading || creating}
                          onChange={(event) =>
                            setRomanceDays(Number(event.target.value))
                          }
                        >
                          {ROMANCE_DAY_OPTIONS.map((days) => (
                            <option key={days} value={days}>
                              {days}
                            </option>
                          ))}
                        </select>
                        <span className="adventure-setup-turns__unit">
                          {t("adventure.romance.daysUnit")}
                        </span>
                      </label>
                    )}
                    <label
                      className="adventure-setup-turns"
                      title={t("adventure.romance.playerHint")}
                    >
                      <span className="adventure-setup-turns__label">
                        {t("adventure.romance.player")}
                      </span>
                      <select
                        value={romancePlayerId}
                        disabled={setupGenerating || loading || creating}
                        onChange={(event) =>
                          setRomancePlayerId(event.target.value)
                        }
                      >
                        {playerCharacters.length === 0 ? (
                          <option value={ROMANCE_DEFAULT_PLAYER_ID}>
                            {t("adventure.romance.playerLoading")}
                          </option>
                        ) : (
                          playerCharacters.map((character) => (
                            <option key={character.id} value={character.id}>
                              {character.name}
                            </option>
                          ))
                        )}
                        <option value={ROMANCE_PLAYER_SESSION_VALUE}>
                          {t("adventure.romance.playerFromSession")}
                        </option>
                      </select>
                    </label>
                    <label
                      className="adventure-setup-turns adventure-setup-turns--player-name"
                      title={t("adventure.romance.playerNameHint")}
                    >
                      <span className="adventure-setup-turns__label">
                        {t("adventure.romance.playerName")}
                      </span>
                      <input
                        type="text"
                        maxLength={ROMANCE_PLAYER_NAME_MAX_LENGTH}
                        value={romancePlayerName}
                        disabled={setupGenerating || loading || creating}
                        placeholder={
                          romancePlayerDefaultName ||
                          t("adventure.romance.playerNamePlaceholder")
                        }
                        onChange={(event) =>
                          setRomancePlayerName(event.target.value)
                        }
                      />
                    </label>
                  </>
                ) : (
                  <label className="adventure-setup-turns">
                    <span className="adventure-setup-turns__label">
                      {t("adventure.maxTurns")}
                    </span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={MIN_MAX_TURNS}
                      max={MAX_MAX_TURNS}
                      step={1}
                      value={scenarioMaxTurns}
                      disabled={setupGenerating || loading || creating}
                      onChange={(event) =>
                        setScenarioMaxTurns(event.target.value)
                      }
                      onBlur={() =>
                        setScenarioMaxTurns(String(effectiveMaxTurns))
                      }
                    />
                    <span className="adventure-setup-turns__unit">
                      {t("adventure.maxTurnsUnit")}
                    </span>
                  </label>
                )}
                <button
                  type="button"
                  disabled={
                    !hasSource ||
                    setupGenerating ||
                    loading ||
                    tooManyConstraints
                  }
                  aria-busy={setupGenerating}
                  onClick={() => void handleGenerateSetup()}
                >
                  {setupGenerating && (
                    <span className="adventure-setup-generator__spinner" />
                  )}
                  {setupGenerating
                    ? t("adventure.generatingSetup")
                    : t("adventure.generateSetup")}
                </button>
                <small className="adventure-setup-turns__hint">
                  {preset === "romance"
                    ? companionMode
                      ? t("adventure.companionTurnsHint")
                      : t("adventure.romance.daysHint", {
                          min: ROMANCE_MIN_DAYS,
                          max: ROMANCE_MAX_DAYS,
                        })
                    : t("adventure.maxTurnsHint", {
                        min: MIN_MAX_TURNS,
                        max: MAX_MAX_TURNS,
                      })}
                </small>
              </div>

              {preset === "romance" &&
                romancePlayerId === ROMANCE_PLAYER_SESSION_VALUE && (
                  <div className="adventure-romance-player-source">
                    <span className="adventure-romance-player-source__label">
                      {t("adventure.romance.playerSession")}
                    </span>
                    <SourceSelectionSummary
                      selection={playerSelection}
                      disabled={setupGenerating || loading || creating}
                      onOpenPicker={() => setPickerTarget("player")}
                    />
                  </div>
                )}

              <details
                className="adventure-setup-details-wrapper"
                open={detailsOpen}
                onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
              >
                <summary>{t("adventure.detailsToggle")}</summary>
                <small className="adventure-setup-turns__hint">
                  {t("adventure.detailsDraftHint")}
                </small>
                <div className="adventure-setup-details">
                  <label>
                    <span>{t("adventure.setting")}</span>
                    <textarea
                      value={scenarioSetting}
                      maxLength={600}
                      rows={2}
                      onChange={(event) =>
                        setScenarioSetting(event.target.value)
                      }
                      placeholder={t("adventure.settingPlaceholder")}
                    />
                  </label>
                  <label>
                    <span>{t("adventure.goal")}</span>
                    <textarea
                      value={scenarioObjective}
                      maxLength={600}
                      rows={2}
                      onChange={(event) =>
                        setScenarioObjective(event.target.value)
                      }
                      placeholder={t("adventure.goalPlaceholder")}
                    />
                  </label>
                  <label>
                    <span>{t("adventure.constraints")}</span>
                    <textarea
                      value={scenarioConstraints}
                      maxLength={SCENARIO_CONSTRAINTS_MAX_LENGTH}
                      rows={3}
                      aria-invalid={tooManyConstraints || undefined}
                      onChange={(event) =>
                        setScenarioConstraints(event.target.value)
                      }
                      placeholder={t("adventure.constraintsPlaceholder", {
                        max: SCENARIO_CONSTRAINTS_MAX_ITEMS,
                      })}
                    />
                    <small
                      className={`adventure-setup-turns__hint${
                        tooManyConstraints
                          ? " adventure-setup-constraints__hint--over"
                          : ""
                      }`}
                    >
                      {tooManyConstraints
                        ? t("adventure.disabledReason.tooManyConstraints", {
                            max: SCENARIO_CONSTRAINTS_MAX_ITEMS,
                            count: constraintCount,
                          })
                        : t("adventure.constraintsCount", {
                            count: constraintCount,
                            max: SCENARIO_CONSTRAINTS_MAX_ITEMS,
                          })}
                    </small>
                  </label>
                </div>
              </details>
            </>
          ) : (
            <div className="adventure-selected-scenario">
              <span>{t("adventure.selectedScenario")}</span>
              {selectedScenario ? (
                <>
                  <strong>{selectedScenario.title}</strong>
                  <p>{selectedScenario.objective}</p>
                  <small>
                    {selectedReplayRun
                      ? t("adventure.scenarioTabs.played")
                      : t("adventure.scenarioTabs.authored")}
                    {selectedScenarioPreset &&
                      ` · ${t("adventure.presetFromScenario")}: ${t(
                        `adventure.presets.${selectedScenarioPreset}`,
                      )}`}
                  </small>
                </>
              ) : (
                <p>{t("adventure.noScenarioSelected")}</p>
              )}
              <button
                type="button"
                disabled={loading}
                onClick={openScenarioPicker}
              >
                {selectedScenario
                  ? t("adventure.chooseScenarioAgain")
                  : t("adventure.selectScenario")}
              </button>
            </div>
          )}

          <details className="adventure-setup-details-wrapper">
            <summary>{t("adventure.storyOptions")}</summary>
            <div className="adventure-setup-details adventure-story-options">
              <fieldset className="adventure-narration-voice">
                <legend>{t("adventure.narrationVoice")}</legend>
                <div className="adventure-narration-voice__cards">
                  {NARRATION_VOICES.map((value) => (
                    <button
                      type="button"
                      key={value}
                      disabled={setupGenerating || loading || creating}
                      className={narrationVoice === value ? "is-active" : ""}
                      aria-pressed={narrationVoice === value}
                      onClick={() => setNarrationVoice(value)}
                    >
                      <strong>{t(`adventure.narrationVoices.${value}`)}</strong>
                      <small>
                        {t(`adventure.narrationVoiceExamples.${value}`, {
                          pronoun:
                            narrationPronoun.trim() ||
                            DEFAULT_NARRATION_PRONOUN,
                        })}
                      </small>
                    </button>
                  ))}
                </div>
                <p className="adventure-narration-voice__hint">
                  {t("adventure.narrationVoiceHint")}
                </p>
              </fieldset>
              {narrationVoice === "first_person" && (
                <label className="adventure-narration-pronoun">
                  <span>{t("adventure.narrationPronoun")}</span>
                  <input
                    type="text"
                    list="adventure-narration-pronoun-options"
                    maxLength={NARRATION_PRONOUN_MAX_LENGTH}
                    value={narrationPronoun}
                    disabled={setupGenerating || loading || creating}
                    onChange={(event) =>
                      setNarrationPronoun(event.target.value)
                    }
                    onBlur={() =>
                      setNarrationPronoun(
                        (current) =>
                          current.trim() || DEFAULT_NARRATION_PRONOUN,
                      )
                    }
                  />
                  <datalist id="adventure-narration-pronoun-options">
                    {NARRATION_PRONOUN_SUGGESTIONS.map((value) => (
                      <option key={value} value={value} />
                    ))}
                  </datalist>
                </label>
              )}
              <fieldset className="adventure-speech-style">
                <legend>{t("adventure.speechStyle")}</legend>
                <div className="adventure-speech-style__cards">
                  {SPEECH_STYLES.map((value) => (
                    <button
                      type="button"
                      key={value}
                      disabled={setupGenerating || loading || creating}
                      className={speechStyle === value ? "is-active" : ""}
                      aria-pressed={speechStyle === value}
                      onClick={() => setSpeechStyle(value)}
                    >
                      <strong>{t(`adventure.speechStyles.${value}`)}</strong>
                      <small>
                        {t(`adventure.speechStyleExamples.${value}`)}
                      </small>
                    </button>
                  ))}
                </div>
                <p className="adventure-speech-style__hint">
                  {t("adventure.speechStyleHint")}
                </p>
              </fieldset>
              {speechStyle === "custom" && (
                <label className="adventure-speech-style__custom">
                  <span>{t("adventure.speechStyleCustom")}</span>
                  <input
                    type="text"
                    maxLength={SPEECH_CUSTOM_MAX_LENGTH}
                    value={speechCustom}
                    disabled={setupGenerating || loading || creating}
                    placeholder={t("adventure.speechStyleCustomPlaceholder")}
                    onChange={(event) => setSpeechCustom(event.target.value)}
                  />
                </label>
              )}
              {effectivePreset === "romance" && (
                <label className="adventure-speech-style__partner">
                  <span>{t("adventure.romance.partnerSpeechStyle")}</span>
                  <input
                    type="text"
                    maxLength={PARTNER_SPEECH_STYLE_MAX_LENGTH}
                    value={partnerSpeechStyle}
                    disabled={setupGenerating || loading || creating}
                    placeholder={t(
                      "adventure.romance.partnerSpeechStylePlaceholder",
                    )}
                    onChange={(event) =>
                      setPartnerSpeechStyle(event.target.value)
                    }
                  />
                  <small>{t("adventure.romance.partnerSpeechStyleHint")}</small>
                </label>
              )}
            </div>
          </details>

          <details className="adventure-setup-details-wrapper">
            <summary>{t("adventure.imageGenOptions")}</summary>
            <div className="adventure-setup-details adventure-image-gen-options">
              <AdventureTurnEstimate settings={setupImageSettings} />
              {/* この run 専用のNovelAI画像モデル。既定はグローバル設定に従う */}
              <AdventureImageModelPicker
                value={imageModelChoice}
                hint={t(
                  settingsState.imageProvider === "novelai"
                    ? "adventure.imageModelHint"
                    : "adventure.imageModelOtherProviderHint",
                )}
                disabled={setupGenerating || loading || creating}
                onChange={setImageModelChoice}
              />
              {/* NovelAI以外では効果もAnlas消費もない旨、V5では非対応の旨を明示する */}
              <AdventureToggleRow
                label={t("adventure.preciseReference")}
                hint={t(
                  setupIsV5
                    ? "adventure.preciseReferenceV5Hint"
                    : settingsState.imageProvider === "novelai"
                      ? "adventure.preciseReferenceHint"
                      : "adventure.preciseReferenceOtherProviderHint",
                )}
                checked={usePreciseReference && !setupIsV5}
                disabled={setupGenerating || loading || creating || setupIsV5}
                onChange={setUsePreciseReference}
              />
              <AdventureToggleRow
                label={t("adventure.enableCompositeScene")}
                hint={t(
                  setupCompanion
                    ? "adventure.enableCompositeSceneCompanionHint"
                    : "adventure.enableCompositeSceneHint",
                )}
                checked={enableCompositeScene}
                disabled={setupGenerating || loading || creating}
                onChange={setEnableCompositeScene}
              />
              {/* 立ち絵の毎ターン描画は合成・精密参照の設定に関わらず効くため常に表示する */}
              <AdventureToggleRow
                label={t("adventure.drawPortraitEveryTurn")}
                hint={t(
                  setupCompanion
                    ? "adventure.drawPortraitEveryTurnCompanionHint"
                    : "adventure.drawPortraitEveryTurnHint",
                )}
                checked={drawPortraitEveryTurn}
                disabled={setupGenerating || loading || creating}
                onChange={setDrawPortraitEveryTurn}
              />
              {preset === "romance" && (
                <AdventureToggleRow
                  label={t("adventure.drawPartnerEveryTurn")}
                  hint={t("adventure.drawPartnerEveryTurnHint")}
                  checked={drawPartnerEveryTurn}
                  disabled={setupGenerating || loading || creating}
                  onChange={setDrawPartnerEveryTurn}
                />
              )}
            </div>
          </details>

          {disabledReason && (
            <p className="adventure-disabled-reason" role="status">
              {disabledReason}
            </p>
          )}

          <button
            type="button"
            className="adventure-primary"
            disabled={
              loading || setupGenerating || creating || !!disabledReason
            }
            onClick={() => void handleCreate()}
          >
            {creating ? t("adventure.preparing") : t("adventure.start")}
          </button>
        </section>

        <section className="adventure-runs">
          <div className="adventure-runs__header">
            <h2>{t("adventure.savedRuns")}</h2>
            <span className="adventure-runs__count">
              {t("adventure.savedRunsCount", { count: runs.length })}
            </span>
          </div>
          {runs.length > 0 && (
            <div
              className="adventure-run-filters"
              role="group"
              aria-label={t("adventure.runFilterLabel")}
            >
              {RUN_FILTERS.map((value) => (
                <button
                  type="button"
                  key={value}
                  className={`adventure-run-filters__chip adventure-run-filters__chip--${value}${
                    runFilter === value ? " is-active" : ""
                  }`}
                  aria-pressed={runFilter === value}
                  // 0件でも選択中なら押せるままにし、抜け出せない状態を作らない
                  disabled={runCounts[value] === 0 && runFilter !== value}
                  onClick={() => setRunFilter(value)}
                >
                  {value === "all"
                    ? t("adventure.runFilterAll")
                    : t(`adventure.status.${value}`)}
                  <span className="adventure-run-filters__count">
                    {runCounts[value]}
                  </span>
                </button>
              ))}
            </div>
          )}
          {runs.length === 0 ? (
            <p className="adventure-empty">{t("adventure.noRuns")}</p>
          ) : filteredRuns.length === 0 ? (
            <p className="adventure-empty">{t("adventure.noRunsForFilter")}</p>
          ) : (
            <div className="adventure-run-list">
              {filteredRuns.map((run) => (
                <AdventureRunRow
                  key={run.id}
                  run={run}
                  onResume={() => navigate(`/adventure/${run.id}`)}
                  onDelete={() => {
                    if (window.confirm(t("adventure.deleteConfirm"))) {
                      void removeRun(run.id);
                    }
                  }}
                />
              ))}
            </div>
          )}
        </section>
      </div>
      <AdventureScenarioPickerModal
        isOpen={scenarioPickerOpen}
        tab={scenarioPickerTab}
        onTabChange={setScenarioPickerTab}
        templates={templates}
        runs={runs}
        selectedTemplateId={selectedTemplateId}
        selectedReplayRunId={selectedReplayRunId}
        onSelectTemplate={(templateId) => {
          setSelectedTemplateId(templateId);
          setSelectedReplayRunId("");
          setStartMode("authored");
          setScenarioPickerOpen(false);
        }}
        onSelectRun={(replayRunId) => {
          setSelectedReplayRunId(replayRunId);
          setSelectedTemplateId("");
          setStartMode("authored");
          setScenarioPickerOpen(false);
        }}
        onClose={() => setScenarioPickerOpen(false)}
      />
      {pickerTarget && (
        <AdventureSessionPickerModal
          title={
            pickerTarget === "source"
              ? t("adventure.sourceSession")
              : t("adventure.romance.playerSession")
          }
          selected={
            pickerTarget === "source" ? sourceSelection : playerSelection
          }
          onSelect={
            pickerTarget === "source" ? handleSourceSelect : handlePlayerSelect
          }
          onClose={() => setPickerTarget(null)}
          // 主人公(player)側は変身後の姿を選ぶ用途なので Prompt Expander は出さない
          allowPromptExpander={
            pickerTarget === "source" &&
            settingsState.experimentalPromptExpanderEnabled
          }
        />
      )}
      {creating && (
        <div
          className="adventure-preparing-overlay"
          role="status"
          aria-live="polite"
        >
          <span className="adventure-preparing-overlay__spinner" aria-hidden />
          <strong>{t("adventure.preparingTitle")}</strong>
          <p>{t("adventure.preparingDetail")}</p>
          <p className="adventure-preparing-overlay__note">
            {t("adventure.preparingNote")}
          </p>
        </div>
      )}
      <AnlasConfirmDialog
        open={startAnlasConfirmOpen}
        body={t("adventure.anlasWarnStartBody", {
          estimate: formatAnlasEstimate(
            t,
            estimateAdventureAnlas({
              kind: "start",
              preset,
              enableCompositeScene,
            }),
          ),
        })}
        onConfirm={handleStartAnlasConfirm}
        onCancel={() => setStartAnlasConfirmOpen(false)}
      />
    </MainLayout>
  );
}
