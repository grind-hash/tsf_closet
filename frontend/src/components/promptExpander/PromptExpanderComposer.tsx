/**
 * PromptExpanderComposer - Prompt Expander の入力欄
 *
 * 上から ① 生成パラメータ（背景透過スイッチを含む） ② 漫画 ③ プロンプト（「LLMで作る｜直接書く」の切り替え、
 * 指示（漫画ではあらすじ）→ ネーム（漫画のとき）→ プロンプト → ネガティブの欄。各欄の右上に、その欄の文から
 * 次の段階を作るボタン。プロンプト化の結果はプロンプト欄へ直接入れ、ネガティブの変換結果は欄の直下のカードに出す）
 * ④ キャラクタープロンプト ⑤ i2i 設定 ⑥ 精密参照（V4.5 系のみ。i2i 元とは別の参照画像）の
 * 開閉セクションと、最下部の「生成」ボタン。
 */

import {
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  isEconomyImageModel,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import {
  appendedTags,
  getPromptExpanderImageModelLabel,
  mangaPanelCountOptions,
  PROMPT_EXPANDER_I2I_NOISE_MAX,
  PROMPT_EXPANDER_I2I_NOISE_MIN,
  PROMPT_EXPANDER_I2I_STRENGTH_MAX,
  PROMPT_EXPANDER_I2I_STRENGTH_MIN,
  PROMPT_EXPANDER_MANGA_LAYOUTS,
  PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
  PROMPT_EXPANDER_MANGA_READING_DIRECTIONS,
  PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES,
  PROMPT_EXPANDER_SEED_MAX,
  PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS,
  type PromptExpanderImageSize,
  type PromptExpanderMangaLayout,
  type PromptExpanderMangaReadingDirection,
  type PromptExpanderMangaTextLanguage,
  type PromptExpandMode,
  supportsMangaMode,
  TRANSPARENT_BACKGROUND_NEGATIVE_TAGS,
  transparentBackgroundTags,
  transparentEmphasisSample,
  usesNativeTransparency,
} from "../../constants/promptExpander";
import { useNotification } from "../../contexts/NotificationContext";
import {
  type PromptExpanderExpansionTarget,
  type PromptExpanderPickerTarget,
  type PromptExpanderPromptInputMode,
  type PromptExpanderPromptSource,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import { useInsertAtCaret } from "../../hooks/useInsertAtCaret";
import {
  openPromptExpanderSection,
  revealPromptExpanderSection,
} from "../../hooks/usePersistedSectionState";
import { useWindowFileDrop } from "../../hooks/useWindowFileDrop";
import {
  FavoritePromptInsertButton,
  FavoritePromptSaveButton,
} from "../favoritePrompts/FavoritePromptButtons";
import FileDropOverlay from "../ui/FileDropOverlay";
import PromptExpanderCharacterSlots from "./PromptExpanderCharacterSlots";
import PromptExpanderDropChooserModal, {
  type PromptExpanderDropChooserOptions,
  type PromptExpanderDropDestination,
} from "./PromptExpanderDropChooserModal";
import PromptExpanderExpansionPanel from "./PromptExpanderExpansionPanel";
import PromptExpanderInpaintModal from "./PromptExpanderInpaintModal";
import PromptExpanderProgress from "./PromptExpanderProgress";
import PromptExpanderReferenceList from "./PromptExpanderReferenceList";
import PromptExpanderSection from "./PromptExpanderSection";
import PromptExpanderSourcePickerModal from "./PromptExpanderSourcePickerModal";
import PromptExpanderStoryContextChips from "./PromptExpanderStoryContextChips";
import PromptExpanderSuggestModal from "./PromptExpanderSuggestModal";
import PromptExpanderSwitch from "./PromptExpanderSwitch";
import PromptExpanderUploadDialog from "./PromptExpanderUploadDialog";
import "./PromptExpanderShared.css";
import "./PromptExpanderComposer.css";

interface ExpandModeRadioProps {
  name: string;
  value: PromptExpandMode;
  onChange: (mode: PromptExpandMode) => void;
  /** 無効化の理由（title に出す。漫画モード中の固定など） */
  disabledReason?: string | null;
}

function ExpandModeRadio({
  name,
  value,
  onChange,
  disabledReason = null,
}: ExpandModeRadioProps) {
  const { t } = useTranslation();
  const items: Array<{ mode: PromptExpandMode; label: string }> = [
    { mode: "japanese", label: t("promptExpander.composer.expandJapanese") },
    { mode: "tags", label: t("promptExpander.composer.expandTags") },
  ];
  return (
    <div
      className="prompt-expander__radio-group prompt-expander__radio-group--compact"
      role="radiogroup"
      aria-label={t("promptExpander.composer.expandModeLabel")}
      title={disabledReason ?? undefined}
    >
      {items.map((item) => (
        <label
          key={item.mode}
          className={`prompt-expander__radio ${value === item.mode ? "is-active" : ""}`}
        >
          <input
            type="radio"
            name={name}
            value={item.mode}
            checked={value === item.mode}
            disabled={disabledReason !== null}
            onChange={() => onChange(item.mode)}
          />
          {item.label}
        </label>
      ))}
    </div>
  );
}

/** 欄の下に出す拡張エラー（API の code を文言に変換する）。正プロンプト側は操作した欄の下に出す */
function ExpansionErrorNotice({
  target,
  field,
}: {
  target: PromptExpanderExpansionTarget;
  field?: PromptExpanderPromptSource;
}) {
  const { t } = useTranslation();
  const { expansionError, clearExpansionError, mangaActive } =
    usePromptExpander();
  if (!expansionError || expansionError.target !== target) return null;
  if (
    target === "positive" &&
    (expansionError.field ?? "instruction") !== field
  )
    return null;

  let message: string;
  let hint: string | null = null;
  switch (expansionError.code) {
    case "empty_instruction":
      message =
        target === "negative"
          ? t("promptExpander.composer.expandEmptyNegative")
          : field === "script"
            ? t("promptExpander.composer.expandEmptyScript")
            : mangaActive
              ? t("promptExpander.composer.expandEmptySynopsis")
              : t("promptExpander.composer.expandEmptyInstruction");
      break;
    case "memory_empty":
      message = t("promptExpander.suggest.memoryEmpty");
      hint = t("promptExpander.suggest.memoryEmptyHint");
      break;
    default:
      message = t("promptExpander.composer.expandFailed", {
        message: expansionError.message,
      });
  }
  return (
    <div className="prompt-expander__expansion-error" role="alert">
      <div className="prompt-expander__expansion-error-main">
        <p className="prompt-expander__error">{message}</p>
        {hint && <span className="prompt-expander__hint">{hint}</span>}
      </div>
      <button
        type="button"
        className="prompt-expander__btn prompt-expander__btn--sm"
        onClick={clearExpansionError}
      >
        {t("promptExpander.header.dismissError")}
      </button>
    </div>
  );
}

/**
 * 背景透過で送信時に足されるタグのプレビュー（欄の直下）。
 *
 * 透過タグはエントリの最終プロンプトには保存されず送信プロンプトにだけ載るため、
 * 強調段数を変えても結果を見るまで効いているか分からない。ここで実物を見せる。
 */
function TransparentTailPreview({
  target,
}: {
  target: PromptExpanderExpansionTarget;
}) {
  const { t } = useTranslation();
  const { settings, transparentActive, positiveText, negativeText } =
    usePromptExpander();
  if (!transparentActive) return null;

  const isPositive = target === "positive";
  const tags = isPositive
    ? transparentBackgroundTags(
        settings.image_model,
        settings.transparent_emphasis,
      )
    : [...TRANSPARENT_BACKGROUND_NEGATIVE_TAGS];
  const added = appendedTags(isPositive ? positiveText : negativeText, tags);

  return (
    <p className="prompt-expander__hint prompt-expander__transparent-tail">
      <span>{t("promptExpander.composer.transparentTailLabel")}</span>{" "}
      {added.length > 0 ? (
        <code className="prompt-expander__transparent-tail-tags">
          {added.join(", ")}
        </code>
      ) : (
        <span>{t("promptExpander.composer.transparentTailNone")}</span>
      )}
    </p>
  );
}

/**
 * 漫画モードの記法をワンクリックで挿入するチップ。
 * 「」セリフ / 『』モノローグ / 【】ナレーション / 《》効果音 / ① コマ番号（行頭に連番で入る）
 */
const NOTATION_CHIPS = [
  { key: "speech", label: "「」", open: "「", close: "」" },
  { key: "monologue", label: "『』", open: "『", close: "』" },
  { key: "narration", label: "【】", open: "【", close: "】" },
  { key: "sfx", label: "《》", open: "《", close: "》" },
  { key: "panel", label: "①", open: "", close: "" },
] as const;

const CIRCLED_ONE = 0x2460;
const CIRCLED_MAX = 20;

/**
 * 欄の高さを中身に合わせて伸ばす（上限は CSS の max-height。超えた分は欄の中でスクロール）。
 * ネームのように複数行を書く欄で、欄の中をスクロールしないと読めない状態を避ける。
 * rows で決まる高さより低くはしない。
 */
function useAutoGrowTextarea(
  ref: RefObject<HTMLTextAreaElement | null>,
  value: string,
) {
  useLayoutEffect(() => {
    const field = ref.current;
    if (!field) return;
    // value の変更をトリガーに高さを再計算する
    void value;
    field.style.height = "auto";
    // 隠している間（セクションを閉じているなど）は測れないため、rows の高さのままにする
    if (field.scrollHeight === 0) return;
    // box-sizing: border-box なので、内容の高さに上下の枠線を足す
    field.style.height = `${field.scrollHeight + field.offsetHeight - field.clientHeight}px`;
  }, [ref, value]);
}

/** Ctrl+Enter（Mac は ⌘+Enter）か。変換中の Enter と Shift 付きは除く */
function isExpandShortcut(event: KeyboardEvent<HTMLTextAreaElement>) {
  return (
    event.key === "Enter" &&
    (event.ctrlKey || event.metaKey) &&
    !event.shiftKey &&
    !event.nativeEvent.isComposing
  );
}

export default function PromptExpanderComposer() {
  const { t } = useTranslation();
  const {
    activeSession,
    settings,
    options,
    source,
    clearSource,
    referenceSupported,
    referenceCast,
    transparentActive,
    inpaintMask,
    inpaintActive,
    setInpaintMask,
    clearInpaintMask,
    promptInputMode,
    setPromptInputMode,
    instructionText,
    setInstructionText,
    scriptText,
    setScriptText,
    positiveText,
    setPositiveText,
    positiveMode,
    setPositiveMode,
    positiveOrigin,
    promptUndo,
    undoPrompt,
    characterMode,
    setCharacterMode,
    characterSlots,
    maxCharacterPrompts,
    mangaActive,
    effectivePositiveMode,
    negativeText,
    setNegativeText,
    negativeMode,
    setNegativeMode,
    negativeOrigin,
    updateSettings,
    updateSettingsDebounced,
    expanding,
    expandingTarget,
    generating,
    expandPositive,
    expandNegative,
    draftingScript,
    draftScript,
    scriptUndo,
    undoScript,
    restoreUndo,
    undoRestore,
    uploadImage,
    uploading,
  } = usePromptExpander();

  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [inpaintOpen, setInpaintOpen] = useState(false);
  // ピッカー／アップロードは i2i 元と精密参照で共用し、開いたときの入れ先だけを覚える
  const [pickerTarget, setPickerTarget] =
    useState<PromptExpanderPickerTarget>("source");
  const openPicker = (target: PromptExpanderPickerTarget) => {
    setPickerTarget(target);
    setPickerOpen(true);
  };
  const openUpload = (target: PromptExpanderPickerTarget) => {
    setPickerTarget(target);
    setUploadOpen(true);
  };

  // 画面全体への画像ドロップ: NovelAI 風に「何に使うか」を選ばせてから入れ先へ送る
  const { showNotification } = useNotification();
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [revealSectionId, setRevealSectionId] =
    useState<PromptExpanderDropDestination | null>(null);
  const handleDroppedFiles = useCallback(
    (files: File[]) => {
      const image = files.find((file) => file.type.startsWith("image/"));
      if (!image) {
        showNotification(
          "warning",
          t("promptExpander.drop.title"),
          t("promptExpander.drop.notImage"),
        );
        return;
      }
      setDroppedFile(image);
    },
    [showNotification, t],
  );
  const isFileDragging = useWindowFileDrop({
    enabled: activeSession !== null,
    onFiles: handleDroppedFiles,
  });
  const handleDropChoose = async (
    destination: PromptExpanderDropDestination,
    dropOptions: PromptExpanderDropChooserOptions,
  ) => {
    if (!droppedFile) return;
    const target: PromptExpanderPickerTarget =
      destination === "reference" ? "reference" : "source";
    const ok = await uploadImage(droppedFile, {
      keepAsEntry: dropOptions.keepAsEntry,
      useAsSource: true,
      target,
      note: dropOptions.note,
    });
    // 失敗は Context が通知済み。ダイアログは開いたままにして選び直せるようにする
    if (!ok) return;
    setDroppedFile(null);
    if (destination === "inpaint") {
      if (!settings.use_inpaint) void updateSettings({ use_inpaint: true });
      // 元画像が入ったので、続けてマスクを描けるように編集モーダルを開く
      setInpaintOpen(true);
    } else if (destination === "reference" && !settings.use_precise_reference) {
      void updateSettings({ use_precise_reference: true });
    }
    openPromptExpanderSection(destination);
    setRevealSectionId(destination);
  };
  // 登場人物のチップから、精密参照の欄を開いてそこへ移る
  const revealReferenceSection = () => revealPromptExpanderSection("reference");
  // 入れ先セクションが開いた描画後にそこへスクロールする
  useEffect(() => {
    if (!revealSectionId) return;
    setRevealSectionId(null);
    document
      .querySelector(
        `.prompt-expander__section[data-section-id="${revealSectionId}"]`,
      )
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [revealSectionId]);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [seedDraft, setSeedDraft] = useState<string | null>(null);
  const instructionRef = useRef<HTMLTextAreaElement>(null);
  const scriptRef = useRef<HTMLTextAreaElement>(null);
  const positiveRef = useRef<HTMLTextAreaElement>(null);
  const negativeRef = useRef<HTMLTextAreaElement>(null);
  useAutoGrowTextarea(instructionRef, instructionText);
  useAutoGrowTextarea(scriptRef, scriptText);
  useAutoGrowTextarea(positiveRef, positiveText);
  useAutoGrowTextarea(negativeRef, negativeText);
  const insertFavoriteIntoPositive = useInsertAtCaret(
    positiveRef,
    positiveText,
    setPositiveText,
  );
  const insertFavoriteIntoNegative = useInsertAtCaret(
    negativeRef,
    negativeText,
    setNegativeText,
  );

  // 記法チップ: ネーム欄のカーソル位置（選択範囲があればそれを包む）へ挿入し、括弧の内側へカーソルを戻す
  const insertIntoScript = (before: string, after: string) => {
    const el = scriptRef.current;
    const start = el?.selectionStart ?? scriptText.length;
    const end = el?.selectionEnd ?? scriptText.length;
    const selected = scriptText.slice(start, end);
    const next = `${scriptText.slice(0, start)}${before}${selected}${after}${scriptText.slice(end)}`;
    // 同期描画してから選択位置を置く（非同期だと React の再描画でカーソルが末尾へ飛ぶ）
    flushSync(() => setScriptText(next));
    const caret = start + before.length + selected.length;
    const node = scriptRef.current;
    if (node) {
      node.focus();
      node.setSelectionRange(caret, caret);
    }
  };
  const insertPanelNumber = () => {
    const el = scriptRef.current;
    const start = el?.selectionStart ?? scriptText.length;
    const used = Array.from(
      scriptText.matchAll(/[\u2460-\u2473]/g),
      (m) => m[0].charCodeAt(0) - CIRCLED_ONE + 1,
    );
    const nextNumber = Math.min(
      (used.length ? Math.max(...used) : 0) + 1,
      CIRCLED_MAX,
    );
    const mark = String.fromCharCode(CIRCLED_ONE + nextNumber - 1);
    const atLineStart = start === 0 || scriptText[start - 1] === "\n";
    insertIntoScript(`${atLineStart ? "" : "\n"}${mark}`, "");
  };

  const isV45 = !isV5ImageModel(settings.image_model);
  const mangaSupported = supportsMangaMode(settings.image_model);
  const busy = expanding || generating || draftingScript;
  const assist = promptInputMode === "assist";
  // LLM の結果が入る欄は、処理中は読み取り専用にして処理中を示す（指示・あらすじ欄は書き換えないので常に書ける）
  const positiveBusy = expandingTarget === "positive";
  const scriptBusy = draftingScript;
  const negativeBusy = expandingTarget === "negative";
  // 指示欄の見出し（漫画モードでは「あらすじ」）
  const instructionLabel = mangaActive
    ? t("promptExpander.composer.synopsisLabel")
    : t("promptExpander.composer.instructionLabel");
  const sourceFieldLabel = (field: PromptExpanderPromptSource) =>
    field === "script"
      ? t("promptExpander.composer.scriptLabel")
      : instructionLabel;
  // プロンプトを作ったあとで、元にした欄（指示・ネーム）を書き換えたか
  const promptSourceText =
    positiveOrigin?.source === "script" ? scriptText : instructionText;
  const sourceChanged =
    assist &&
    positiveOrigin !== null &&
    promptSourceText.trim().length > 0 &&
    promptSourceText.trim() !== positiveOrigin.instruction.trim();
  const inputModes: Array<{
    mode: PromptExpanderPromptInputMode;
    label: string;
  }> = [
    { mode: "assist", label: t("promptExpander.composer.inputModeAssist") },
    { mode: "direct", label: t("promptExpander.composer.inputModeDirect") },
  ];
  const favoritePromptButtons = (
    text: string,
    onInsert: (content: string) => void,
    fieldBusy: boolean,
  ) => (
    <>
      <FavoritePromptInsertButton onInsert={onInsert} disabled={fieldBusy} />
      <FavoritePromptSaveButton text={text} />
    </>
  );
  const notConfigured = !options.novelaiConfigured;
  const notConfiguredText = t("promptExpander.composer.disabledNotConfigured");

  // 拡張 / 提案ボタンの無効理由（NovelAI 未設定 > 処理中 > 空欄）
  const expandDisabledReason = (text: string): string | null => {
    if (notConfigured) return notConfiguredText;
    if (busy) return null;
    if (!text.trim()) {
      return t("promptExpander.composer.expandDisabledEmpty");
    }
    return null;
  };
  const instructionExpandReason = expandDisabledReason(instructionText);
  const scriptExpandReason = expandDisabledReason(scriptText);
  const negativeExpandReason = expandDisabledReason(negativeText);
  const suggestReason = notConfigured ? notConfiguredText : null;
  const slotSuggestReason = notConfigured
    ? notConfiguredText
    : !characterMode
      ? t("promptExpander.composer.suggestNeedsCharacterMode")
      : null;

  const sourceKindLabel = source
    ? t(`promptExpander.composer.sourceKind.${source.kind}`)
    : null;

  const seedValue =
    seedDraft ?? (settings.seed === null ? "" : String(settings.seed));

  const commitSeed = (raw: string) => {
    if (raw === "") {
      updateSettings({ seed: null });
      return;
    }
    const num = Number.parseInt(raw, 10);
    if (!Number.isNaN(num) && num >= 0 && num <= PROMPT_EXPANDER_SEED_MAX) {
      updateSettingsDebounced({ seed: num });
    }
  };

  // 漫画セクションの見出し右側に出す要約（閉じていても状態が分かるように）
  const mangaPanelLabel = (count: number) =>
    count === PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
      ? t("promptExpander.composer.mangaPanelAuto")
      : t("promptExpander.composer.mangaPanelValue", { count });
  const mangaSummary = !mangaSupported
    ? t("promptExpander.composer.mangaSummaryUnsupported")
    : !settings.manga_mode
      ? t("promptExpander.composer.mangaSummaryOff")
      : [
          mangaPanelLabel(settings.manga_panel_count),
          t(`promptExpander.composer.mangaLayout.${settings.manga_layout}`),
          t(
            `promptExpander.composer.mangaReadingDirectionShort.${settings.manga_reading_direction}`,
          ),
          settings.manga_dialogue
            ? t(
                `promptExpander.composer.mangaTextLanguage.${settings.manga_text_language}`,
              )
            : t("promptExpander.composer.mangaSummaryNoDialogue"),
          settings.manga_narration
            ? t("promptExpander.composer.mangaSummaryNarration")
            : null,
        ]
          .filter(Boolean)
          .join(" · ");

  // 背景透過の説明はモデル世代と漫画モードで切り替える（スイッチ自体は常に操作できる）
  const transparentHint = mangaActive
    ? t("promptExpander.composer.transparentHintManga")
    : usesNativeTransparency(settings.image_model)
      ? t("promptExpander.composer.transparentHintV5")
      : t("promptExpander.composer.transparentHintV45");
  // インペイントの要約（見出し右に出す。効かない組み合わせは理由が分かる文言にする）
  const inpaintSummary = !settings.use_inpaint
    ? t("promptExpander.composer.inpaintSummaryOff")
    : !source
      ? t("promptExpander.composer.inpaintNoSource")
      : !inpaintMask
        ? t("promptExpander.composer.inpaintNoMask")
        : t("promptExpander.composer.inpaintSummaryOn", {
            label: inpaintMask.label,
          });
  // 強調が効かない組み合わせは選択肢を隠さず、理由の文言だけ差し替える
  const emphasisHint = !transparentActive
    ? t("promptExpander.composer.transparentEmphasisDisabledOff")
    : usesNativeTransparency(settings.image_model)
      ? t("promptExpander.composer.transparentEmphasisDisabledV5")
      : null;

  // プロンプト化を押した欄（指示 or ネーム）。押した欄のボタンにだけ「プロンプト化中…」を出す
  const [expandingField, setExpandingField] =
    useState<PromptExpanderPromptSource | null>(null);
  const runExpandPositive = async (field: PromptExpanderPromptSource) => {
    setExpandingField(field);
    try {
      await expandPositive(field);
    } finally {
      setExpandingField(null);
    }
  };

  // 欄の右上の操作。作業の順に左から並べる（出力形式 → 前段の操作 → プロンプト化 → 補助）
  const renderFieldToolbar = ({
    label,
    mode,
    leading,
    expand,
    extra,
  }: {
    label: string;
    mode?: ReactNode;
    leading?: ReactNode;
    expand?: {
      onClick: () => void;
      reason: string | null;
      title: string;
      running: boolean;
      /** 既定は「LLMでプロンプト化」 */
      label?: string;
      /** false で枠線のボタンにする（その欄の次の一歩が別のボタンのとき） */
      primary?: boolean;
    };
    extra?: ReactNode;
  }) => (
    <div
      className="prompt-expander__field-toolbar"
      role="toolbar"
      aria-label={label}
    >
      {mode}
      {leading}
      {expand && (
        <button
          type="button"
          className={`prompt-expander__btn prompt-expander__btn--sm${expand.primary === false ? "" : " prompt-expander__btn--primary"}`}
          onClick={expand.onClick}
          disabled={busy || expand.reason !== null}
          title={expand.reason ?? expand.title}
        >
          {expand.running
            ? t("promptExpander.composer.expanding")
            : (expand.label ?? t("promptExpander.composer.expandButton"))}
        </button>
      )}
      {extra}
    </div>
  );

  const suggestButton = (reason: string | null) => (
    <button
      type="button"
      className="prompt-expander__btn prompt-expander__btn--sm"
      onClick={() => setSuggestOpen(true)}
      disabled={reason !== null}
      title={reason ?? t("promptExpander.composer.suggestFromMemory")}
    >
      {t("promptExpander.composer.suggestButton")}
    </button>
  );

  return (
    <div className="prompt-expander__composer">
      {/* ① 生成パラメータ */}
      <PromptExpanderSection
        id="params"
        title={t("promptExpander.composer.sectionParams")}
        toolbar={
          <span className="prompt-expander__section-summary">
            {getPromptExpanderImageModelLabel(settings.image_model)} ·{" "}
            {t(`promptExpander.composer.size.${settings.image_size}`)}
            {settings.seed !== null &&
              ` · ${t("promptExpander.entry.seedBadge", { value: settings.seed })}`}
            {settings.transparent_background &&
              ` · ${t("promptExpander.composer.transparentSummary")}`}
          </span>
        }
      >
        <div className="prompt-expander__params-grid">
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-image-model"
            >
              {t("promptExpander.composer.imageModel")}
            </label>
            <select
              id="prompt-expander-image-model"
              className="prompt-expander__select"
              value={settings.image_model}
              onChange={(e) =>
                void updateSettings({ image_model: e.target.value })
              }
            >
              {options.imageModelOptions.map((model) => (
                <option key={model} value={model}>
                  {getPromptExpanderImageModelLabel(model)}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-image-size"
            >
              {t("promptExpander.composer.imageSize")}
            </label>
            <select
              id="prompt-expander-image-size"
              className="prompt-expander__select"
              value={settings.image_size}
              onChange={(e) =>
                void updateSettings({
                  image_size: e.target.value as PromptExpanderImageSize,
                })
              }
            >
              {options.imageSizes.map((size) => (
                <option key={size} value={size}>
                  {t(`promptExpander.composer.size.${size}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-seed"
            >
              {t("promptExpander.composer.seed")}
            </label>
            <div className="prompt-expander__seed-row">
              <input
                id="prompt-expander-seed"
                type="number"
                className="prompt-expander__input"
                min={0}
                max={PROMPT_EXPANDER_SEED_MAX}
                step={1}
                value={seedValue}
                placeholder={t("promptExpander.composer.seedPlaceholder")}
                onChange={(e) => {
                  setSeedDraft(e.target.value);
                  commitSeed(e.target.value);
                }}
                onBlur={() => setSeedDraft(null)}
              />
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={() => {
                  setSeedDraft(null);
                  void updateSettings({ seed: null });
                }}
                disabled={settings.seed === null}
                title={t("promptExpander.composer.seedClear")}
                aria-label={t("promptExpander.composer.seedClear")}
              >
                ✕
              </button>
            </div>
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.seedHint")}
            </span>
          </div>
        </div>
        {/* 背景透過。V5 はプロンプト指示、V4.5 は白背景生成 + 表示時の切り抜き。漫画モード中は無効 */}
        <div className="prompt-expander__field">
          <PromptExpanderSwitch
            checked={settings.transparent_background}
            onChange={(checked) =>
              void updateSettings({ transparent_background: checked })
            }
            label={t("promptExpander.composer.transparentToggle")}
            title={transparentHint}
          />
          <span
            className={`prompt-expander__hint ${settings.transparent_background && !transparentActive ? "prompt-expander__hint--warning" : ""}`}
          >
            {transparentHint}
          </span>
          {/* 白背景の指定が効かないことがあるため、V4.5 では強調段数を選べるようにする。
              V5・透過 OFF でも隠さず、効かない理由を文言で出す */}
          <span className="prompt-expander__label">
            {t("promptExpander.composer.transparentEmphasis")}
          </span>
          <div
            className="prompt-expander__radio-group prompt-expander__radio-group--compact"
            role="radiogroup"
            aria-label={t("promptExpander.composer.transparentEmphasis")}
            title={emphasisHint ?? undefined}
          >
            {PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS.map((level) => (
              <label
                key={level}
                className={`prompt-expander__radio ${settings.transparent_emphasis === level ? "is-active" : ""}`}
              >
                <input
                  type="radio"
                  name="prompt-expander-transparent-emphasis"
                  value={level}
                  checked={settings.transparent_emphasis === level}
                  onChange={() =>
                    void updateSettings({ transparent_emphasis: level })
                  }
                />
                {level === 0
                  ? t("promptExpander.composer.transparentEmphasisNone")
                  : transparentEmphasisSample(level)}
              </label>
            ))}
          </div>
          <span
            className={`prompt-expander__hint ${emphasisHint ? "prompt-expander__hint--warning" : ""}`}
          >
            {emphasisHint ??
              t("promptExpander.composer.transparentEmphasisHint")}
          </span>
        </div>
      </PromptExpanderSection>

      {/* ② 漫画（コマ割り）。V5 のコマ割り・吹き出し生成を「拡張」で支援する */}
      <PromptExpanderSection
        id="manga"
        title={t("promptExpander.composer.sectionManga")}
        defaultOpen={false}
        toolbar={
          <>
            <span className="prompt-expander__section-summary">
              {mangaSummary}
            </span>
            <PromptExpanderSwitch
              checked={settings.manga_mode}
              onChange={(checked) =>
                void updateSettings({ manga_mode: checked })
              }
              label={t("promptExpander.composer.mangaToggle")}
              disabled={!mangaSupported}
              title={
                mangaSupported
                  ? undefined
                  : t("promptExpander.composer.mangaRequiresV5")
              }
            />
          </>
        }
      >
        {!mangaSupported && (
          <p className="prompt-expander__hint prompt-expander__hint--warning">
            {t("promptExpander.composer.mangaRequiresV5")}
          </p>
        )}
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.mangaHint")}
        </p>
        <div className="prompt-expander__params-grid">
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-manga-panels"
            >
              {t("promptExpander.composer.mangaPanelCount")}
            </label>
            <select
              id="prompt-expander-manga-panels"
              className="prompt-expander__select"
              value={settings.manga_panel_count}
              onChange={(e) =>
                void updateSettings({
                  manga_panel_count: Number.parseInt(e.target.value, 10),
                })
              }
            >
              {mangaPanelCountOptions().map((count) => (
                <option key={count} value={count}>
                  {mangaPanelLabel(count)}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-manga-layout"
            >
              {t("promptExpander.composer.mangaLayoutLabel")}
            </label>
            <select
              id="prompt-expander-manga-layout"
              className="prompt-expander__select"
              value={settings.manga_layout}
              onChange={(e) =>
                void updateSettings({
                  manga_layout: e.target.value as PromptExpanderMangaLayout,
                })
              }
            >
              {PROMPT_EXPANDER_MANGA_LAYOUTS.map((layout) => (
                <option key={layout} value={layout}>
                  {t(`promptExpander.composer.mangaLayout.${layout}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-manga-reading"
            >
              {t("promptExpander.composer.mangaReadingDirectionLabel")}
            </label>
            <select
              id="prompt-expander-manga-reading"
              className="prompt-expander__select"
              value={settings.manga_reading_direction}
              onChange={(e) =>
                void updateSettings({
                  manga_reading_direction: e.target
                    .value as PromptExpanderMangaReadingDirection,
                })
              }
            >
              {PROMPT_EXPANDER_MANGA_READING_DIRECTIONS.map((direction) => (
                <option key={direction} value={direction}>
                  {t(
                    `promptExpander.composer.mangaReadingDirection.${direction}`,
                  )}
                </option>
              ))}
            </select>
          </div>
          <div className="prompt-expander__field">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-manga-language"
            >
              {t("promptExpander.composer.mangaTextLanguageLabel")}
            </label>
            <select
              id="prompt-expander-manga-language"
              className="prompt-expander__select"
              value={settings.manga_text_language}
              onChange={(e) =>
                void updateSettings({
                  manga_text_language: e.target
                    .value as PromptExpanderMangaTextLanguage,
                })
              }
            >
              {PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES.map((lang) => (
                <option key={lang} value={lang}>
                  {t(`promptExpander.composer.mangaTextLanguage.${lang}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="prompt-expander__manga-switches">
          <PromptExpanderSwitch
            checked={settings.manga_dialogue}
            onChange={(checked) =>
              void updateSettings({ manga_dialogue: checked })
            }
            label={t("promptExpander.composer.mangaDialogue")}
          />
          <PromptExpanderSwitch
            checked={settings.manga_sound_effects}
            onChange={(checked) =>
              void updateSettings({ manga_sound_effects: checked })
            }
            label={t("promptExpander.composer.mangaSoundEffects")}
          />
          <PromptExpanderSwitch
            checked={settings.manga_narration}
            onChange={(checked) =>
              void updateSettings({ manga_narration: checked })
            }
            label={t("promptExpander.composer.mangaNarration")}
          />
        </div>
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.mangaNarrationHint")}
        </p>
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.mangaLayoutSizeHint")}
        </p>
        <p className="prompt-expander__hint">
          {characterMode
            ? t("promptExpander.composer.mangaCharacterOnHint")
            : t("promptExpander.composer.mangaCharacterOffHint")}
        </p>
      </PromptExpanderSection>

      {/* ③ プロンプト（指示 → ネーム → プロンプトの順に作る。直接書くときはプロンプト欄だけ） */}
      <PromptExpanderSection
        id="prompt"
        title={t("promptExpander.composer.sectionPrompt")}
      >
        <div className="prompt-expander__input-mode">
          <div
            className="prompt-expander__radio-group"
            role="radiogroup"
            aria-label={t("promptExpander.composer.inputModeLabel")}
          >
            {inputModes.map((item) => (
              <label
                key={item.mode}
                className={`prompt-expander__radio ${promptInputMode === item.mode ? "is-active" : ""}`}
              >
                <input
                  type="radio"
                  name="prompt-expander-input-mode"
                  value={item.mode}
                  checked={promptInputMode === item.mode}
                  onChange={() => setPromptInputMode(item.mode)}
                />
                {item.label}
              </label>
            ))}
          </div>
          <p className="prompt-expander__hint">
            {assist
              ? t("promptExpander.composer.inputModeAssistHint")
              : t("promptExpander.composer.inputModeDirectHint")}
          </p>
        </div>

        {/* 名前を付けた精密参照（登場人物）。あらすじやネームを書くときに名前を確かめられるよう欄の上に出す */}
        {assist && referenceCast.length > 0 && (
          <div
            className="prompt-expander__cast-chips"
            role="group"
            aria-label={t("promptExpander.composer.castChipsLabel")}
          >
            <span className="prompt-expander__cast-chips-label">
              {t("promptExpander.composer.castChipsLabel")}
            </span>
            {referenceCast.map((member) => (
              <button
                key={member.name}
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={revealReferenceSection}
                title={t("promptExpander.composer.castChipTitle", {
                  name: member.name,
                })}
              >
                {member.name}
              </button>
            ))}
          </div>
        )}

        {/* これまでの話（漫画モード）。選んだ前のページをネーム下書きとプロンプト化に渡す */}
        {assist && mangaActive && <PromptExpanderStoryContextChips />}

        {/* 指示（漫画モードではあらすじ）。利用者が書く欄で、LLM は書き換えない */}
        {assist && (
          <div className="prompt-expander__field-block">
            <div className="prompt-expander__field-head">
              <label
                className="prompt-expander__label"
                htmlFor="prompt-expander-instruction"
              >
                {instructionLabel}
              </label>
              {renderFieldToolbar({
                label: mangaActive
                  ? t("promptExpander.composer.synopsisToolbar")
                  : t("promptExpander.composer.instructionToolbar"),
                mode: (
                  <ExpandModeRadio
                    name="prompt-expander-positive-mode"
                    value={effectivePositiveMode}
                    onChange={setPositiveMode}
                    disabledReason={
                      mangaActive
                        ? t("promptExpander.composer.mangaModeFixedHint")
                        : null
                    }
                  />
                ),
                // 漫画モードのあらすじ欄では、次の一歩のネーム下書きを右端の主ボタンにする。
                // あらすじから直接のプロンプト化は枠線のボタンにして文言でも区別する（押し間違い防止）
                expand: {
                  onClick: () => void runExpandPositive("instruction"),
                  reason: instructionExpandReason,
                  title: mangaActive
                    ? t("promptExpander.composer.expandFromSynopsisTitle")
                    : t("promptExpander.composer.expandFromInstructionTitle"),
                  running: positiveBusy && expandingField === "instruction",
                  ...(mangaActive
                    ? {
                        label: t("promptExpander.composer.expandSkipScript"),
                        primary: false,
                      }
                    : {}),
                },
                extra: mangaActive ? (
                  <button
                    type="button"
                    className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__btn--primary"
                    onClick={() => void draftScript()}
                    disabled={busy || !instructionText.trim()}
                    title={t("promptExpander.composer.draftScriptTitle")}
                  >
                    {t("promptExpander.composer.draftScript")}
                  </button>
                ) : null,
              })}
            </div>
            <textarea
              id="prompt-expander-instruction"
              ref={instructionRef}
              className="prompt-expander__textarea prompt-expander__textarea--autogrow"
              rows={3}
              value={instructionText}
              onChange={(e) => setInstructionText(e.target.value)}
              onKeyDown={(e) => {
                if (!isExpandShortcut(e)) return;
                e.preventDefault();
                if (busy || instructionExpandReason !== null) return;
                // 漫画モードでは次の段階（ネームの下書き）、それ以外はプロンプト化
                void (mangaActive
                  ? draftScript()
                  : runExpandPositive("instruction"));
              }}
              placeholder={
                mangaActive
                  ? t("promptExpander.composer.synopsisPlaceholder")
                  : t("promptExpander.composer.instructionPlaceholder")
              }
            />
            {mangaActive && (
              <p className="prompt-expander__hint">
                {t("promptExpander.composer.mangaModeFixedHint")}
              </p>
            )}
            {positiveMode === "japanese" && isV45 && !mangaActive && (
              <p className="prompt-expander__hint prompt-expander__hint--warning">
                {t("promptExpander.composer.v45JapaneseHint")}
              </p>
            )}
            <ExpansionErrorNotice target="positive" field="instruction" />
          </div>
        )}

        {/* ネーム（漫画モード）。LLM の下書きが入り、手直ししてからプロンプト化する */}
        {assist && mangaActive && (
          <div className="prompt-expander__field-block">
            <div className="prompt-expander__field-head">
              <label
                className="prompt-expander__label"
                htmlFor="prompt-expander-script"
              >
                {t("promptExpander.composer.scriptLabel")}
              </label>
              {renderFieldToolbar({
                label: t("promptExpander.composer.scriptToolbar"),
                expand: {
                  onClick: () => void runExpandPositive("script"),
                  reason: scriptExpandReason,
                  title: t("promptExpander.composer.expandFromScriptTitle"),
                  running: positiveBusy && expandingField === "script",
                },
              })}
            </div>
            <div
              className="prompt-expander__notation-chips"
              role="toolbar"
              aria-label={t("promptExpander.composer.notation.toolbar")}
            >
              {NOTATION_CHIPS.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="prompt-expander__btn prompt-expander__btn--sm"
                  onClick={() =>
                    chip.key === "panel"
                      ? insertPanelNumber()
                      : insertIntoScript(chip.open, chip.close)
                  }
                  disabled={scriptBusy}
                  aria-label={t(`promptExpander.composer.notation.${chip.key}`)}
                  title={t(`promptExpander.composer.notation.${chip.key}`)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            <textarea
              id="prompt-expander-script"
              ref={scriptRef}
              className={`prompt-expander__textarea prompt-expander__textarea--autogrow${scriptBusy ? " prompt-expander__textarea--busy" : ""}`}
              rows={5}
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              onKeyDown={(e) => {
                if (!isExpandShortcut(e)) return;
                e.preventDefault();
                if (!busy && scriptExpandReason === null) {
                  void runExpandPositive("script");
                }
              }}
              readOnly={scriptBusy}
              aria-busy={scriptBusy}
              placeholder={t("promptExpander.composer.scriptPlaceholder")}
            />
            {scriptBusy && (
              <PromptExpanderProgress
                label={t("promptExpander.composer.draftingHint")}
              />
            )}
            {scriptUndo && scriptText === scriptUndo.applied && (
              <p className="prompt-expander__hint prompt-expander__draft-done">
                <span>{t("promptExpander.composer.draftDone")}</span>
                <button
                  type="button"
                  className="prompt-expander__btn prompt-expander__btn--sm"
                  onClick={undoScript}
                >
                  {t("promptExpander.composer.draftUndo")}
                </button>
              </p>
            )}
            <p className="prompt-expander__hint">
              {t("promptExpander.composer.mangaNotationHint")}
            </p>
            <ExpansionErrorNotice target="positive" field="script" />
          </div>
        )}

        {/* プロンプト（生成で送る内容）。プロンプト化の結果が入り、直接書いても手直ししてもよい */}
        <div className="prompt-expander__field-block">
          <div className="prompt-expander__field-head">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-positive"
            >
              {t("promptExpander.composer.promptLabel")}
              {positiveOrigin && (
                <span
                  className="prompt-expander__badge prompt-expander__badge--accent"
                  title={t("promptExpander.composer.originTitle", {
                    instruction: positiveOrigin.instruction,
                  })}
                >
                  {t(`promptExpander.entry.expandBadge.${positiveOrigin.mode}`)}
                </span>
              )}
            </label>
            {renderFieldToolbar({
              label: t("promptExpander.composer.positiveToolbar"),
              extra: (
                <>
                  {suggestButton(suggestReason)}
                  {favoritePromptButtons(
                    positiveText,
                    insertFavoriteIntoPositive,
                    positiveBusy,
                  )}
                </>
              ),
            })}
          </div>
          <textarea
            id="prompt-expander-positive"
            ref={positiveRef}
            className={`prompt-expander__textarea prompt-expander__textarea--autogrow${positiveBusy ? " prompt-expander__textarea--busy" : ""}`}
            rows={assist ? 3 : 5}
            value={positiveText}
            onChange={(e) => setPositiveText(e.target.value)}
            readOnly={positiveBusy}
            aria-busy={positiveBusy}
            placeholder={
              assist
                ? t("promptExpander.composer.promptPlaceholderAssist")
                : t("promptExpander.composer.promptPlaceholderDirect")
            }
          />
          {positiveBusy && (
            <PromptExpanderProgress
              label={t("promptExpander.composer.expandingHint")}
            />
          )}
          {promptUndo && positiveText === promptUndo.applied && (
            <p className="prompt-expander__hint prompt-expander__draft-done">
              <span>{t("promptExpander.composer.promptRebuilt")}</span>
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={undoPrompt}
              >
                {t("promptExpander.composer.promptUndo")}
              </button>
            </p>
          )}
          {/* プロンプトを作ったあとで元の欄を書き換えたら、作り直せることを知らせる */}
          {sourceChanged && positiveOrigin && (
            <p
              className="prompt-expander__hint prompt-expander__hint--warning prompt-expander__draft-done"
              role="status"
            >
              <span>
                {t("promptExpander.composer.sourceChanged", {
                  field: sourceFieldLabel(positiveOrigin.source),
                })}
              </span>
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={() => void runExpandPositive(positiveOrigin.source)}
                disabled={busy}
              >
                {t("promptExpander.composer.rebuildFromSource", {
                  field: sourceFieldLabel(positiveOrigin.source),
                })}
              </button>
            </p>
          )}
          {/* 「欄へ復元」で書きかけの内容を置き換えたときは、すぐ元に戻せるようにする */}
          {restoreUndo && positiveText === restoreUndo.restoredPositive && (
            <p className="prompt-expander__hint prompt-expander__draft-done">
              <span>{t("promptExpander.composer.restoreDone")}</span>
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={undoRestore}
              >
                {t("promptExpander.composer.restoreUndo")}
              </button>
            </p>
          )}
          <TransparentTailPreview target="positive" />
        </div>

        {/* ネガティブ */}
        <div className="prompt-expander__field-block">
          <div className="prompt-expander__field-head">
            <label
              className="prompt-expander__label"
              htmlFor="prompt-expander-negative"
            >
              {t("promptExpander.composer.negativeLabel")}
              {negativeOrigin && (
                <span className="prompt-expander__badge prompt-expander__badge--accent">
                  {t(`promptExpander.entry.expandBadge.${negativeOrigin.mode}`)}
                </span>
              )}
            </label>
            {renderFieldToolbar({
              label: t("promptExpander.composer.negativeToolbar"),
              mode: (
                <ExpandModeRadio
                  name="prompt-expander-negative-mode"
                  value={negativeMode}
                  onChange={setNegativeMode}
                />
              ),
              expand: {
                onClick: () => void expandNegative(),
                reason: negativeExpandReason,
                title: t("promptExpander.composer.expandNegativeTitle"),
                running: negativeBusy,
              },
              extra: favoritePromptButtons(
                negativeText,
                insertFavoriteIntoNegative,
                negativeBusy,
              ),
            })}
          </div>
          <textarea
            ref={negativeRef}
            id="prompt-expander-negative"
            className={`prompt-expander__textarea prompt-expander__textarea--autogrow${negativeBusy ? " prompt-expander__textarea--busy" : ""}`}
            rows={3}
            value={negativeText}
            onChange={(e) => setNegativeText(e.target.value)}
            onKeyDown={(e) => {
              if (!isExpandShortcut(e)) return;
              e.preventDefault();
              if (!busy && negativeExpandReason === null) void expandNegative();
            }}
            readOnly={negativeBusy}
            aria-busy={negativeBusy}
            placeholder={t("promptExpander.composer.negativePlaceholder")}
          />
          {isEconomyImageModel(settings.image_model) && (
            <p className="prompt-expander__hint prompt-expander__hint--warning">
              {t("promptExpander.composer.negativeEconomyHint")}
            </p>
          )}
          {negativeBusy && (
            <PromptExpanderProgress
              label={t("promptExpander.composer.expandingHint")}
            />
          )}
          <TransparentTailPreview target="negative" />
          <ExpansionErrorNotice target="negative" />
          <PromptExpanderExpansionPanel />
        </div>
      </PromptExpanderSection>

      {/* ④ キャラクタープロンプト */}
      <PromptExpanderSection
        id="characters"
        title={t("promptExpander.composer.sectionCharacters")}
        toolbar={
          <>
            {characterMode && (
              <span className="prompt-expander__section-summary">
                {t("promptExpander.composer.characterCounter", {
                  count: characterSlots.length,
                  max: maxCharacterPrompts,
                })}
              </span>
            )}
            <PromptExpanderSwitch
              checked={characterMode}
              onChange={setCharacterMode}
              label={t("promptExpander.composer.characterToggle")}
            />
            {suggestButton(slotSuggestReason)}
          </>
        }
      >
        {characterMode ? (
          <PromptExpanderCharacterSlots />
        ) : (
          <p className="prompt-expander__hint">
            {t("promptExpander.composer.characterOffHint")}
          </p>
        )}
      </PromptExpanderSection>

      {/* ⑤ 精密参照（V5 節約モード以外）。i2i 元とは別の参照画像（複数枚）で人物を固定し、
          名前を付けた参照は登場人物としてプロンプト化・ネーム下書きに渡す。
          登場人物はキャラクタープロンプトと同じ人物の話なので、その直後に置く */}
      <PromptExpanderReferenceList
        onPick={() => openPicker("reference")}
        onUpload={() => openUpload("reference")}
      />

      {/* ⑥ i2i 設定（ここから下は画像を加工する欄） */}
      <PromptExpanderSection
        id="i2i"
        title={t("promptExpander.composer.sectionI2i")}
        toolbar={
          <span className="prompt-expander__section-summary">
            {source
              ? t("promptExpander.composer.i2iSummaryOn", {
                  kind: sourceKindLabel,
                })
              : t("promptExpander.composer.i2iSummaryOff")}
          </span>
        }
      >
        <div className="prompt-expander__source-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openPicker("source")}
          >
            {t("promptExpander.composer.pickFromList")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openUpload("source")}
          >
            {t("promptExpander.composer.uploadImage")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={clearSource}
            disabled={!source}
            title={source ? undefined : t("promptExpander.composer.sourceNone")}
          >
            {t("promptExpander.composer.sourceClear")}
          </button>
        </div>
        <div className="prompt-expander__source-row">
          {source ? (
            <>
              <img
                className="prompt-expander__thumb"
                src={source.thumbnailUrl}
                alt=""
              />
              <div className="prompt-expander__source-info">
                <span className="prompt-expander__source-label">
                  {source.label}
                </span>
                <span className="prompt-expander__badge">
                  {sourceKindLabel}
                </span>
              </div>
            </>
          ) : (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.sourceNone")}
            </span>
          )}
        </div>
        <PromptExpanderSwitch
          checked={settings.inherit_source_prompts}
          onChange={(checked) =>
            void updateSettings({ inherit_source_prompts: checked })
          }
          label={t("promptExpander.composer.inheritSource")}
          title={t("promptExpander.composer.inheritSourceHint")}
        />
        <span className="prompt-expander__hint">
          {t("promptExpander.composer.inheritSourceHint")}
        </span>
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-i2i-strength"
          >
            {t("promptExpander.composer.i2iStrength")}:{" "}
            {settings.i2i_strength.toFixed(2)}
          </label>
          <input
            id="prompt-expander-i2i-strength"
            type="range"
            className="prompt-expander__range"
            min={PROMPT_EXPANDER_I2I_STRENGTH_MIN}
            max={PROMPT_EXPANDER_I2I_STRENGTH_MAX}
            step={0.01}
            value={settings.i2i_strength}
            disabled={!source}
            title={
              source
                ? undefined
                : t("promptExpander.composer.i2iDisabledReason")
            }
            onChange={(e) =>
              updateSettingsDebounced({
                i2i_strength: Number.parseFloat(e.target.value),
              })
            }
          />
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-i2i-noise"
          >
            {t("promptExpander.composer.i2iNoise")}:{" "}
            {settings.i2i_noise.toFixed(2)}
          </label>
          <input
            id="prompt-expander-i2i-noise"
            type="range"
            className="prompt-expander__range"
            min={PROMPT_EXPANDER_I2I_NOISE_MIN}
            max={PROMPT_EXPANDER_I2I_NOISE_MAX}
            step={0.01}
            value={settings.i2i_noise}
            disabled={!source}
            title={
              source
                ? undefined
                : t("promptExpander.composer.i2iDisabledReason")
            }
            onChange={(e) =>
              updateSettingsDebounced({
                i2i_noise: Number.parseFloat(e.target.value),
              })
            }
          />
          {!source && (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.i2iDisabledReason")}
            </span>
          )}
        </div>
      </PromptExpanderSection>

      {/* ⑦ インペイント（部分修正）。i2i 元をベース画像に使い、マスクの領域だけ描き直す */}
      <PromptExpanderSection
        id="inpaint"
        title={t("promptExpander.composer.sectionInpaint")}
        defaultOpen={false}
        toolbar={
          <>
            <span className="prompt-expander__section-summary">
              {inpaintSummary}
            </span>
            <PromptExpanderSwitch
              checked={settings.use_inpaint}
              onChange={(checked) =>
                void updateSettings({ use_inpaint: checked })
              }
              label={t("promptExpander.composer.inpaintToggle")}
            />
          </>
        }
      >
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.inpaintHint")}
        </p>
        <div className="prompt-expander__source-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openPicker("source")}
          >
            {t("promptExpander.composer.pickFromList")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openUpload("source")}
          >
            {t("promptExpander.composer.uploadImage")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={clearSource}
            disabled={!source}
            title={
              source ? undefined : t("promptExpander.composer.inpaintNoSource")
            }
          >
            {t("promptExpander.composer.sourceClear")}
          </button>
        </div>
        <div className="prompt-expander__source-row">
          {source ? (
            <>
              <img
                className="prompt-expander__thumb"
                src={source.thumbnailUrl}
                alt=""
              />
              <div className="prompt-expander__source-info">
                <span className="prompt-expander__source-label">
                  {source.label}
                </span>
                <span className="prompt-expander__badge">
                  {t("promptExpander.composer.inpaintBaseBadge")}
                </span>
              </div>
            </>
          ) : (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.inpaintNoSource")}
            </span>
          )}
        </div>
        <div className="prompt-expander__source-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => setInpaintOpen(true)}
            disabled={!source}
            title={
              source ? undefined : t("promptExpander.composer.inpaintNoSource")
            }
          >
            {t("promptExpander.composer.editMask")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={clearInpaintMask}
            disabled={!inpaintMask}
            title={
              inpaintMask
                ? undefined
                : t("promptExpander.composer.inpaintNoMask")
            }
          >
            {t("promptExpander.composer.clearMask")}
          </button>
        </div>
        <div className="prompt-expander__source-row">
          {inpaintMask ? (
            <>
              <img
                className="prompt-expander__thumb prompt-expander__thumb--mask"
                src={inpaintMask.thumbnailUrl}
                alt=""
              />
              <div className="prompt-expander__source-info">
                <span className="prompt-expander__source-label">
                  {inpaintMask.label}
                </span>
              </div>
            </>
          ) : (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.inpaintNoMask")}
            </span>
          )}
        </div>
        {settings.use_inpaint && !inpaintActive && (
          <p className="prompt-expander__hint prompt-expander__hint--warning">
            {source
              ? t("promptExpander.composer.inpaintNoMask")
              : t("promptExpander.composer.inpaintNoSource")}
          </p>
        )}
        <span className="prompt-expander__hint">
          {t("promptExpander.composer.inpaintStrengthHint")}
        </span>
      </PromptExpanderSection>

      {/* 生成ボタンは画面下端の PromptExpanderControlBar に置く（常に見える位置に保つため） */}

      <PromptExpanderSourcePickerModal
        open={pickerOpen}
        target={pickerTarget}
        onClose={() => setPickerOpen(false)}
      />
      <PromptExpanderUploadDialog
        open={uploadOpen}
        target={pickerTarget}
        onClose={() => setUploadOpen(false)}
      />
      <PromptExpanderSuggestModal
        open={suggestOpen}
        onClose={() => setSuggestOpen(false)}
      />
      <PromptExpanderInpaintModal
        open={inpaintOpen}
        onClose={() => setInpaintOpen(false)}
        baseImageUrl={source?.thumbnailUrl ?? null}
        initialMaskUrl={inpaintMask?.thumbnailUrl ?? null}
        onApply={(dataUrl, label) =>
          setInpaintMask({ dataUrl, thumbnailUrl: dataUrl, label })
        }
      />
      <PromptExpanderDropChooserModal
        file={droppedFile}
        onClose={() => setDroppedFile(null)}
        onChoose={(destination, dropOptions) =>
          void handleDropChoose(destination, dropOptions)
        }
        busy={uploading}
        referenceSupported={referenceSupported}
      />
      {/* 画面全体への画像ドロップ用オーバーレイ（表示のみ。drop 自体は window で受ける） */}
      {isFileDragging && (
        <FileDropOverlay
          testId="prompt-expander-drop-overlay"
          title={t("promptExpander.drop.overlayTitle")}
          hint={t("promptExpander.drop.overlayHint")}
        />
      )}
    </div>
  );
}
