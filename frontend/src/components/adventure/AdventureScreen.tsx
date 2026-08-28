import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type {
  AdventureBgmKey,
  AdventureInputKind,
  AdventureNarrationVoice,
  AdventurePreset,
  AdventureRun,
  AdventureSim,
  AdventureSpeechStyle,
  AdventureStatus,
  AdventureTurn,
} from "../../apis/adventure";
import { canActOnRun } from "../../apis/adventure";
import { fetchAnlasBalance } from "../../apis/anlas";
import { fetchGallerySessions } from "../../apis/gallery";
import { fetchPromptExpanderEntry } from "../../apis/promptExpander";
import {
  type AvatarExpressionKey,
  type AvatarGestureKey,
  normalizeAvatarExpression,
  normalizeAvatarGesture,
} from "../../constants/companionAvatar";
import {
  ADVENTURE_IMAGE_MODEL_CHOICES,
  isAdventureImageModelValue,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import {
  ANLAS_WARN_SUPPRESSED_KEY,
  DRAW_PARTNER_STORAGE_KEY,
  DRAW_PORTRAIT_STORAGE_KEY,
  readDrawPartnerEveryTurn,
  readDrawPortraitEveryTurn,
  useAdventure,
} from "../../contexts/AdventureContext";
import { useNotification } from "../../contexts/NotificationContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { useAdventureVoice } from "../../hooks/useAdventureVoice";
import {
  type TimedProgressSegment,
  useTimedProgress,
} from "../../hooks/useTimedProgress";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import { ROUTES } from "../../routes";
import type { AnlasBalance, Character, GallerySession } from "../../types";
import {
  type AdventureAnlasEstimate,
  estimateAdventureAnlas,
} from "../../utils/adventureAnlasEstimate";
import {
  joinForSpeech,
  parseDialogueSegments,
  partnerLines,
  stripStageDirections,
} from "../../utils/adventureDialogue";
import {
  ADVENTURE_PROGRESS_BUDGET_MS,
  estimateAdventureTurnSeconds,
  isAdventureTurnTextOnly,
} from "../../utils/adventureTurnTimeEstimate";
import { API_BASE } from "../../utils/api";
import ImagePreviewModal from "../ImagePreviewModal";
import MainLayout from "../layout/MainLayout";
import AdventureAnlasConfirmDialog from "./AdventureAnlasConfirmDialog";
import AdventureAttributeModal from "./AdventureAttributeModal";
import AdventureBgmControl from "./AdventureBgmControl";
import AdventureGiftShopModal from "./AdventureGiftShopModal";
import AdventureImagePromptModal from "./AdventureImagePromptModal";
import AdventurePromptPreviewModal from "./AdventurePromptPreviewModal";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
  selectionFromPromptExpanderEntry,
  selectionFromSession,
} from "./AdventureSessionPickerModal";
import AdventureSpeechStyleModal from "./AdventureSpeechStyleModal";
import "./AdventureScreen.css";

// Anlas見積もりを表示用文字列にする。min=maxなら単一値、異なれば範囲表記
function formatAnlasEstimate(
  t: TFunction,
  estimate: AdventureAnlasEstimate,
): string {
  return estimate.min === estimate.max
    ? t("adventure.anlasEstimateExact", { value: estimate.min })
    : t("adventure.anlasEstimateRange", {
        min: estimate.min,
        max: estimate.max,
      });
}

// 新規作成で選べるミッション。恋愛シミュレーションを先頭に置く。
// "infiltration"(潜入)は「なりすまし・着替え」と体験が重複するため非表示
// (backend は保持しており、既存の潜入 run の表示・リプレイには影響しない)
const PRESETS: AdventurePreset[] = [
  "romance",
  "escape",
  "negotiation",
  "disguise",
];

function mediaUrl(url: string): string {
  if (url.startsWith(`${API_BASE}/`)) return url;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

// 自動生成ミッションのターン数。backend/gateway/consts/adventure_turns.py と揃える
const DEFAULT_MAX_TURNS = 15;
const MIN_MAX_TURNS = 5;
const MAX_MAX_TURNS = 30;

// 恋愛シミュレーションの日数。backend/gateway/consts/adventure_romance.py と揃える。
// 1日=昼夜2ターンなので scenario_max_turns には日数×2 を送る
const ROMANCE_DEFAULT_DAYS = 7;
// 対面会話モードは日数でなくターン数(1ターン=1往復)。romance のクランプ(10〜60、偶数)に合わせる
const COMPANION_DEFAULT_TURNS = 20;
const COMPANION_TURN_OPTIONS = [10, 14, 20, 30, 40, 60] as const;
const ROMANCE_MIN_DAYS = 5;
const ROMANCE_MAX_DAYS = 30;
const ROMANCE_DAY_OPTIONS = Array.from(
  { length: ROMANCE_MAX_DAYS - ROMANCE_MIN_DAYS + 1 },
  (_, index) => ROMANCE_MIN_DAYS + index,
);
// romance の主人公既定キャラクター。backend/gateway/consts/adventure_romance.py と揃える
const ROMANCE_DEFAULT_PLAYER_ID = "char1";
// 主人公セレクトで「セッションの姿を使う」を表す特殊値
const ROMANCE_PLAYER_SESSION_VALUE = "__session__";

function clampMaxTurns(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_TURNS;
  return Math.min(MAX_MAX_TURNS, Math.max(MIN_MAX_TURNS, Math.round(value)));
}

// 主人公ドックは他のHUDパネルと排他にせず、開いたままプレイできるようにする
const PROTAGONIST_DOCK_STORAGE_KEY = "adventure_protagonist_dock_open";

function readProtagonistDockOpen(): boolean {
  try {
    return localStorage.getItem(PROTAGONIST_DOCK_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

// backend/gateway/consts/adventure_narration.py と揃える
const NARRATION_VOICES: AdventureNarrationVoice[] = [
  "second_person",
  "third_person",
  "first_person",
];
const DEFAULT_NARRATION_PRONOUN = "僕";
const NARRATION_PRONOUN_SUGGESTIONS = ["僕", "俺", "私", "わたし", "あたし"];
const NARRATION_PRONOUN_MAX_LENGTH = 10;

// backend/gateway/consts/adventure_speech.py と揃える
const SPEECH_STYLES: AdventureSpeechStyle[] = [
  "polite",
  "casual",
  "formal",
  "custom",
];
const DEFAULT_SPEECH_STYLE: AdventureSpeechStyle = "polite";
const SPEECH_CUSTOM_MAX_LENGTH = 120;
const PARTNER_SPEECH_STYLE_MAX_LENGTH = 200;
// 制約(1行1件)の上限件数。backend の consts/adventure_setup.py と合わせる
const SCENARIO_CONSTRAINTS_MAX_ITEMS = 20;
const SCENARIO_CONSTRAINTS_MAX_LENGTH = 2000;

// セットアップで選んだ語りと画像オプションは次回の作成時にも引き継ぐ。
// 精密参照はAnlasを追加消費するため保存対象に含めず、常に既定OFFから始める
const SETUP_PREFS_STORAGE_KEY = "adventure_setup_prefs";

// 3D モデル(VRM)のステージは three.js を含むため遅延読込する
const CompanionAvatarStage = lazy(
  () => import("./avatar/CompanionAvatarStage"),
);

type AdventureSetupPrefs = {
  narrationVoice: AdventureNarrationVoice;
  narrationPronoun: string;
  /** 主人公のセリフの口調。攻略対象の口調はrun固有なので保存しない */
  speechStyle: AdventureSpeechStyle;
  speechCustom: string;
  enableCompositeScene: boolean;
  /** 対面会話モード(romance のみ)。既定 OFF */
  companionMode: boolean;
  /** 対面会話モードで描く 3D モデル(VRM)の登録 ID。"" は「なし(立ち絵)」 */
  companionAvatarId: string;
  /** romance の主人公(自分)。テンプレキャラID または __session__。次回にも引き継ぐ */
  romancePlayerCharacterId: string;
  /** 主人公を「セッションの姿」にしたときのセッションID */
  romancePlayerSessionId: string;
  /** run 単位のNovelAI画像モデル。"default" はグローバル設定に従う */
  imageModel: string;
};

function readSetupPrefs(): Partial<AdventureSetupPrefs> {
  try {
    const saved = localStorage.getItem(SETUP_PREFS_STORAGE_KEY);
    if (!saved) return {};
    const parsed: unknown = JSON.parse(saved);
    if (!parsed || typeof parsed !== "object") return {};
    return parsed as Partial<AdventureSetupPrefs>;
  } catch {
    return {};
  }
}

function normalizeNarrationVoice(
  value: unknown,
): AdventureNarrationVoice | null {
  return NARRATION_VOICES.includes(value as AdventureNarrationVoice)
    ? (value as AdventureNarrationVoice)
    : null;
}

function normalizeNarrationPronoun(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return trimmed.slice(0, NARRATION_PRONOUN_MAX_LENGTH);
}

function normalizeSpeechStyle(value: unknown): AdventureSpeechStyle | null {
  return SPEECH_STYLES.includes(value as AdventureSpeechStyle)
    ? (value as AdventureSpeechStyle)
    : null;
}

function normalizeSpeechCustom(value: unknown): string | null {
  if (typeof value !== "string") return null;
  return value.trim().slice(0, SPEECH_CUSTOM_MAX_LENGTH);
}

/** 口調をUIへ1行で出す。custom は自由入力本文、空の攻略対象は「自動」表記 */
function speechStyleLabel(
  style: AdventureSpeechStyle,
  custom: string,
  t: (key: string) => string,
): string {
  if (style === "custom") {
    return custom.trim() || t("adventure.speechStyles.polite");
  }
  return t(`adventure.speechStyles.${style}`);
}

type RunFilter = "all" | AdventureStatus;

const RUN_FILTERS: RunFilter[] = [
  "all",
  "active",
  "success",
  "partial",
  "failure",
];

const PORTRAIT_ALPHA_OPTIONS = { threshold: 12, featherRadius: 1.8 };

// 現実改変の宣言記法。判定はサーバ側 _detect_reality_declaration と揃える
const REALITY_DECLARATION_PATTERN =
  /^\s*(?:\[\s*(?:現実改変|reality(?:[ _-]?alteration)?)\s*\]\s*[:：]?|(?:現実改変|reality(?:[ _-]?alteration)?)\s*[:：])\s*\S/i;

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

function AdventureHub() {
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
  const [enableCompositeScene, setEnableCompositeScene] = useState(() =>
    typeof savedSetupPrefs.enableCompositeScene === "boolean"
      ? savedSetupPrefs.enableCompositeScene
      : settingsState.adventureEnableCompositeScene,
  );
  // プレイ画面と同じブラウザ単位の好み。専用キーで共有する
  const [drawPortraitEveryTurn, setDrawPortraitEveryTurn] = useState(
    readDrawPortraitEveryTurn,
  );
  const [drawPartnerEveryTurn, setDrawPartnerEveryTurn] = useState(
    readDrawPartnerEveryTurn,
  );
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

  // 既存の送信・保存ロジックは選択オブジェクトから派生したIDを参照する
  const sourceSessionId = sourceSelection?.sessionId ?? "";
  const sourceHistoryId = sourceSelection?.historyId;
  const sourcePeEntryId = sourceSelection?.promptExpanderEntryId;
  // 開始元はセッションか Prompt Expander エントリのどちらかがあればよい
  const hasSource = Boolean(sourceSessionId || sourcePeEntryId);
  const romancePlayerSessionId = playerSelection?.sessionId ?? "";
  const romancePlayerHistoryId = playerSelection?.historyId;

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
      imageModel: imageModelChoice,
    };
    try {
      localStorage.setItem(SETUP_PREFS_STORAGE_KEY, JSON.stringify(prefs));
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
    imageModelChoice,
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
      sessionStorage.getItem(ANLAS_WARN_SUPPRESSED_KEY) !== "true"
    ) {
      setStartAnlasConfirmOpen(true);
      return;
    }
    await performCreate();
  };

  const handleStartAnlasConfirm = (suppressUntilBrowserClose: boolean) => {
    if (suppressUntilBrowserClose) {
      sessionStorage.setItem(ANLAS_WARN_SUPPRESSED_KEY, "true");
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
                {/* ヒントは label の外に出す。label 内に入れると入力の
                    アクセシブル名にヒント全文が混ざる */}
                {preset === "romance" ? (
                  <>
                    {/* 対面会話モード(1手番=1往復・昼夜なし)。ON なら日数でなくターン数を選ぶ */}
                    <label className="adventure-precise-toggle adventure-companion-toggle">
                      <span className="adventure-precise-toggle__info">
                        <strong>{t("adventure.companionMode")}</strong>
                        <small>{t("adventure.companionModeHint")}</small>
                      </span>
                      <input
                        type="checkbox"
                        className="adventure-precise-toggle__input"
                        checked={companionMode}
                        disabled={setupGenerating || loading || creating}
                        onChange={(event) =>
                          setCompanionMode(event.target.checked)
                        }
                      />
                      <span className="adventure-precise-toggle__switch" />
                    </label>
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
                        {avatarModels.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.name}
                          </option>
                        ))}
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
              {/* 各トグルの結果である所要時間は、スクロールしても見える先頭へ置く */}
              <p className="adventure-turn-estimate">
                {t("adventure.turnTimeEstimate", {
                  seconds: estimateAdventureTurnSeconds(setupImageSettings),
                })}
              </p>
              {isAdventureTurnTextOnly(setupImageSettings) && (
                <p className="adventure-turn-note">
                  {t(
                    setupImageSettings.preset === "romance"
                      ? "adventure.turnImagesDisabledNoticeRomance"
                      : "adventure.turnImagesDisabledNotice",
                  )}
                </p>
              )}
              {/* この run 専用のNovelAI画像モデル。既定はグローバル設定に従う */}
              <label className="adventure-image-model-picker">
                <span className="adventure-precise-toggle__info">
                  <strong>{t("adventure.imageModel")}</strong>
                  <small>
                    {t(
                      settingsState.imageProvider === "novelai"
                        ? "adventure.imageModelHint"
                        : "adventure.imageModelOtherProviderHint",
                    )}
                  </small>
                </span>
                <select
                  value={imageModelChoice}
                  disabled={setupGenerating || loading || creating}
                  onChange={(event) => setImageModelChoice(event.target.value)}
                >
                  <option value="default">
                    {t("adventure.imageModelDefault")}
                  </option>
                  {ADVENTURE_IMAGE_MODEL_CHOICES.map((choice) => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="adventure-precise-toggle">
                <span className="adventure-precise-toggle__info">
                  <strong>{t("adventure.preciseReference")}</strong>
                  {/* NovelAI以外では効果もAnlas消費もない旨、V5では非対応の旨を明示する */}
                  <small>
                    {t(
                      setupIsV5
                        ? "adventure.preciseReferenceV5Hint"
                        : settingsState.imageProvider === "novelai"
                          ? "adventure.preciseReferenceHint"
                          : "adventure.preciseReferenceOtherProviderHint",
                    )}
                  </small>
                </span>
                <input
                  type="checkbox"
                  className="adventure-precise-toggle__input"
                  checked={usePreciseReference && !setupIsV5}
                  disabled={setupGenerating || loading || creating || setupIsV5}
                  onChange={(event) =>
                    setUsePreciseReference(event.target.checked)
                  }
                />
                <span className="adventure-precise-toggle__switch" />
              </label>
              <label className="adventure-precise-toggle">
                <span className="adventure-precise-toggle__info">
                  <strong>{t("adventure.enableCompositeScene")}</strong>
                  <small>
                    {t(
                      setupCompanion
                        ? "adventure.enableCompositeSceneCompanionHint"
                        : "adventure.enableCompositeSceneHint",
                    )}
                  </small>
                </span>
                <input
                  type="checkbox"
                  className="adventure-precise-toggle__input"
                  checked={enableCompositeScene}
                  disabled={setupGenerating || loading || creating}
                  onChange={(event) =>
                    setEnableCompositeScene(event.target.checked)
                  }
                />
                <span className="adventure-precise-toggle__switch" />
              </label>
              {/* 立ち絵の毎ターン描画は合成・精密参照の設定に関わらず効くため常に表示する */}
              <label className="adventure-precise-toggle">
                <span className="adventure-precise-toggle__info">
                  <strong>{t("adventure.drawPortraitEveryTurn")}</strong>
                  <small>
                    {t(
                      setupCompanion
                        ? "adventure.drawPortraitEveryTurnCompanionHint"
                        : "adventure.drawPortraitEveryTurnHint",
                    )}
                  </small>
                </span>
                <input
                  type="checkbox"
                  className="adventure-precise-toggle__input"
                  checked={drawPortraitEveryTurn}
                  disabled={setupGenerating || loading || creating}
                  onChange={(event) => {
                    const next = event.target.checked;
                    setDrawPortraitEveryTurn(next);
                    try {
                      localStorage.setItem(
                        DRAW_PORTRAIT_STORAGE_KEY,
                        String(next),
                      );
                    } catch {
                      // プライベートモード等で保存できなくても切り替え自体は有効
                    }
                  }}
                />
                <span className="adventure-precise-toggle__switch" />
              </label>
              {preset === "romance" && (
                <label className="adventure-precise-toggle">
                  <span className="adventure-precise-toggle__info">
                    <strong>{t("adventure.drawPartnerEveryTurn")}</strong>
                    <small>{t("adventure.drawPartnerEveryTurnHint")}</small>
                  </span>
                  <input
                    type="checkbox"
                    className="adventure-precise-toggle__input"
                    checked={drawPartnerEveryTurn}
                    disabled={setupGenerating || loading || creating}
                    onChange={(event) => {
                      const next = event.target.checked;
                      setDrawPartnerEveryTurn(next);
                      try {
                        localStorage.setItem(
                          DRAW_PARTNER_STORAGE_KEY,
                          String(next),
                        );
                      } catch {
                        // プライベートモード等で保存できなくても切り替え自体は有効
                      }
                    }}
                  />
                  <span className="adventure-precise-toggle__switch" />
                </label>
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
      {scenarioPickerOpen && (
        <div
          className="adventure-scenario-modal"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target)
              setScenarioPickerOpen(false);
          }}
        >
          <section
            className="adventure-scenario-modal__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="adventure-scenario-modal-title"
          >
            <header>
              <h2 id="adventure-scenario-modal-title">
                {t("adventure.selectScenario")}
              </h2>
              <button
                type="button"
                className="adventure-scenario-modal__close"
                aria-label={t("adventure.closeScenarioPicker")}
                onClick={() => setScenarioPickerOpen(false)}
              >
                ×
              </button>
            </header>
            <div className="adventure-scenario-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={scenarioPickerTab === "played"}
                className={scenarioPickerTab === "played" ? "is-active" : ""}
                onClick={() => setScenarioPickerTab("played")}
              >
                {t("adventure.scenarioTabs.played")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={scenarioPickerTab === "authored"}
                className={scenarioPickerTab === "authored" ? "is-active" : ""}
                onClick={() => setScenarioPickerTab("authored")}
              >
                {t("adventure.scenarioTabs.authored")}
              </button>
            </div>
            <div className="adventure-scenario-modal__list">
              {scenarioPickerTab === "authored" ? (
                templates.length === 0 ? (
                  <p className="adventure-empty">
                    {t("adventure.noTemplates")}
                  </p>
                ) : (
                  templates.map((template) => (
                    <button
                      type="button"
                      key={template.id}
                      className={
                        selectedTemplateId === template.id &&
                        !selectedReplayRunId
                          ? "is-selected"
                          : ""
                      }
                      onClick={() => {
                        setSelectedTemplateId(template.id);
                        setSelectedReplayRunId("");
                        setStartMode("authored");
                        setScenarioPickerOpen(false);
                      }}
                    >
                      <span className="adventure-template-item__title">
                        <strong>{template.title}</strong>
                        {template.content_rating === "mature" && (
                          <small>{t("adventure.matureScenario")}</small>
                        )}
                      </span>
                      <span>{template.synopsis}</span>
                      <span className="adventure-scenario-option__meta">
                        {t("adventure.templateMeta", {
                          turns: template.max_turns,
                          preset: t(`adventure.presets.${template.preset}`),
                        })}
                      </span>
                      <span className="adventure-scenario-option__detail">
                        <b>{t("adventure.goal")}</b>
                        <span>{template.objective}</span>
                      </span>
                      <span className="adventure-scenario-option__detail">
                        <b>{t("adventure.constraints")}</b>
                        <span>{template.constraints.join(" / ")}</span>
                      </span>
                    </button>
                  ))
                )
              ) : runs.length === 0 ? (
                <p className="adventure-empty">
                  {t("adventure.noPlayedScenarios")}
                </p>
              ) : (
                runs.map((run) => (
                  <button
                    type="button"
                    key={run.id}
                    className={
                      selectedReplayRunId === run.id ? "is-selected" : ""
                    }
                    onClick={() => {
                      setSelectedReplayRunId(run.id);
                      setSelectedTemplateId("");
                      setStartMode("authored");
                      setScenarioPickerOpen(false);
                    }}
                  >
                    <span className="adventure-template-item__title">
                      <strong>{run.title}</strong>
                      <small>{t(`adventure.status.${run.status}`)}</small>
                    </span>
                    <span>{run.objective}</span>
                    <span className="adventure-scenario-option__meta">
                      {t("adventure.playedScenarioMeta", {
                        turns: run.turn_count,
                        maxTurns: run.max_turns,
                      })}
                    </span>
                  </button>
                ))
              )}
            </div>
          </section>
        </div>
      )}
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
      <AdventureAnlasConfirmDialog
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

interface AdventureStageFrame {
  key: string;
  turnNumber: number;
  /** ステージ／サムネイル用の代表画像 */
  imageUrl: string;
  /** imageUrl が合成シーンか立ち絵か、対面会話モードの攻略対象立ち絵かを示す */
  kind: "composite" | "portrait" | "partner";
  /** 非合成モードの背景。romance ではこの手番の現在地・時間帯のもの */
  backgroundUrl: string | null;
  /** この手番の立ち絵（白背景の元画像）。無ければ null */
  portraitUrl: string | null;
  /** この手番の立ち絵生成の結果。"failed" のとき再試行導線を出す */
  portraitStatus: string | null;
  /** この手番の合成シーン。非合成モードでは null */
  sceneUrl: string | null;
  userInput: string | null;
  inputKind: AdventureTurn["input_kind"] | null;
  narrative: string;
  location: string | null;
  /** romance のみ。この手番確定時点の公開シミュ状態 */
  sim: AdventureSim | null;
  /** romance のみ。この手番の攻略対象の様子 */
  partnerNote: string | null;
  /** romance 非合成のみ。この手番時点の攻略対象の立ち絵(白背景の元画像) */
  partnerUrl: string | null;
  /** この手番時点のBGMカテゴリ。据え置きターンは直前の値を引き継ぐ */
  bgm: AdventureBgmKey;
  /** この手番のBGM選曲理由。キーと対で引き継ぎ、旧runでは null */
  bgmReason: string | null;
  /** 対面会話モードの 3D モデル向け。攻略対象の表情・身振り(無ければ null) */
  partnerExpression?: AvatarExpressionKey | null;
  partnerGesture?: AvatarGestureKey | null;
}

/**
 * フレームが描いている日付と時間帯。サーバの scene_day/scene_slot が唯一の情報源。
 * sim.day/slot は「次に行動する枠」で常に半日先を指すため使わない。
 */
function frameDaySlot(
  frame: AdventureStageFrame | undefined,
): { day: number; slot: "day" | "night" } | null {
  const day = frame?.sim?.scene_day;
  const slot = frame?.sim?.scene_slot;
  if (!frame || frame.turnNumber <= 0) return null;
  if (typeof day !== "number" || (slot !== "day" && slot !== "night"))
    return null;
  return { day, slot };
}

/**
 * romance HUD の共通タイル。
 * 4段(ラベル/値/ゲージ/バッジ)を常に描画し、Day・好感度・所持金の高さを揃える。
 * 値の無い段は visibility を落として枠だけ残す。
 */
function HudTile({
  className,
  title,
  label,
  value,
  gaugeRatio,
  badge,
  badgeClassName,
}: {
  className?: string;
  title?: string;
  label: ReactNode;
  value: ReactNode;
  gaugeRatio: number | null;
  badge: ReactNode | null;
  badgeClassName?: string;
}) {
  return (
    <div
      className={`adventure-hud__tile${className ? ` ${className}` : ""}`}
      title={title}
    >
      <span className="adventure-hud__tile-label">{label}</span>
      <strong className="adventure-hud__tile-value">{value}</strong>
      <span
        className={`adventure-hud__gauge${gaugeRatio === null ? " is-empty" : ""}`}
        aria-hidden
      >
        <i style={{ width: `${gaugeRatio ?? 0}%` }} />
      </span>
      <em
        className={`adventure-hud__tile-badge${badge === null ? " is-empty" : ""}${
          badgeClassName ? ` ${badgeClassName}` : ""
        }`}
      >
        {badge ?? "-"}
      </em>
    </div>
  );
}

/**
 * 台本形式(名前「セリフ」)の本文を、話者ラベル付きの行と地の文に分けて描く。
 * 名前付き行が無ければ本文全体が1つの地の文になる
 */
function AdventureScriptText({
  text,
  speakers,
}: {
  text: string;
  speakers: string[];
}) {
  const segments = parseDialogueSegments(text, speakers);
  return (
    <>
      {segments.map((segment, index) =>
        segment.kind === "dialogue" ? (
          <p
            // biome-ignore lint/suspicious/noArrayIndexKey: 本文の行は順序固定で識別子を持たない
            key={index}
            className="adventure-messagebox__line adventure-messagebox__line--dialogue"
          >
            <span className="adventure-messagebox__speaker">
              {segment.speaker}
            </span>
            <span>「{segment.text}」</span>
          </p>
        ) : (
          <p
            // biome-ignore lint/suspicious/noArrayIndexKey: 本文の行は順序固定で識別子を持たない
            key={index}
            className="adventure-messagebox__line adventure-messagebox__line--narration"
          >
            {segment.text}
          </p>
        ),
      )}
    </>
  );
}

function AdventurePlay({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    activeRun,
    loading,
    streaming,
    phase,
    phaseStep,
    streamingNarrative,
    pendingUserInput,
    talking,
    talkDraft,
    pendingTalkInput,
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
    regenerateChoices,
    updateSettings,
    rewindRun,
    startEpilogue,
    clearError,
    avatarModels,
    companionAvatarFailed,
    setCompanionAvatarFailed,
  } = useAdventure();
  const { showNotification } = useNotification();
  const {
    state: settingsState,
    setAnlasBalance: setGlobalAnlasBalance,
    effectiveNovelaiImageModel,
  } = useSettings();
  const respectClothingLayers = settingsState.respectClothingLayers;
  const [input, setInput] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const turnStripEndRef = useRef<HTMLDivElement>(null);
  // モーダルを開いた時に選択中のビュー切替チップへフォーカスを移すための参照
  const lightboxViewsRef = useRef<HTMLDivElement>(null);
  const messageTextRef = useRef<HTMLDivElement>(null);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number | null>(
    null,
  );
  // モーダル内のナビゲーションはモーダル内で完結させる（ステージ側の
  // selectedFrameIndex には触れない）ため、専用のインデックスを持つ
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [lightboxView, setLightboxView] = useState<
    "scene" | "background" | "portrait" | "partner" | "overview"
  >("scene");
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  // romance 専用モーダル（ギフトショップ・属性付与）
  const [giftShopOpen, setGiftShopOpen] = useState(false);
  const [attributeModalOpen, setAttributeModalOpen] = useState(false);
  const [speechModalOpen, setSpeechModalOpen] = useState(false);
  const [imageSettingsOpen, setImageSettingsOpen] = useState(false);
  const [bgmSettingsOpen, setBgmSettingsOpen] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [messageWindowHidden, setMessageWindowHidden] = useState(false);
  const [hudPanel, setHudPanel] = useState<
    "milestones" | "clues" | "realityRules" | "speechStyle" | "bgm" | null
  >(null);
  const [protagonistDockOpen, setProtagonistDockOpen] = useState(
    readProtagonistDockOpen,
  );
  const [drawPortraitEveryTurn, setDrawPortraitEveryTurn] = useState(
    readDrawPortraitEveryTurn,
  );
  const [drawPartnerEveryTurn, setDrawPartnerEveryTurn] = useState(
    readDrawPartnerEveryTurn,
  );
  // romance の行動パネル: 行動(手番を消費) / トーク(手番を消費しない会話)
  const [actionMode, setActionMode] = useState<"act" | "talk">("act");
  const talkThreadRef = useRef<HTMLDivElement>(null);
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
  // streamingがfalseへ戻るたび（＝各ストリーム完了後）に再取得する。
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
  // HUD の V5 利用上限表示（実効モデルが V5 のときのみ）
  const hudUsage = runIsV5 ? (anlasBalance?.usage ?? null) : null;
  const hudUsageExhausted =
    hudUsage != null && (hudUsage.percent <= 0 || hudUsage.isNegative);
  const hudUsagePercent =
    hudUsage != null ? Math.max(0, Math.min(100, hudUsage.percent)) : 0;
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

  useEffect(() => {
    if (!logOpen) return;
    transcriptEndRef.current?.scrollIntoView({ block: "end" });
  }, [logOpen]);

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

  useEffect(() => {
    if (!streamingNarrative) return;
    const node = messageTextRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [streamingNarrative]);

  const frames = useMemo<AdventureStageFrame[]>(() => {
    if (!activeRun) return [];
    const list: AdventureStageFrame[] = [];
    const runBackground =
      activeRun.background_image_url ?? activeRun.current_image_url ?? null;
    if (activeRun.preset === "romance" && activeRun.companion_mode) {
      // 対面会話モード: 代表画像は攻略対象の立ち絵。生成の無い手番も
      // フレームにし、立ち絵と背景は直前の1枚を引き継ぐ
      let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
      let lastBackgroundUrl = runBackground;
      let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
      let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
      list.push({
        key: "opening",
        turnNumber: 0,
        imageUrl:
          lastPartnerUrl ?? runBackground ?? activeRun.opening_image_url,
        kind: "partner",
        backgroundUrl: runBackground,
        portraitUrl: null,
        portraitStatus: null,
        sceneUrl: null,
        userInput: null,
        inputKind: null,
        narrative: activeRun.opening_narrative,
        location: null,
        sim: activeRun.opening_sim ?? null,
        partnerNote: null,
        partnerUrl: lastPartnerUrl,
        bgm: lastBgm,
        bgmReason: lastBgmReason,
      });
      for (const turn of activeRun.turns) {
        if (turn.bgm) {
          lastBgm = turn.bgm;
          lastBgmReason = turn.bgm_reason ?? null;
        }
        lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
        lastBackgroundUrl = turn.background_image_url ?? lastBackgroundUrl;
        list.push({
          key: turn.id,
          turnNumber: turn.turn_number,
          imageUrl:
            lastPartnerUrl ?? lastBackgroundUrl ?? activeRun.current_image_url,
          kind: "partner",
          backgroundUrl: lastBackgroundUrl,
          portraitUrl: null,
          portraitStatus: null,
          sceneUrl: null,
          userInput: turn.user_input,
          inputKind: turn.input_kind,
          narrative: turn.narrative,
          location: turn.location,
          sim: turn.sim ?? null,
          partnerNote: turn.partner_note ?? null,
          partnerUrl: lastPartnerUrl,
          bgm: lastBgm,
          bgmReason: lastBgmReason,
          partnerExpression: normalizeAvatarExpression(turn.partner_expression),
          partnerGesture: normalizeAvatarGesture(turn.partner_gesture),
        });
      }
    } else if (activeRun.enable_composite_scene) {
      // 合成モードでは攻略対象の立ち絵をターンごとに再生成しないが、
      // ライトボックスの攻略対象タブ用に直近の1枚(最低でも開幕分)を引き継ぐ
      let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
      let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
      let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
      if (activeRun.opening_image_url) {
        list.push({
          key: "opening",
          turnNumber: 0,
          imageUrl: activeRun.opening_image_url,
          kind: "composite",
          backgroundUrl: null,
          portraitUrl: activeRun.opening_portrait_url ?? null,
          portraitStatus: null,
          sceneUrl: activeRun.opening_image_url,
          userInput: null,
          inputKind: null,
          narrative: activeRun.opening_narrative,
          location: null,
          sim: activeRun.opening_sim ?? null,
          partnerNote: null,
          partnerUrl: lastPartnerUrl,
          bgm: lastBgm,
          bgmReason: lastBgmReason,
        });
      }
      for (const turn of activeRun.turns) {
        // 画像の無いターンもBGMは進むため、continue より前に引き継ぐ。
        // 理由はキー更新時だけ取り込み、キーとの食い違いを作らない
        if (turn.bgm) {
          lastBgm = turn.bgm;
          lastBgmReason = turn.bgm_reason ?? null;
        }
        if (!turn.image_url) continue;
        lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
        list.push({
          key: turn.id,
          turnNumber: turn.turn_number,
          imageUrl: turn.image_url,
          kind: "composite",
          backgroundUrl: null,
          portraitUrl: turn.portrait_image_url,
          portraitStatus: turn.portrait_status,
          sceneUrl: turn.image_url,
          userInput: turn.user_input,
          inputKind: turn.input_kind,
          narrative: turn.narrative,
          location: turn.location,
          sim: turn.sim ?? null,
          partnerNote: turn.partner_note ?? null,
          partnerUrl: lastPartnerUrl,
          bgm: lastBgm,
          bgmReason: lastBgmReason,
        });
      }
    } else {
      // 攻略対象の立ち絵は生成失敗ターンで欠けうるため、直前の1枚を引き継ぐ
      let lastPartnerUrl = activeRun.opening_partner_portrait_url ?? null;
      let lastBgm: AdventureBgmKey = activeRun.opening_bgm ?? "daily";
      let lastBgmReason: string | null = activeRun.opening_bgm_reason ?? null;
      if (activeRun.opening_portrait_url) {
        list.push({
          key: "opening",
          turnNumber: 0,
          imageUrl: activeRun.opening_portrait_url,
          kind: "portrait",
          backgroundUrl: runBackground,
          portraitUrl: activeRun.opening_portrait_url,
          portraitStatus: null,
          sceneUrl: null,
          userInput: null,
          inputKind: null,
          narrative: activeRun.opening_narrative,
          location: null,
          sim: activeRun.opening_sim ?? null,
          partnerNote: null,
          partnerUrl: lastPartnerUrl,
          bgm: lastBgm,
          bgmReason: lastBgmReason,
        });
      }
      for (const turn of activeRun.turns) {
        // 画像の無いターンもBGMは進むため、continue より前に引き継ぐ。
        // 理由はキー更新時だけ取り込み、キーとの食い違いを作らない
        if (turn.bgm) {
          lastBgm = turn.bgm;
          lastBgmReason = turn.bgm_reason ?? null;
        }
        if (!turn.portrait_image_url) continue;
        lastPartnerUrl = turn.partner_portrait_url ?? lastPartnerUrl;
        list.push({
          key: turn.id,
          turnNumber: turn.turn_number,
          imageUrl: turn.portrait_image_url,
          kind: "portrait",
          // romance は現在地・時間帯ごとに背景が変わるため、その手番の1枚を使う
          backgroundUrl: turn.background_image_url ?? runBackground,
          portraitUrl: turn.portrait_image_url,
          portraitStatus: turn.portrait_status,
          sceneUrl: null,
          userInput: turn.user_input,
          inputKind: turn.input_kind,
          narrative: turn.narrative,
          location: turn.location,
          sim: turn.sim ?? null,
          partnerNote: turn.partner_note ?? null,
          partnerUrl: lastPartnerUrl,
          bgm: lastBgm,
          bgmReason: lastBgmReason,
        });
      }
    }
    return list;
  }, [activeRun]);

  // 新しいターン到着・画像再生成時は自動的に最新表示へ復帰する
  // biome-ignore lint/correctness/useExhaustiveDependencies: turn_count/current_image_url の変化を検知するための依存
  useEffect(() => {
    setSelectedFrameIndex(null);
  }, [activeRun?.turn_count, activeRun?.current_image_url]);

  useEffect(() => {
    if (frames.length === 0) return;
    turnStripEndRef.current?.scrollIntoView({
      block: "nearest",
      inline: "end",
    });
  }, [frames.length]);

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

  // セリフ読み上げ(AivisSpeech)。設定画面の TTS が有効なときだけ動く
  const voice = useAdventureVoice({
    available: settingsState.ttsEnabled,
    speakerId:
      settingsState.ttsStyleId?.trim() ||
      settingsState.ttsSpeakerId?.trim() ||
      null,
    engineDir: settingsState.ttsEngineDir,
    useGpu: settingsState.ttsUseGpu,
  });
  const { canSpeak: voiceCanSpeak, speak: voiceSpeak } = voice;
  const voicePlaying = voice.status === "playing";
  useEffect(() => {
    setBgmDucked(voicePlaying);
  }, [voicePlaying, setBgmDucked]);

  // run が変わったら行動モードへ戻す
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeRun.id の変化を検知して行動モードへ戻すための依存
  useEffect(() => {
    setActionMode("act");
  }, [activeRun?.id]);

  // 読み上げ(1): 新しい手番が届いたら攻略対象のセリフだけを読む。
  // 初回ロード・run 切替では読まない(その時点の最新手番を控えるだけ)
  const spokenTurnRef = useRef<{ runId: string; turnId: string | null } | null>(
    null,
  );
  useEffect(() => {
    if (!activeRun) return;
    const latest = activeRun.turns.at(-1) ?? null;
    const previous = spokenTurnRef.current;
    spokenTurnRef.current = { runId: activeRun.id, turnId: latest?.id ?? null };
    if (!previous || previous.runId !== activeRun.id) return;
    if (!latest || previous.turnId === latest.id) return;
    if (activeRun.preset !== "romance" || !voiceCanSpeak) return;
    const name = activeRun.sim?.partner_name?.trim() ?? "";
    const text = joinForSpeech(partnerLines(latest.narrative, name));
    if (text) void voiceSpeak(text, `turn:${latest.id}`);
  }, [activeRun, voiceCanSpeak, voiceSpeak]);

  // 読み上げ(2): トークの返答が確定したら、その返答を読む
  const spokenTalkRef = useRef<{
    runId: string;
    entryId: string | null;
  } | null>(null);
  useEffect(() => {
    if (!activeRun) return;
    const lastPartner =
      [...(activeRun.talk_log ?? [])]
        .reverse()
        .find((entry) => entry.role === "partner") ?? null;
    const previous = spokenTalkRef.current;
    spokenTalkRef.current = {
      runId: activeRun.id,
      entryId: lastPartner?.id ?? null,
    };
    if (!previous || previous.runId !== activeRun.id) return;
    if (!lastPartner || previous.entryId === lastPartner.id) return;
    if (!voiceCanSpeak) return;
    const text = stripStageDirections(lastPartner.text);
    if (text) void voiceSpeak(text, `talk:${lastPartner.id}`);
  }, [activeRun, voiceCanSpeak, voiceSpeak]);

  // トークスレッドは常に末尾(最新の返答)を見せる
  const talkLogLength = activeRun?.talk_log?.length ?? 0;
  // biome-ignore lint/correctness/useExhaustiveDependencies: talk_log の件数と下書きの変化で末尾へスクロールする
  useEffect(() => {
    const node = talkThreadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [talkLogLength, talkDraft, pendingTalkInput]);

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

  const portraitSource = useMemo(() => {
    // 対面会話モードでは主人公の立ち絵をステージに出さない
    if (
      !activeRun ||
      activeRun.enable_composite_scene ||
      (activeRun.preset === "romance" && activeRun.companion_mode)
    ) {
      return null;
    }
    if (selectedFrameIndex !== null) {
      return (
        frames[selectedFrameIndex]?.imageUrl ?? activeRun.portrait_image_url
      );
    }
    return activeRun.portrait_image_url ?? activeRun.opening_portrait_url;
  }, [activeRun, frames, selectedFrameIndex]);
  // 生成画像の白背景はわずかに灰色に振れるため、既定より広めの許容差で抜く。
  const { url: transparentPortraitUrl } = useTransparentImage(
    portraitSource,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const { url: transparentResultUrl } = useTransparentImage(
    activeRun?.enable_composite_scene ? null : activeRun?.portrait_image_url,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  // romance 非合成モードの攻略対象立ち絵。過去フレーム閲覧中はその手番の1枚を表示する
  const stagePartnerSource =
    activeRun?.preset === "romance" &&
    (!activeRun?.enable_composite_scene || activeRun?.companion_mode)
      ? selectedFrameIndex !== null
        ? (frames[selectedFrameIndex]?.partnerUrl ?? null)
        : (activeRun?.partner_portrait_url ?? null)
      : null;
  const { url: transparentPartnerUrl } = useTransparentImage(
    stagePartnerSource,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const toggleProtagonistDock = useCallback(() => {
    setProtagonistDockOpen((current) => {
      const next = !current;
      try {
        localStorage.setItem(PROTAGONIST_DOCK_STORAGE_KEY, String(next));
      } catch {
        // プライベートモード等で保存できなくても表示自体は切り替える
      }
      return next;
    });
  }, []);

  // 主人公ドックは常に最新状態を見せる。過去フレーム閲覧中でも
  // 追従しないよう、ステージ用の portraitSource とは別に最新分を解決する。
  const { url: currentPortraitUrl } = useTransparentImage(
    activeRun?.portrait_image_url ?? activeRun?.opening_portrait_url ?? null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  // 攻略対象も同じく最新分。合成モードでもドックには並べる
  const { url: currentPartnerDockUrl } = useTransparentImage(
    activeRun?.preset === "romance"
      ? (activeRun?.partner_portrait_url ??
          activeRun?.opening_partner_portrait_url ??
          null)
      : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );

  const lightboxFrame =
    lightboxIndex !== null ? frames[lightboxIndex] : undefined;
  const lightboxOpen = lightboxFrame !== undefined;
  // タブ的なチップ列なので、モーダルを開いた時点で選択中のチップへ
  // キーボードフォーカスを移し、そのまま操作できるようにする
  useEffect(() => {
    if (!lightboxOpen) return;
    lightboxViewsRef.current
      ?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]')
      ?.focus();
  }, [lightboxOpen]);
  // romance のターン詳細用。開幕フレーム(手番0)には日付が無い。
  // 導出はサーバの scene_day/scene_slot に一本化し、HUD と食い違わせない
  const lightboxDaySlot = frameDaySlot(lightboxFrame);
  const canShowBackground = Boolean(lightboxFrame?.backgroundUrl);
  const canShowPortrait = Boolean(lightboxFrame?.portraitUrl);
  // romance: そのフレーム時点の攻略対象立ち絵があれば過去手番でも切替可能
  const canShowPartner =
    activeRun?.preset === "romance" && Boolean(lightboxFrame?.partnerUrl);
  // 非合成モードのシーン表示は、ステージと同じく背景に白抜きの立ち絵を重ねる。
  // 概要ビューは画像をシーンのまま維持し、右側の詳細だけを差し替える
  const needsComposite =
    (lightboxView === "scene" || lightboxView === "overview") &&
    (lightboxFrame?.kind === "portrait" || lightboxFrame?.kind === "partner") &&
    Boolean(lightboxFrame.backgroundUrl);
  // ステージ用の transparentPortraitUrl はモーダルと別フレームを指しうるので流用しない。
  // 同一 src なら utils/imageAlpha のモジュールキャッシュに当たるため追加コストは無い。
  const { url: lightboxPortraitUrl } = useTransparentImage(
    needsComposite ? lightboxFrame?.portraitUrl : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const { url: lightboxPartnerUrl } = useTransparentImage(
    needsComposite && canShowPartner ? lightboxFrame?.partnerUrl : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );

  // 実進捗が取れないため、サブ工程statusと見なし所要時間で進捗バーを描く。
  // narrativeフェーズはテキスト自体が進捗になるため対象外（スピナー維持）。
  const enableCompositeScene = activeRun?.enable_composite_scene ?? false;
  const isRomancePreset = activeRun?.preset === "romance";
  // 対面会話モード: 主人公立ち絵と合成シーンの工程は走らない
  const companionActive = isRomancePreset && Boolean(activeRun?.companion_mode);
  // 対面会話モードで 3D モデルを表示中は攻略対象の立ち絵を毎ターン描かない
  const avatarActive =
    companionActive &&
    Boolean(activeRun?.companion_avatar_url) &&
    !companionAvatarFailed;
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
  const phaseLabel = phaseStep
    ? t(`adventure.phaseStep.${phaseStep.step}`)
    : t(`adventure.phase.${phase ?? "narrative"}`);
  const isViewingPast = selectedFrameIndex !== null;
  // 対面会話モード(romance): 背景の上に攻略対象の立ち絵だけを置く
  const isCompanion =
    activeRun.preset === "romance" && Boolean(activeRun.companion_mode);
  const isCompositeMode = activeRun.enable_composite_scene && !isCompanion;
  // 生成時間の見積もりと「テキストのみ」告知は同じ設定から導く
  const playImageSettings = {
    preset: activeRun.preset,
    enableCompositeScene: activeRun.enable_composite_scene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn: drawPartnerEveryTurn && !avatarActive,
    companionMode: isCompanion,
  };
  const effectiveIndex =
    selectedFrameIndex ?? (frames.length > 0 ? frames.length - 1 : -1);
  const selectedFrame =
    effectiveIndex >= 0 ? frames[effectiveIndex] : undefined;
  const backgroundUrl =
    activeRun.background_image_url ?? activeRun.current_image_url;
  const displayedImageUrl = isCompanion
    ? isViewingPast
      ? (selectedFrame?.backgroundUrl ?? backgroundUrl)
      : backgroundUrl
    : isCompositeMode
      ? isViewingPast
        ? (selectedFrame?.imageUrl ?? activeRun.current_image_url)
        : activeRun.current_image_url
      : backgroundUrl;
  const displayedPortraitUrl = transparentPortraitUrl;

  // ターンストリップ専用。モーダルの送りはここを通さない
  const goToFrame = (index: number) => {
    if (index < 0 || index >= frames.length) return;
    setSelectedFrameIndex(index === frames.length - 1 ? null : index);
  };

  // モーダル内だけを動かす。前後送りと閉じてからの開き直しのどちらも
  // 直前に見ていたタブを引き継ぎ(タブ選択の復元)、
  // 送り先に存在しないタブへ着地しないようシーンへ戻す
  const openLightboxFrame = (
    index: number,
    view?: "scene" | "background" | "portrait" | "partner" | "overview",
  ) => {
    if (index < 0 || index >= frames.length) return;
    const target = frames[index];
    const requested = view ?? lightboxView;
    const supported =
      requested === "partner"
        ? Boolean(target.partnerUrl)
        : requested === "portrait"
          ? Boolean(target.portraitUrl)
          : requested === "background"
            ? Boolean(target.backgroundUrl)
            : true;
    setLightboxIndex(index);
    setLightboxView(supported ? requested : "scene");
  };

  const lightboxImageUrl =
    lightboxView === "partner"
      ? (lightboxFrame?.partnerUrl ?? null)
      : lightboxView === "portrait"
        ? (lightboxFrame?.portraitUrl ?? null)
        : lightboxView === "background"
          ? (lightboxFrame?.backgroundUrl ?? null)
          : (lightboxFrame?.sceneUrl ??
            lightboxFrame?.backgroundUrl ??
            lightboxFrame?.imageUrl ??
            null);

  const latestTurn = activeRun.turns.at(-1) ?? null;
  const isStreamingNarrative = pendingUserInput !== null;
  const activeNarrative = isStreamingNarrative
    ? streamingNarrative
    : isViewingPast
      ? (selectedFrame?.narrative ?? activeRun.opening_narrative)
      : (latestTurn?.narrative ?? activeRun.opening_narrative);
  const activeAction = isStreamingNarrative
    ? pendingUserInput
    : isViewingPast
      ? selectedFrame?.userInput
      : latestTurn?.user_input;
  const activeLocation = isViewingPast
    ? selectedFrame?.location
    : (latestTurn?.location ?? activeRun.visual_state?.location);
  const availableChoices = activeRun.choices.filter(
    (choice) => choice.label.trim().length > 0,
  );
  const completedMilestones = new Set(activeRun.completed_milestones);
  // 「現実改変：〜」で宣言され、以降の判定に効いている世界ルール。
  // romance では「付与した属性」として表示する
  const realityRules = activeRun.reality_rules ?? [];
  // romance の公開シミュ状態。他プリセットでは null
  const sim = activeRun.preset === "romance" ? (activeRun.sim ?? null) : null;
  const cast = activeRun.visual_state?.main_characters ?? [];
  // 攻略対象の服装は sim ではなく現在の場面側に載る。名前の部分一致で引く
  // (バックエンドの _romance_partner_visual_entry と同じ突合)
  const partnerName = sim?.partner_name?.trim() ?? "";
  const partnerClothing = partnerName
    ? (cast.find((member) => {
        const name = member.name.trim();
        // 空名エントリは partnerName.includes("") で誤ヒットするため除く
        return (
          name !== "" &&
          (name.includes(partnerName) || partnerName.includes(name))
        );
      })?.clothing ?? "")
    : "";
  const resultImageUrl = isCompositeMode
    ? (activeRun.current_image_url ?? activeRun.portrait_image_url)
    : (transparentResultUrl ?? activeRun.current_image_url);
  const turnRatio =
    activeRun.max_turns > 0
      ? Math.round((activeRun.remaining_turns / activeRun.max_turns) * 100)
      : 0;
  // HUD は「今ステージに映っている場面の枠」を出す。過去フレーム閲覧中は
  // そのフレームの枠に追従させ、ライトボックスの表示と一致させる。
  // 次に行動する枠(sim.day/slot)は tooltip 側で補う。
  const stageDaySlot = frameDaySlot(
    isViewingPast ? selectedFrame : frames[frames.length - 1],
  ) ?? { day: sim?.day ?? 1, slot: sim?.slot ?? "day" };
  const stagePortraitFailed =
    !isCompanion &&
    (isViewingPast ? selectedFrame : frames[frames.length - 1])
      ?.portraitStatus === "failed";
  // トークモード(romance): 行動パネルを会話スレッドに切り替える
  const talkMode = Boolean(sim) && actionMode === "talk";
  const playerDisplayName = sim?.player_name?.trim() || t("adventure.talk.you");
  const currentTalkEntries = (activeRun.talk_log ?? []).filter(
    (entry) => entry.after_turn === activeRun.turn_count,
  );
  const lastPartnerTalk =
    [...(activeRun.talk_log ?? [])]
      .reverse()
      .find((entry) => entry.role === "partner") ?? null;
  // 🔊 の再読み上げ対象。トーク中は最新の返答、それ以外は表示中フレームのセリフ
  const voiceReplayText =
    talkMode && lastPartnerTalk
      ? stripStageDirections(lastPartnerTalk.text)
      : joinForSpeech(partnerLines(activeNarrative, partnerName));
  const voiceReplayKey =
    talkMode && lastPartnerTalk
      ? `talk:${lastPartnerTalk.id}`
      : `frame:${selectedFrame?.key ?? "latest"}`;
  const voiceReplayActive =
    voice.currentKey === voiceReplayKey && voice.status !== "idle";
  // 3D モデルの表情・身振り。トーク中は最新の返答、それ以外は表示中フレームの値
  const avatarExpression: AvatarExpressionKey | null =
    talkMode && lastPartnerTalk
      ? normalizeAvatarExpression(lastPartnerTalk.expression)
      : (selectedFrame?.partnerExpression ?? null);
  const avatarGesture: AvatarGestureKey | null =
    talkMode && lastPartnerTalk
      ? normalizeAvatarGesture(lastPartnerTalk.gesture)
      : (selectedFrame?.partnerGesture ?? null);
  // 身振りの再生トリガ。読み上げ可能なら声の開始(到着・🔊再生)に合わせ、
  // 読み上げ不可ならセリフ/フレームの切り替わりで再生する
  const avatarGestureKey = voiceCanSpeak
    ? (voice.status === "loading" || voice.status === "playing") &&
      voice.currentKey
      ? voice.currentKey
      : null
    : voiceReplayKey;
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
    setLightboxIndex(null);
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
          <div
            className={`adventure-hud${sim ? " adventure-hud--romance" : ""}`}
          >
            <button
              type="button"
              className="adventure-hud__back"
              onClick={() => navigate("/adventure")}
              aria-label={t("adventure.back")}
            >
              ←
            </button>
            <div className="adventure-hud__title">
              <p>{activeRun.title}</p>
              <h1 title={activeRun.objective}>
                <b>{t("adventure.goal")}</b>
                <span>{activeRun.objective}</span>
              </h1>
            </div>
            {(activeLocation || currentBgm) && (
              <div className="adventure-hud__location-stack">
                {activeLocation && (
                  <span
                    className="adventure-hud__location"
                    title={activeLocation}
                  >
                    <b>{t("adventure.currentLocation")}</b>
                    <span>{activeLocation}</span>
                  </span>
                )}
                {currentBgm && (
                  <button
                    type="button"
                    className={`adventure-hud__bgm-chip${
                      hudPanel === "bgm" ? " is-open" : ""
                    }`}
                    aria-expanded={hudPanel === "bgm"}
                    title={t("adventure.bgm.chipHint")}
                    onClick={() =>
                      setHudPanel((current) =>
                        current === "bgm" ? null : "bgm",
                      )
                    }
                  >
                    <span aria-hidden>♪</span>
                    <span>{currentBgm.key}</span>
                  </button>
                )}
              </div>
            )}
            <div className="adventure-hud__metrics">
              {sim && isCompanion ? (
                // 対面会話モード: 昼夜の枠が無いのでターン数(1ターン=1往復)を出す
                <HudTile
                  className="adventure-hud__day is-day"
                  title={
                    stageEpilogue
                      ? t("adventure.epilogueTurnsHint")
                      : t("adventure.companion.turnCounterHint", {
                          turn: activeRun.turn_count,
                          max: activeRun.max_turns,
                        })
                  }
                  label={t("adventure.companion.turnLabel")}
                  value={
                    stageEpilogue ? (
                      t("adventure.epilogueLabel")
                    ) : (
                      <>
                        {activeRun.turn_count}
                        <i>/{activeRun.max_turns}</i>
                      </>
                    )
                  }
                  gaugeRatio={stageEpilogue ? null : turnRatio}
                  badge={
                    stageEpilogue
                      ? null
                      : t("adventure.companion.turnsLeft", {
                          count: activeRun.remaining_turns,
                        })
                  }
                  badgeClassName="adventure-hud__slot is-day"
                />
              ) : sim ? (
                // エピローグでは期限が無いため「N日目」の開放表示に切り替え、
                // 残りターンのゲージも出さない
                <HudTile
                  className={`adventure-hud__day is-${stageDaySlot.slot}`}
                  title={
                    stageEpilogue
                      ? t("adventure.romance.dayCounterEpilogueHint")
                      : t("adventure.romance.dayCounterHint", {
                          day: sim.day,
                          total: sim.total_days,
                          slot: t(`adventure.romance.slot.${sim.slot}`),
                        })
                  }
                  label={t("adventure.romance.day")}
                  value={
                    stageEpilogue ? (
                      t("adventure.romance.dayOpen", { day: stageDaySlot.day })
                    ) : (
                      <>
                        {stageDaySlot.day}
                        <i>/{sim.total_days}</i>
                      </>
                    )
                  }
                  gaugeRatio={stageEpilogue ? null : turnRatio}
                  badge={t(`adventure.romance.slot.${stageDaySlot.slot}`)}
                  badgeClassName={`adventure-hud__slot is-${stageDaySlot.slot}`}
                />
              ) : isEpilogue ? (
                <div
                  className="adventure-hud__turns"
                  title={t("adventure.epilogueTurnsHint")}
                >
                  <span>{t("adventure.epilogueLabel")}</span>
                  <strong>
                    {t("adventure.epilogueTurns", {
                      turn: activeRun.turn_count,
                    })}
                  </strong>
                </div>
              ) : (
                <div
                  className="adventure-hud__turns"
                  title={t("adventure.remaining")}
                >
                  <span>{t("adventure.remaining")}</span>
                  <strong>
                    {activeRun.remaining_turns}
                    <i>/{activeRun.max_turns}</i>
                  </strong>
                  <span className="adventure-hud__gauge" aria-hidden>
                    <i style={{ width: `${turnRatio}%` }} />
                  </span>
                </div>
              )}
              {sim && (
                <>
                  <HudTile
                    className={`adventure-hud__affection is-${sim.stage}`}
                    title={t(`adventure.romance.stages.${sim.stage}`)}
                    label={t("adventure.romance.affection")}
                    value={
                      <>
                        <svg
                          className="adventure-hud__heart"
                          viewBox="0 0 24 24"
                          aria-hidden
                        >
                          <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                        </svg>
                        {sim.affection}
                        <i>/100</i>
                      </>
                    }
                    gaugeRatio={sim.affection}
                    badge={t(`adventure.romance.stages.${sim.stage}`)}
                    badgeClassName="adventure-hud__stage"
                  />
                  <HudTile
                    className="adventure-hud__money"
                    title={t("adventure.romance.money")}
                    label={t("adventure.romance.money")}
                    value={sim.money.toLocaleString()}
                    gaugeRatio={null}
                    badge={t("adventure.romance.moneyUnit")}
                  />
                </>
              )}
              {/* V5 利用上限。通常ゲームHUDと同じく Anlas の左隣に置く */}
              {hudUsage &&
                (sim ? (
                  <HudTile
                    className={`adventure-hud__usage-tile${
                      hudUsageExhausted ? " is-warning" : ""
                    }`}
                    title={t("gameplay.novelaiUsageTooltip", {
                      percent: hudUsage.percent,
                    })}
                    label={t("gameplay.novelaiUsageLabel")}
                    value={
                      hudUsageExhausted
                        ? t("gameplay.novelaiUsageExhausted")
                        : `${hudUsage.percent}%`
                    }
                    gaugeRatio={hudUsagePercent}
                    badge={null}
                  />
                ) : (
                  <div
                    className={`adventure-hud__usage${
                      hudUsageExhausted ? " is-warning" : ""
                    }`}
                    title={t("gameplay.novelaiUsageTooltip", {
                      percent: hudUsage.percent,
                    })}
                  >
                    <span>{t("gameplay.novelaiUsageLabel")}</span>
                    <strong>
                      {hudUsageExhausted
                        ? t("gameplay.novelaiUsageExhausted")
                        : `${hudUsage.percent}%`}
                    </strong>
                    <span className="adventure-hud__gauge" aria-hidden>
                      <i style={{ width: `${hudUsagePercent}%` }} />
                    </span>
                  </div>
                ))}
              {(activeRun.use_precise_reference || runIsV5) &&
                anlasBalance &&
                (sim ? (
                  // romance では他のメトリクスと同じ共通タイルで並べる。
                  // 精密参照ON時 / V5実効時だけ出るので、バッジで理由を示す
                  <HudTile
                    className="adventure-hud__anlas-tile"
                    title={t("adventure.anlasDetail", {
                      fixed: anlasBalance.fixedAnlas.toLocaleString(),
                      purchased: anlasBalance.purchasedAnlas.toLocaleString(),
                    })}
                    label="Anlas"
                    value={anlasBalance.totalAnlas.toLocaleString()}
                    gaugeRatio={null}
                    badge={
                      runIsV5
                        ? t("adventure.anlasBadgeV5")
                        : t("adventure.anlasBadge")
                    }
                  />
                ) : (
                  <div
                    className="adventure-hud__anlas"
                    title={t("adventure.anlasDetail", {
                      fixed: anlasBalance.fixedAnlas.toLocaleString(),
                      purchased: anlasBalance.purchasedAnlas.toLocaleString(),
                    })}
                  >
                    <span>Anlas</span>
                    <strong>{anlasBalance.totalAnlas.toLocaleString()}</strong>
                  </div>
                ))}
              {/* OpenRouter利用時は従量課金なので累計API料金を常時見せる。
                  通常ゲーム画面のコストバーと同じ累計値(SettingsContext)を表示する */}
              {settingsState.showCost &&
                (sim ? (
                  <HudTile
                    className="adventure-hud__cost-tile"
                    title={t("gameplay.apiCost")}
                    label={t("gameplay.apiCost")}
                    value={`$${settingsState.totalCost.toFixed(4)}`}
                    gaugeRatio={null}
                    badge={null}
                  />
                ) : (
                  <div
                    className="adventure-hud__cost"
                    title={t("gameplay.apiCost")}
                  >
                    <span>{t("gameplay.apiCost")}</span>
                    <strong>${settingsState.totalCost.toFixed(4)}</strong>
                  </div>
                ))}
              {activeRun.milestones.length > 0 && (
                <button
                  type="button"
                  className={`adventure-hud__chip${hudPanel === "milestones" ? " is-open" : ""}`}
                  aria-expanded={hudPanel === "milestones"}
                  onClick={() =>
                    setHudPanel((current) =>
                      current === "milestones" ? null : "milestones",
                    )
                  }
                >
                  <span>{t("adventure.milestones")}</span>
                  <strong>
                    {completedMilestones.size}
                    <i>/{activeRun.milestones.length}</i>
                  </strong>
                </button>
              )}
              <button
                type="button"
                className={`adventure-hud__chip${hudPanel === "clues" ? " is-open" : ""}`}
                aria-expanded={hudPanel === "clues"}
                disabled={activeRun.clues.length === 0}
                onClick={() =>
                  setHudPanel((current) =>
                    current === "clues" ? null : "clues",
                  )
                }
              >
                <span>
                  {t(sim ? "adventure.romance.hints" : "adventure.clues")}
                </span>
                <strong>{activeRun.clues.length}</strong>
              </button>
              {realityRules.length > 0 && (
                <button
                  type="button"
                  className={`adventure-hud__chip${hudPanel === "realityRules" ? " is-open" : ""}`}
                  aria-expanded={hudPanel === "realityRules"}
                  onClick={() =>
                    setHudPanel((current) =>
                      current === "realityRules" ? null : "realityRules",
                    )
                  }
                >
                  <span>
                    {t(
                      sim
                        ? "adventure.romance.grantedAttributes"
                        : "adventure.realityRules",
                    )}
                  </span>
                  <strong>{realityRules.length}</strong>
                </button>
              )}
              <button
                type="button"
                className={`adventure-hud__chip adventure-hud__chip--speech${
                  hudPanel === "speechStyle" ? " is-open" : ""
                }`}
                aria-expanded={hudPanel === "speechStyle"}
                onClick={() =>
                  setHudPanel((current) =>
                    current === "speechStyle" ? null : "speechStyle",
                  )
                }
              >
                <span>{t("adventure.speechStyleChip")}</span>
                {/* 自由入力の全文はポップオーバーで読めるため、チップは分類名だけ出す */}
                <strong>
                  {t(`adventure.speechStyles.${activeRun.player_speech_style}`)}
                </strong>
              </button>
              <button
                type="button"
                className={`adventure-hud__chip adventure-hud__chip--protagonist${
                  protagonistDockOpen ? " is-open" : ""
                }`}
                aria-pressed={protagonistDockOpen}
                title={t("adventure.protagonistToggleHint")}
                disabled={!currentPortraitUrl && !activeRun.visual_state}
                onClick={toggleProtagonistDock}
              >
                <span>{t("adventure.protagonist")}</span>
                {currentPortraitUrl ? (
                  <img
                    className="adventure-hud__chip-thumb"
                    src={currentPortraitUrl}
                    alt=""
                  />
                ) : (
                  <strong>-</strong>
                )}
              </button>
            </div>
            {hudPanel && (
              <div
                className="adventure-hud__popover"
                role="dialog"
                aria-label={t(
                  // adventure.bgm は i18n 上オブジェクトのため専用キーを使う
                  hudPanel === "bgm"
                    ? "adventure.bgm.panelTitle"
                    : `adventure.${hudPanel}`,
                )}
              >
                {hudPanel === "speechStyle" ? (
                  <>
                    <p className="adventure-hud__note">
                      {t("adventure.speechStyleHint")}
                    </p>
                    <dl className="adventure-hud__facts">
                      <div>
                        <dt>{t("adventure.protagonist")}</dt>
                        <dd>
                          {speechStyleLabel(
                            activeRun.player_speech_style,
                            activeRun.player_speech_custom,
                            t,
                          )}
                        </dd>
                      </div>
                      {sim && (
                        <div>
                          <dt>{sim.partner_name}</dt>
                          <dd>
                            {sim.partner_speech_style ||
                              t("adventure.romance.partnerSpeechStyleAuto")}
                          </dd>
                        </div>
                      )}
                    </dl>
                    <button
                      type="button"
                      className="adventure-hud__panel-action"
                      disabled={!canActOnRun(activeRun)}
                      onClick={() => {
                        setHudPanel(null);
                        setSpeechModalOpen(true);
                      }}
                    >
                      {t("adventure.speechStyleManager.manage")}
                    </button>
                  </>
                ) : hudPanel === "bgm" ? (
                  <>
                    <p className="adventure-hud__bgm-key">
                      <span aria-hidden>♪</span>
                      <strong>{currentBgm?.key ?? "daily"}</strong>
                    </p>
                    <p className="adventure-hud__note">
                      {t("adventure.bgm.reasonLabel")}
                    </p>
                    <p className="adventure-hud__bgm-reason">
                      {currentBgm?.reason ?? t("adventure.bgm.noReason")}
                    </p>
                  </>
                ) : hudPanel === "milestones" ? (
                  <ul className="adventure-hud__milestones">
                    {activeRun.milestones.map((milestone) => {
                      const done = completedMilestones.has(milestone.id);
                      return (
                        <li
                          key={milestone.id}
                          className={done ? "is-done" : ""}
                        >
                          <span aria-hidden>{done ? "✓" : "・"}</span>
                          {milestone.label}
                          {done && <em>{t("adventure.milestoneDone")}</em>}
                        </li>
                      );
                    })}
                  </ul>
                ) : hudPanel === "realityRules" ? (
                  <>
                    <p className="adventure-hud__note">
                      {t(
                        sim
                          ? "adventure.romance.grantedAttributesHint"
                          : "adventure.realityRulesHint",
                      )}
                    </p>
                    <ul className="adventure-hud__clues">
                      {realityRules.map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      className="adventure-hud__panel-action"
                      disabled={!canActOnRun(activeRun)}
                      onClick={() => {
                        setHudPanel(null);
                        setAttributeModalOpen(true);
                      }}
                    >
                      {t(
                        sim
                          ? "adventure.romance.attribute.manage"
                          : "adventure.realityRuleManager.manage",
                      )}
                    </button>
                  </>
                ) : (
                  <ul className="adventure-hud__clues">
                    {activeRun.clues.map((clue) => (
                      <li key={clue}>{clue}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/*
            登場人物と主人公ドックは同じ左レールに積む。別々の絶対配置にすると
            ドックの高さ次第で重なるため、レール内で上下に振り分ける。
          */}
          <div className="adventure-left-rail" aria-hidden={false}>
            {cast.length > 0 && (
              <ul className="adventure-cast" aria-label={t("adventure.cast")}>
                {cast.map((member) => (
                  <li key={member.name}>
                    <strong>{member.name}</strong>
                    {member.action && <span>{member.action}</span>}
                  </li>
                ))}
              </ul>
            )}
            {protagonistDockOpen && (
              <aside
                className="adventure-protagonist-dock"
                aria-label={t("adventure.protagonist")}
              >
                <div className="adventure-protagonist-dock__head">
                  <strong>
                    {sim?.player_name || t("adventure.protagonist")}
                  </strong>
                  <button
                    type="button"
                    className="adventure-protagonist-dock__close"
                    aria-label={t("adventure.protagonistHide")}
                    title={t("adventure.protagonistHide")}
                    onClick={toggleProtagonistDock}
                  >
                    ✕
                  </button>
                </div>
                {currentPortraitUrl && (
                  <button
                    type="button"
                    className="adventure-protagonist-dock__figure"
                    disabled={frames.length === 0}
                    title={t("adventure.viewFullScreen")}
                    onClick={() =>
                      openLightboxFrame(frames.length - 1, "portrait")
                    }
                  >
                    <img
                      src={currentPortraitUrl}
                      alt={t("adventure.portraitAlt")}
                    />
                  </button>
                )}
                <dl className="adventure-protagonist-dock__facts">
                  <div>
                    <dt>{t("adventure.protagonistAppearance")}</dt>
                    <dd>
                      {activeRun.visual_state?.appearance ||
                        t("adventure.protagonistUnknown")}
                    </dd>
                  </div>
                  <div>
                    <dt>{t("adventure.protagonistClothing")}</dt>
                    <dd>
                      {activeRun.visual_state?.clothing ||
                        t("adventure.protagonistUnknown")}
                    </dd>
                  </div>
                </dl>
                {sim && (
                  <div className="adventure-protagonist-dock__partner">
                    <div className="adventure-protagonist-dock__subhead">
                      <span>{t("adventure.partnerSection")}</span>
                      <strong>{sim.partner_name}</strong>
                    </div>
                    {currentPartnerDockUrl && (
                      <button
                        type="button"
                        className="adventure-protagonist-dock__figure"
                        disabled={frames.length === 0}
                        title={t("adventure.viewFullScreen")}
                        onClick={() =>
                          openLightboxFrame(frames.length - 1, "partner")
                        }
                      >
                        <img
                          src={currentPartnerDockUrl}
                          alt={t("adventure.romance.partnerPortraitAlt")}
                        />
                      </button>
                    )}
                    <dl className="adventure-protagonist-dock__facts">
                      <div>
                        <dt>{t("adventure.protagonistAppearance")}</dt>
                        <dd>
                          {sim.partner_appearance ||
                            t("adventure.protagonistUnknown")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("adventure.protagonistClothing")}</dt>
                        <dd>
                          {partnerClothing || t("adventure.protagonistUnknown")}
                        </dd>
                      </div>
                    </dl>
                  </div>
                )}
              </aside>
            )}
          </div>
          <section className="adventure-stage" aria-busy={isStageLoading}>
            <div
              className={`adventure-stage__frame ${isCompositeMode ? "is-composite" : "is-background"}`}
            >
              <button
                type="button"
                className="adventure-stage__image-button"
                onClick={() => openLightboxFrame(effectiveIndex)}
                disabled={frames.length === 0}
                aria-label={t("adventure.viewFullScreen")}
              >
                <img
                  className={isStageLoading ? "is-generating" : undefined}
                  src={displayedImageUrl}
                  alt={activeRun.title}
                />
              </button>
              <div className="adventure-stage__scrim" aria-hidden />
              {displayedPortraitUrl && (
                <img
                  key={displayedPortraitUrl}
                  className={`adventure-stage__portrait${
                    transparentPartnerUrl
                      ? " adventure-stage__portrait--paired"
                      : ""
                  }`}
                  src={displayedPortraitUrl}
                  alt={t("adventure.portraitAlt")}
                />
              )}
              {showAvatar && avatarUrl ? (
                <Suspense fallback={null}>
                  <CompanionAvatarStage
                    fileUrl={avatarUrl}
                    expression={avatarExpression}
                    gesture={avatarGesture}
                    gestureKey={avatarGestureKey}
                    getVoiceLevel={voice.getLevel}
                    onError={handleAvatarError}
                  />
                </Suspense>
              ) : (
                transparentPartnerUrl && (
                  <img
                    key={transparentPartnerUrl}
                    className={`adventure-stage__portrait ${
                      isCompanion
                        ? "adventure-stage__portrait--solo"
                        : "adventure-stage__portrait--partner"
                    }`}
                    src={transparentPartnerUrl}
                    alt={t("adventure.romance.partnerPortraitAlt")}
                  />
                )
              )}
              {isStageLoading && !isViewingPast && (
                <div className="adventure-stage__loading" role="status">
                  {progressSegments && progressActiveKey ? (
                    <span className="adventure-progressbar" aria-hidden>
                      <i
                        style={{
                          width: `${Math.round(stageProgress * 100)}%`,
                        }}
                      />
                    </span>
                  ) : (
                    <span className="adventure-stage__loading-spinner" />
                  )}
                  <strong>{phaseLabel}</strong>
                </div>
              )}
              {isViewingPast && (
                <div className="adventure-stage__past-banner">
                  <span>{t("adventure.turnStrip.viewingPast")}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedFrameIndex(null)}
                  >
                    {t("adventure.turnStrip.backToLatest")}
                  </button>
                  {canRewindHere && rewindTarget && (
                    <button
                      type="button"
                      className="adventure-stage__past-banner-rewind"
                      title={t("adventure.turnStrip.rewindHint")}
                      onClick={() => requestRewind(rewindTarget.turnNumber)}
                    >
                      {t("adventure.turnStrip.rewind")}
                    </button>
                  )}
                </div>
              )}
              {stagePortraitFailed && !isStageLoading && (
                <div className="adventure-stage__portrait-failed" role="status">
                  <span>{t("adventure.portraitFailed")}</span>
                  <button
                    type="button"
                    disabled={streaming || isViewingPast}
                    onClick={() =>
                      regenerateImage({
                        redraw_from_reference: true,
                        target: "portrait",
                      })
                    }
                  >
                    {t("adventure.portraitRetry")}
                  </button>
                </div>
              )}
              <button
                type="button"
                className="adventure-stage__regenerate"
                onClick={() => {
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
                disabled={streaming || talking || isViewingPast}
                title={t(
                  isCompanion
                    ? "adventure.regeneratePartnerPortrait"
                    : "adventure.regenerateImage",
                )}
                aria-label={t(
                  isCompanion
                    ? "adventure.regeneratePartnerPortrait"
                    : "adventure.regenerateImage",
                )}
              >
                ↻
              </button>
              <button
                type="button"
                className="adventure-stage__settings"
                onClick={() => {
                  setBgmSettingsOpen(false);
                  setImageSettingsOpen((current) => !current);
                }}
                title={t("adventure.imageSettings")}
                aria-label={t("adventure.imageSettings")}
                aria-expanded={imageSettingsOpen}
              >
                ⚙
              </button>
              <AdventureBgmControl
                muted={bgmMuted}
                volume={bgmVolume}
                autoplayBlocked={bgmAutoplayBlocked}
                open={bgmSettingsOpen}
                onToggleOpen={() => {
                  setImageSettingsOpen(false);
                  setBgmSettingsOpen((current) => !current);
                }}
                onMutedChange={setBgmMuted}
                onVolumeChange={setBgmVolume}
                voice={{
                  available: settingsState.ttsEnabled,
                  enabled: voice.enabled,
                  volume: voice.volume,
                  speed: voice.speed,
                  status: voice.status,
                  onEnabledChange: voice.setEnabled,
                  onVolumeChange: voice.setVolume,
                  onSpeedChange: voice.setSpeed,
                  onStop: voice.stop,
                }}
              />
              {imageSettingsOpen && (
                <div className="adventure-image-settings-popover">
                  {/* 各トグルの結果である所要時間は、スクロールしても見える先頭へ置く */}
                  <p className="adventure-turn-estimate">
                    {t("adventure.turnTimeEstimate", {
                      seconds: estimateAdventureTurnSeconds(playImageSettings),
                    })}
                  </p>
                  {isAdventureTurnTextOnly(playImageSettings) && (
                    <p className="adventure-turn-note">
                      {t(
                        activeRun.preset === "romance"
                          ? "adventure.turnImagesDisabledNoticeRomance"
                          : "adventure.turnImagesDisabledNotice",
                      )}
                    </p>
                  )}
                  {/* この run 専用のNovelAI画像モデル。次の画像生成から反映される */}
                  <label className="adventure-image-model-picker">
                    <span className="adventure-precise-toggle__info">
                      <strong>{t("adventure.imageModel")}</strong>
                      <small>
                        {t(
                          settingsState.imageProvider === "novelai"
                            ? "adventure.imageModelPlayHint"
                            : "adventure.imageModelOtherProviderHint",
                        )}
                      </small>
                    </span>
                    <select
                      value={activeRun.image_model_override ?? "default"}
                      disabled={streaming || settingsSaving}
                      onChange={(event) => {
                        const next = event.target.value;
                        setSettingsSaving(true);
                        void updateSettings({
                          use_precise_reference:
                            activeRun.use_precise_reference,
                          enable_composite_scene:
                            activeRun.enable_composite_scene,
                          image_model: next,
                        })
                          .catch(() => undefined)
                          .finally(() => setSettingsSaving(false));
                      }}
                    >
                      <option value="default">
                        {t("adventure.imageModelDefault")}
                      </option>
                      {ADVENTURE_IMAGE_MODEL_CHOICES.map((choice) => (
                        <option key={choice.value} value={choice.value}>
                          {choice.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {/* 対面会話モード(romance 専用)。次の手番から反映 */}
                  {activeRun.preset === "romance" && (
                    <label className="adventure-precise-toggle adventure-companion-toggle">
                      <span className="adventure-precise-toggle__info">
                        <strong>{t("adventure.companionMode")}</strong>
                        <small>{t("adventure.companionModePlayHint")}</small>
                      </span>
                      <input
                        type="checkbox"
                        className="adventure-precise-toggle__input"
                        checked={isCompanion}
                        disabled={streaming || settingsSaving}
                        onChange={(event) => {
                          const next = event.target.checked;
                          setSettingsSaving(true);
                          void updateSettings({
                            use_precise_reference:
                              activeRun.use_precise_reference,
                            enable_composite_scene:
                              activeRun.enable_composite_scene,
                            companion_mode: next,
                          })
                            .catch(() => undefined)
                            .finally(() => setSettingsSaving(false));
                        }}
                      />
                      <span className="adventure-precise-toggle__switch" />
                    </label>
                  )}
                  {/* 3D モデル(VRM)。対面会話モード OFF でも隠さず、文言で説明する */}
                  {activeRun.preset === "romance" && (
                    <label className="adventure-setup-turns adventure-setup-avatar">
                      <span className="adventure-setup-turns__label">
                        {t("adventure.avatar.selectLabel")}
                      </span>
                      <select
                        value={activeRun.companion_avatar_id ?? ""}
                        disabled={streaming || settingsSaving}
                        onChange={(event) => {
                          const next = event.target.value;
                          setSettingsSaving(true);
                          void updateSettings({
                            use_precise_reference:
                              activeRun.use_precise_reference,
                            enable_composite_scene:
                              activeRun.enable_composite_scene,
                            companion_avatar_id: next || "none",
                          })
                            .catch(() => undefined)
                            .finally(() => setSettingsSaving(false));
                        }}
                      >
                        <option value="">{t("adventure.avatar.none")}</option>
                        {activeRun.companion_avatar_id &&
                          !avatarModels.some(
                            (model) =>
                              model.id === activeRun.companion_avatar_id,
                          ) && (
                            <option
                              value={activeRun.companion_avatar_id}
                              disabled
                            >
                              {t("adventure.avatar.deletedModel")}
                            </option>
                          )}
                        {avatarModels.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.name}
                          </option>
                        ))}
                      </select>
                      <span className="adventure-setup-turns__hint">
                        {avatarModels.length === 0 ? (
                          <>
                            {t("adventure.avatar.noModelsHint")}{" "}
                            <Link to={ROUTES.SETTINGS}>
                              {t("adventure.avatar.registerLink")}
                            </Link>
                          </>
                        ) : isCompanion ? (
                          t("adventure.avatar.playHint")
                        ) : (
                          t("adventure.avatar.companionOffHint")
                        )}
                      </span>
                    </label>
                  )}
                  <label className="adventure-precise-toggle">
                    <span className="adventure-precise-toggle__info">
                      <strong>{t("adventure.preciseReference")}</strong>
                      {/* NovelAI以外では効果もAnlas消費もない旨、V5では非対応の旨を明示する */}
                      <small>
                        {t(
                          runIsV5
                            ? "adventure.preciseReferenceV5Hint"
                            : settingsState.imageProvider === "novelai"
                              ? "adventure.preciseReferencePlayHint"
                              : "adventure.preciseReferenceOtherProviderHint",
                        )}
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      className="adventure-precise-toggle__input"
                      checked={activeRun.use_precise_reference && !runIsV5}
                      disabled={streaming || settingsSaving || runIsV5}
                      onChange={(event) => {
                        const next = event.target.checked;
                        setSettingsSaving(true);
                        void updateSettings({
                          use_precise_reference: next,
                          enable_composite_scene:
                            activeRun.enable_composite_scene,
                        })
                          .catch(() => undefined)
                          .finally(() => setSettingsSaving(false));
                      }}
                    />
                    <span className="adventure-precise-toggle__switch" />
                  </label>
                  <label className="adventure-precise-toggle">
                    <span className="adventure-precise-toggle__info">
                      <strong>{t("adventure.enableCompositeScene")}</strong>
                      <small>
                        {t(
                          isCompanion
                            ? "adventure.enableCompositeSceneCompanionHint"
                            : "adventure.enableCompositeScenePlayHint",
                        )}
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      className="adventure-precise-toggle__input"
                      checked={activeRun.enable_composite_scene}
                      disabled={streaming || settingsSaving}
                      onChange={(event) => {
                        const next = event.target.checked;
                        setSettingsSaving(true);
                        void updateSettings({
                          use_precise_reference:
                            activeRun.use_precise_reference,
                          enable_composite_scene: next,
                        })
                          .catch(() => undefined)
                          .finally(() => setSettingsSaving(false));
                      }}
                    />
                    <span className="adventure-precise-toggle__switch" />
                  </label>
                  {/* 立ち絵の毎ターン描画は合成・精密参照の設定に関わらず効くため常に表示する */}
                  <label className="adventure-precise-toggle">
                    <span className="adventure-precise-toggle__info">
                      <strong>{t("adventure.drawPortraitEveryTurn")}</strong>
                      <small>
                        {t(
                          isCompanion
                            ? "adventure.drawPortraitEveryTurnCompanionHint"
                            : "adventure.drawPortraitEveryTurnHint",
                        )}
                      </small>
                    </span>
                    <input
                      type="checkbox"
                      className="adventure-precise-toggle__input"
                      checked={drawPortraitEveryTurn}
                      disabled={streaming}
                      onChange={(event) => {
                        const next = event.target.checked;
                        setDrawPortraitEveryTurn(next);
                        try {
                          localStorage.setItem(
                            DRAW_PORTRAIT_STORAGE_KEY,
                            String(next),
                          );
                        } catch {
                          // プライベートモード等で保存できなくても切り替え自体は有効
                        }
                      }}
                    />
                    <span className="adventure-precise-toggle__switch" />
                  </label>
                  {activeRun.preset === "romance" && (
                    <label className="adventure-precise-toggle">
                      <span className="adventure-precise-toggle__info">
                        <strong>{t("adventure.drawPartnerEveryTurn")}</strong>
                        <small>{t("adventure.drawPartnerEveryTurnHint")}</small>
                      </span>
                      <input
                        type="checkbox"
                        className="adventure-precise-toggle__input"
                        checked={drawPartnerEveryTurn}
                        disabled={streaming}
                        onChange={(event) => {
                          const next = event.target.checked;
                          setDrawPartnerEveryTurn(next);
                          try {
                            localStorage.setItem(
                              DRAW_PARTNER_STORAGE_KEY,
                              String(next),
                            );
                          } catch {
                            // プライベートモード等で保存できなくても切り替え自体は有効
                          }
                        }}
                      />
                      <span className="adventure-precise-toggle__switch" />
                    </label>
                  )}
                  {/* ENABLE_PROMPT_PREVIEW のときだけ出る確認用の入口 */}
                  {activeRun.enable_prompt_preview && (
                    <button
                      type="button"
                      className="adventure-hud__panel-action"
                      onClick={() => {
                        setImageSettingsOpen(false);
                        setPromptPreviewOpen(true);
                      }}
                    >
                      {t("adventure.promptPreview.open")}
                    </button>
                  )}
                </div>
              )}
            </div>
          </section>

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

          <section
            className={`adventure-messagebox${
              sim ? " adventure-messagebox--romance" : ""
            }${messageWindowHidden ? " is-hidden" : ""}`}
            aria-live="polite"
            inert={messageWindowHidden}
          >
            <div className="adventure-messagebox__meta">
              {sim && (
                <button
                  type="button"
                  className="adventure-messagebox__voice-button"
                  disabled={!voice.canSpeak || !voiceReplayText}
                  aria-pressed={voiceReplayActive}
                  aria-label={t("adventure.voice.replay")}
                  title={t(
                    voice.canSpeak
                      ? "adventure.voice.replayHint"
                      : "adventure.voice.disabledHint",
                  )}
                  onClick={() => {
                    if (voiceReplayActive) {
                      voice.stop();
                      return;
                    }
                    void voice.speak(voiceReplayText, voiceReplayKey);
                  }}
                >
                  🔊
                </button>
              )}
              <button
                type="button"
                className="adventure-messagebox__log-button"
                onClick={() => setLogOpen(true)}
                title={t("adventure.log.openHint")}
              >
                {t("adventure.log.open")}
              </button>
              <button
                type="button"
                className="adventure-messagebox__hide-button"
                onClick={() => setMessageWindowHidden(true)}
                title={t("adventure.window.hideHint")}
                aria-label={t("adventure.window.hide")}
                tabIndex={messageWindowHidden ? -1 : undefined}
              >
                ✕
              </button>
            </div>

            {activeAction && (
              <p className="adventure-messagebox__action">
                <span>{t("adventure.yourAction")}</span>
                {activeAction}
              </p>
            )}

            <div className="adventure-messagebox__text" ref={messageTextRef}>
              {sim ? (
                // romance は台本形式(名前「セリフ」)の行を話者付きで描く。
                // 名前付き行が無い本文はそのまま1段落になる
                <div className="adventure-messagebox__narrative">
                  <AdventureScriptText
                    text={activeNarrative}
                    speakers={[partnerName, playerDisplayName]}
                  />
                  {isStreamingNarrative && (
                    <span className="adventure-transcript__caret" />
                  )}
                </div>
              ) : (
                <p className="adventure-messagebox__narrative">
                  {activeNarrative}
                  {isStreamingNarrative && (
                    <span className="adventure-transcript__caret" />
                  )}
                </p>
              )}
              {streaming && !isStageLoading && (
                <div className="adventure-progress">
                  <span />
                  {phaseLabel}
                </div>
              )}
            </div>

            {canAct ? (
              <div className="adventure-controls">
                {isViewingPast ? (
                  // 過去の場面では行動UIを出さない。最新へ戻る導線はステージの過去バナーにある
                  <p className="adventure-controls__past-hint">
                    {t("adventure.viewingPastControlsHint")}
                  </p>
                ) : (
                  <>
                    <div className="adventure-controls__header">
                      {sim ? (
                        // romance: 行動(手番を消費) / トーク(消費しない会話)の切替
                        <div
                          className="adventure-segments adventure-segments--pair"
                          role="group"
                          aria-label={t("adventure.actionPanel.title")}
                        >
                          <button
                            type="button"
                            className={actionMode === "act" ? "is-active" : ""}
                            aria-pressed={actionMode === "act"}
                            onClick={() => setActionMode("act")}
                          >
                            {t("adventure.actionPanel.act")}
                          </button>
                          <button
                            type="button"
                            className={actionMode === "talk" ? "is-active" : ""}
                            aria-pressed={actionMode === "talk"}
                            title={t("adventure.actionPanel.talkHint")}
                            onClick={() => setActionMode("talk")}
                          >
                            {t("adventure.actionPanel.talk")}
                          </button>
                        </div>
                      ) : (
                        <span className="adventure-controls__title">
                          {t("adventure.actionPanel.title")}
                        </span>
                      )}
                      {!talkMode && (
                        <button
                          type="button"
                          className="adventure-choices__regenerate"
                          onClick={() => void regenerateChoices()}
                          disabled={streaming || talking}
                          title={t("adventure.regenerateChoices")}
                        >
                          {streaming && phase === "clue_check"
                            ? t("adventure.regeneratingChoices")
                            : t("adventure.regenerateChoices")}
                        </button>
                      )}
                    </div>

                    {/* 生成中は前ターンの選択肢が残留するため、無効化ではなく非表示にする */}
                    {!streaming && !talkMode && (
                      <div className="adventure-choices">
                        {availableChoices.map((choice, index) => (
                          <button
                            type="button"
                            key={choice.id}
                            title={choice.label}
                            onClick={() => submit(choice.label, "choice")}
                          >
                            <span className="adventure-choices__key">
                              {index + 1}
                            </span>
                            {choice.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {!streaming &&
                      !talkMode &&
                      availableChoices.length === 0 && (
                        <p className="adventure-choices__empty">
                          {t("adventure.emptyChoices")}
                        </p>
                      )}

                    {/* romance 専用の行動ボタン行。どの行動も1スロット消費する。
                    選択肢と同様、生成中は非表示にする */}
                    {!streaming && sim && !talkMode && (
                      <div className="adventure-romance-actions">
                        <button
                          type="button"
                          title={t("adventure.romance.workHint", {
                            job: sim.job.name,
                            wage: sim.job.wage.toLocaleString(),
                          })}
                          onClick={() =>
                            submit(
                              t("adventure.romance.workAction", {
                                job: sim.job.name,
                              }),
                              "work",
                            )
                          }
                        >
                          {t("adventure.romance.workButton")}
                        </button>
                        <button
                          type="button"
                          title={t("adventure.romance.giftHint")}
                          onClick={() => setGiftShopOpen(true)}
                        >
                          {t("adventure.romance.giftButton")}
                        </button>
                        <button
                          type="button"
                          title={t("adventure.romance.attributeHint")}
                          onClick={() => setAttributeModalOpen(true)}
                        >
                          {t("adventure.romance.attributeButton")}
                        </button>
                        {sim.confession_available && (
                          <button
                            type="button"
                            className="is-confess"
                            title={t("adventure.romance.confessHint")}
                            onClick={() =>
                              submit(
                                t("adventure.romance.confessAction", {
                                  name: sim.partner_name,
                                }),
                                "confess",
                              )
                            }
                          >
                            {t("adventure.romance.confessButton")}
                          </button>
                        )}
                      </div>
                    )}

                    {/* 自由入力は既定の操作なので常設。streaming中も入力自体は許可し
                    （無効化するとフォーカスが外れて次の数字キーが選択肢送信になる）、
                    送信は submit() 側のガードとボタンの disabled で止める */}
                    {talkMode && (
                      <div
                        className="adventure-talk-thread"
                        ref={talkThreadRef}
                        aria-live="polite"
                      >
                        {currentTalkEntries.length === 0 &&
                          pendingTalkInput === null && (
                            <p className="adventure-talk-thread__empty">
                              {t("adventure.talk.emptyHint", {
                                name: partnerName,
                              })}
                            </p>
                          )}
                        {currentTalkEntries.map((entry) => (
                          <p
                            key={entry.id}
                            className={`adventure-talk-thread__entry adventure-talk-thread__entry--${entry.role}`}
                          >
                            <span className="adventure-messagebox__speaker">
                              {entry.role === "partner"
                                ? partnerName
                                : playerDisplayName}
                            </span>
                            <span>{entry.text}</span>
                          </p>
                        ))}
                        {pendingTalkInput !== null && (
                          <>
                            <p className="adventure-talk-thread__entry adventure-talk-thread__entry--user">
                              <span className="adventure-messagebox__speaker">
                                {playerDisplayName}
                              </span>
                              <span>{pendingTalkInput}</span>
                            </p>
                            {talkDraft ? (
                              <p className="adventure-talk-thread__entry adventure-talk-thread__entry--partner">
                                <span className="adventure-messagebox__speaker">
                                  {partnerName}
                                </span>
                                <span>
                                  {talkDraft}
                                  <span className="adventure-transcript__caret" />
                                </span>
                              </p>
                            ) : (
                              <div className="adventure-progress">
                                <span />
                                {t("adventure.talk.pending", {
                                  name: partnerName,
                                })}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                    <form
                      className="adventure-freeinput"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (talkMode) {
                          submitTalkMessage(input);
                          return;
                        }
                        submit(input, "free_text");
                      }}
                    >
                      <input
                        type="text"
                        className="adventure-freeinput__field"
                        value={input}
                        maxLength={talkMode ? 500 : 1000}
                        onChange={(event) => setInput(event.target.value)}
                        placeholder={
                          talkMode
                            ? t("adventure.talk.placeholder", {
                                name: partnerName,
                              })
                            : t("adventure.freeInput")
                        }
                        aria-label={
                          talkMode
                            ? t("adventure.talk.placeholder", {
                                name: partnerName,
                              })
                            : t("adventure.freeInput")
                        }
                        title={t(
                          talkMode
                            ? "adventure.talk.hint"
                            : "adventure.freeInputHint",
                        )}
                        enterKeyHint="send"
                      />
                      <button
                        type="submit"
                        className="adventure-freeinput__submit"
                        disabled={!input.trim() || streaming || talking}
                      >
                        {t("adventure.send")}
                      </button>
                    </form>
                  </>
                )}
              </div>
            ) : (
              <div className={`adventure-ending is-${activeRun.status}`}>
                <span>{t(`adventure.status.${activeRun.status}`)}</span>
                <h2>{activeRun.ending_title}</h2>
                <p>{activeRun.ending_summary}</p>
                {/* リザルトを閉じた後・再入場時の継続導線 */}
                <button
                  type="button"
                  className="adventure-ending__continue"
                  disabled={streaming}
                  onClick={() => void startEpilogue()}
                >
                  {t("adventure.result.continueEpilogue")}
                </button>
              </div>
            )}
          </section>
        </div>
      </div>

      {activeRun.status !== "active" && !resultDismissed && (
        <div className={`adventure-result is-${activeRun.status}`}>
          <div
            className="adventure-result__card"
            role="dialog"
            aria-modal="true"
            aria-label={activeRun.ending_title ?? activeRun.title}
          >
            {resultImageUrl && (
              <img
                className="adventure-result__image"
                src={resultImageUrl}
                alt={t("adventure.portraitAlt")}
              />
            )}
            <div className="adventure-result__body">
              <span className="adventure-result__badge">
                {t(`adventure.status.${activeRun.status}`)}
              </span>
              <h2>{activeRun.ending_title ?? activeRun.title}</h2>
              <p className="adventure-result__summary">
                {activeRun.ending_summary}
              </p>
              <dl className="adventure-result__stats">
                <div>
                  <dt>{t("adventure.result.turns")}</dt>
                  <dd>
                    {activeRun.turn_count}
                    <i>/{activeRun.max_turns}</i>
                  </dd>
                </div>
                <div>
                  <dt>{t("adventure.milestones")}</dt>
                  <dd>
                    {completedMilestones.size}
                    <i>/{activeRun.milestones.length}</i>
                  </dd>
                </div>
                <div>
                  <dt>{t("adventure.clues")}</dt>
                  <dd>{activeRun.clues.length}</dd>
                </div>
              </dl>
              {activeRun.milestones.length > 0 && (
                <ul className="adventure-result__milestones">
                  {activeRun.milestones.map((milestone) => {
                    const done = completedMilestones.has(milestone.id);
                    return (
                      <li key={milestone.id} className={done ? "is-done" : ""}>
                        <span aria-hidden>{done ? "✓" : "・"}</span>
                        {milestone.label}
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className="adventure-result__actions">
                <button
                  type="button"
                  onClick={() => {
                    setResultDismissed(true);
                    setLogOpen(true);
                  }}
                >
                  {t("adventure.result.readLog")}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    navigate("/adventure", {
                      state: { replayRunId: activeRun.id },
                    })
                  }
                >
                  {t("adventure.result.replay")}
                </button>
                <button type="button" onClick={() => navigate("/adventure")}>
                  {t("adventure.result.backToHub")}
                </button>
                <button
                  type="button"
                  disabled={streaming}
                  onClick={() => {
                    setResultDismissed(true);
                    if (!isEpilogue) void startEpilogue();
                  }}
                >
                  {t("adventure.result.continueEpilogue")}
                </button>
              </div>
              <button
                type="button"
                className="adventure-result__close"
                onClick={() => setResultDismissed(true)}
              >
                {t("adventure.result.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {logOpen && (
        <div className="adventure-log">
          <button
            type="button"
            className="adventure-log__backdrop"
            aria-label={t("adventure.log.close")}
            onClick={() => setLogOpen(false)}
          />
          <aside
            className="adventure-log__panel"
            role="dialog"
            aria-modal="true"
            aria-label={t("adventure.log.title")}
          >
            <header className="adventure-log__header">
              <h2>{t("adventure.log.title")}</h2>
              <button
                type="button"
                onClick={() => setLogOpen(false)}
                aria-label={t("adventure.log.close")}
              >
                ×
              </button>
            </header>
            <div className="adventure-log__body">
              <div className="adventure-transcript">
                <article className="adventure-transcript__entry is-opening">
                  <span>{t("adventure.openingScene")}</span>
                  <p>{activeRun.opening_narrative}</p>
                </article>
                {activeRun.turns.map((turn) => (
                  <article
                    className="adventure-transcript__entry"
                    key={turn.id}
                  >
                    <div className="adventure-transcript__action">
                      <span>
                        {t("adventure.turn", { number: turn.turn_number })}
                      </span>
                      <p>{turn.user_input}</p>
                    </div>
                    <p>{turn.narrative}</p>
                  </article>
                ))}
              </div>
              <div ref={transcriptEndRef} />
            </div>
            {frames.length > 1 && (
              <div className="adventure-turn-strip">
                {frames.map((frame, index) => {
                  const isActive =
                    selectedFrameIndex === index ||
                    (selectedFrameIndex === null &&
                      index === frames.length - 1);
                  return (
                    <button
                      type="button"
                      key={frame.key}
                      className={`adventure-turn-strip__item${isActive ? " is-active" : ""}`}
                      onClick={() => {
                        goToFrame(index);
                        setLogOpen(false);
                      }}
                      aria-current={isActive ? "true" : undefined}
                      title={
                        frame.turnNumber === 0
                          ? t("adventure.turnStrip.opening")
                          : t("adventure.turnNumber", {
                              number: frame.turnNumber,
                            })
                      }
                    >
                      <img
                        src={frame.imageUrl}
                        alt={t("adventure.turnStrip.thumbAlt", {
                          number: frame.turnNumber,
                        })}
                        className="adventure-turn-strip__thumb"
                      />
                      <span className="adventure-turn-strip__badge">
                        {frame.turnNumber === 0
                          ? t("adventure.turnStrip.opening")
                          : frame.turnNumber}
                      </span>
                    </button>
                  );
                })}
                <div ref={turnStripEndRef} />
              </div>
            )}
          </aside>
        </div>
      )}

      <ImagePreviewModal
        isOpen={lightboxFrame !== undefined}
        className={sim ? "adventure-preview--romance" : undefined}
        imageUrl={lightboxImageUrl}
        onClose={() => setLightboxIndex(null)}
        alt={
          lightboxView === "partner"
            ? t("adventure.romance.partnerPortraitAlt")
            : t("adventure.preview.sceneAlt")
        }
        onPrev={() => openLightboxFrame((lightboxIndex ?? 0) - 1)}
        onNext={() => openLightboxFrame((lightboxIndex ?? 0) + 1)}
        hasPrev={lightboxIndex !== null && lightboxIndex > 0}
        hasNext={lightboxIndex !== null && lightboxIndex < frames.length - 1}
        captionPlacement="side"
        media={
          needsComposite && lightboxFrame?.backgroundUrl ? (
            <div className="adventure-scene-preview">
              <img
                className="adventure-scene-preview__background"
                src={lightboxFrame.backgroundUrl}
                alt={t("adventure.preview.backgroundAlt")}
              />
              {lightboxPortraitUrl && (
                <img
                  className={`adventure-scene-preview__portrait${
                    lightboxPartnerUrl
                      ? " adventure-scene-preview__portrait--paired"
                      : ""
                  }`}
                  src={lightboxPortraitUrl}
                  alt={t("adventure.portraitAlt")}
                />
              )}
              {lightboxPartnerUrl && (
                <img
                  className="adventure-scene-preview__portrait adventure-scene-preview__portrait--partner"
                  src={lightboxPartnerUrl}
                  alt={t("adventure.romance.partnerPortraitAlt")}
                />
              )}
            </div>
          ) : undefined
        }
        caption={
          lightboxFrame && (
            <div className="image-preview-modal__detail">
              <header className="adventure-preview__header">
                <p>{activeRun.title}</p>
                <h2>
                  <b>{t("adventure.goal")}</b>
                  <span>{activeRun.objective}</span>
                </h2>
              </header>
              {/* 概要は常に選べるため、切替チップ列は常時表示する */}
              <div
                ref={lightboxViewsRef}
                className="adventure-preview__views"
                role="group"
                aria-label={t("adventure.preview.viewSwitch")}
              >
                {/* シナリオ定義(舞台・制約・日数)の全文表示。先頭に置く */}
                <button
                  type="button"
                  aria-pressed={lightboxView === "overview"}
                  onClick={() => setLightboxView("overview")}
                >
                  {t("adventure.preview.viewOverview")}
                </button>
                <button
                  type="button"
                  aria-pressed={lightboxView === "scene"}
                  onClick={() => setLightboxView("scene")}
                >
                  {t("adventure.preview.viewScene")}
                </button>
                {canShowBackground && (
                  <button
                    type="button"
                    aria-pressed={lightboxView === "background"}
                    onClick={() => setLightboxView("background")}
                  >
                    {t("adventure.preview.viewBackground")}
                  </button>
                )}
                {canShowPortrait && (
                  <button
                    type="button"
                    aria-pressed={lightboxView === "portrait"}
                    onClick={() => setLightboxView("portrait")}
                  >
                    {t("adventure.preview.viewPortrait")}
                  </button>
                )}
                {canShowPartner && (
                  <button
                    type="button"
                    aria-pressed={lightboxView === "partner"}
                    onClick={() => setLightboxView("partner")}
                  >
                    {t("adventure.romance.partnerLabel")}
                  </button>
                )}
              </div>

              {lightboxView === "overview" ? (
                // 概要: シナリオ定義の全文を既存セクションと同じ様式で表示する。
                // タイトルとゴールは直上のヘッダに常時表示のため重複させない
                <>
                  {activeRun.setting && (
                    <section className="image-preview-modal__detail-section">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.setting")}
                      </h2>
                      <p className="image-preview-modal__detail-text">
                        {activeRun.setting}
                      </p>
                    </section>
                  )}
                  {activeRun.constraints.length > 0 && (
                    <section className="image-preview-modal__detail-section">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.constraints")}
                      </h2>
                      <ul className="adventure-preview__constraints">
                        {activeRun.constraints.map((item) => (
                          <li
                            key={item}
                            className="image-preview-modal__detail-text"
                          >
                            {item}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {sim && !isCompanion && (
                    <section className="image-preview-modal__detail-section">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.romance.days")}
                      </h2>
                      <p className="image-preview-modal__detail-text">
                        {t("adventure.scenarioDeadline", {
                          days: sim.total_days,
                        })}
                      </p>
                    </section>
                  )}
                </>
              ) : (
                <>
                  {/* そのフレーム確定時点の sim だけを使う。activeRun.sim への
                  フォールバックは過去手番に現在の好感度を出してしまうため行わない */}
                  {sim && lightboxFrame.sim && (
                    <section className="image-preview-modal__detail-section adventure-preview-partner">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.romance.partnerLabel")}
                      </h2>
                      <p className="adventure-preview-partner__name">
                        {lightboxFrame.sim.partner_name}
                      </p>
                      <div
                        className={`adventure-preview-partner__affection is-${lightboxFrame.sim.stage}`}
                        title={t(
                          `adventure.romance.stages.${lightboxFrame.sim.stage}`,
                        )}
                      >
                        <svg
                          className="adventure-preview-partner__heart"
                          viewBox="0 0 24 24"
                          aria-hidden
                        >
                          <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                        </svg>
                        <strong>
                          {lightboxFrame.sim.affection}
                          <i>/100</i>
                        </strong>
                        <span
                          className="adventure-preview-partner__gauge"
                          aria-hidden
                        >
                          <i
                            style={{ width: `${lightboxFrame.sim.affection}%` }}
                          />
                        </span>
                        <em className="adventure-preview-partner__stage">
                          {t(
                            `adventure.romance.stages.${lightboxFrame.sim.stage}`,
                          )}
                        </em>
                      </div>
                      {lightboxFrame.partnerNote && (
                        <p className="image-preview-modal__detail-text">
                          {lightboxFrame.partnerNote}
                        </p>
                      )}
                    </section>
                  )}

                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.preview.turnLabel")}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {lightboxFrame.turnNumber === 0
                        ? t("adventure.turnStrip.opening")
                        : sim && lightboxDaySlot && !isCompanion
                          ? lightboxFrame.sim?.epilogue
                            ? t("adventure.romance.previewTurnEpilogue", {
                                day: lightboxDaySlot.day,
                                slot: t(
                                  `adventure.romance.slot.${lightboxDaySlot.slot}`,
                                ),
                                turn: lightboxFrame.turnNumber,
                              })
                            : t("adventure.romance.previewTurn", {
                                day: lightboxDaySlot.day,
                                total: sim.total_days,
                                slot: t(
                                  `adventure.romance.slot.${lightboxDaySlot.slot}`,
                                ),
                                turn: lightboxFrame.turnNumber,
                                max: activeRun.max_turns,
                              })
                          : `${lightboxFrame.turnNumber} / ${activeRun.max_turns}`}
                    </p>
                    {lightboxFrame.turnNumber < activeRun.turn_count &&
                      (lightboxFrame.turnNumber > 0 ||
                        activeRun.can_rewind_to_opening) && (
                        <button
                          type="button"
                          className="adventure-preview__rewind"
                          disabled={streaming}
                          title={t("adventure.turnStrip.rewindHint")}
                          onClick={() =>
                            requestRewind(lightboxFrame.turnNumber)
                          }
                        >
                          {t("adventure.turnStrip.rewind")}
                        </button>
                      )}
                  </section>

                  {lightboxFrame.userInput && (
                    <section className="image-preview-modal__detail-section">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.preview.actionLabel")}
                        {lightboxFrame.inputKind && (
                          <span className="adventure-preview__kind">
                            {t(
                              `adventure.preview.inputKind.${lightboxFrame.inputKind}`,
                            )}
                          </span>
                        )}
                      </h2>
                      <p className="image-preview-modal__detail-text">
                        {lightboxFrame.userInput}
                      </p>
                    </section>
                  )}

                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.preview.narrativeLabel")}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {lightboxFrame.narrative}
                    </p>
                  </section>

                  {lightboxFrame.location && (
                    <section className="image-preview-modal__detail-section">
                      <h2 className="image-preview-modal__detail-label">
                        {t("adventure.currentLocation")}
                      </h2>
                      <p className="image-preview-modal__detail-text">
                        {lightboxFrame.location}
                      </p>
                    </section>
                  )}
                </>
              )}
            </div>
          )
        }
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
      <AdventureAnlasConfirmDialog
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
      <AdventureAnlasConfirmDialog
        open={pendingUsageWarnTurn !== null}
        body={t("adventure.v5UsageExhaustedBody")}
        onConfirm={confirmPendingUsageWarnTurn}
        onCancel={handleUsageWarnCancel}
      />
    </MainLayout>
  );
}

export default function AdventureScreen() {
  const location = useLocation();
  const runId = location.pathname.split("/")[2];
  return runId ? <AdventurePlay runId={runId} /> : <AdventureHub />;
}
