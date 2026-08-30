/**
 * PromptExpanderComposer - Prompt Expander の入力欄
 *
 * 上から ① 生成パラメータ（背景透過スイッチを含む） ② 漫画 ③ プロンプト／指示（正 + ネガティブ。
 * 各欄の右上にモード切替・拡張・提案のツールバー、拡張結果は欄の直下にインライン表示）
 * ④ キャラクタープロンプト ⑤ i2i 設定 ⑥ 精密参照（V4.5 系のみ。i2i 元とは別の参照画像）の
 * 開閉セクションと、最下部の「生成」ボタン。
 */

import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";
import { useTranslation } from "react-i18next";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
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
  PROMPT_EXPANDER_REFERENCE_TYPES,
  PROMPT_EXPANDER_SEED_MAX,
  PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS,
  type PromptExpanderImageSize,
  type PromptExpanderMangaLayout,
  type PromptExpanderMangaReadingDirection,
  type PromptExpanderMangaTextLanguage,
  type PromptExpandMode,
  referenceTypeI18nKey,
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
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import { openPromptExpanderSection } from "../../hooks/usePersistedSectionState";
import { useWindowFileDrop } from "../../hooks/useWindowFileDrop";
import FileDropOverlay from "../ui/FileDropOverlay";
import PromptExpanderCharacterSlots from "./PromptExpanderCharacterSlots";
import PromptExpanderDropChooserModal, {
  type PromptExpanderDropChooserOptions,
  type PromptExpanderDropDestination,
} from "./PromptExpanderDropChooserModal";
import PromptExpanderExpansionPanel from "./PromptExpanderExpansionPanel";
import PromptExpanderInpaintModal from "./PromptExpanderInpaintModal";
import PromptExpanderProgress from "./PromptExpanderProgress";
import PromptExpanderSection from "./PromptExpanderSection";
import PromptExpanderSourcePickerModal from "./PromptExpanderSourcePickerModal";
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

/** 欄の下に出す拡張エラー（API の code を文言に変換する） */
function ExpansionErrorNotice({
  target,
}: {
  target: PromptExpanderExpansionTarget;
}) {
  const { t } = useTranslation();
  const { expansionError, clearExpansionError } = usePromptExpander();
  if (!expansionError || expansionError.target !== target) return null;

  let message: string;
  let hint: string | null = null;
  switch (expansionError.code) {
    case "empty_instruction":
      message =
        target === "positive"
          ? t("promptExpander.composer.expandEmptyPositive")
          : t("promptExpander.composer.expandEmptyNegative");
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

export default function PromptExpanderComposer() {
  const { t } = useTranslation();
  const {
    activeSession,
    settings,
    options,
    source,
    clearSource,
    reference,
    clearReference,
    referenceSupported,
    transparentActive,
    inpaintMask,
    inpaintActive,
    setInpaintMask,
    clearInpaintMask,
    positiveText,
    setPositiveText,
    positiveMode,
    setPositiveMode,
    positiveOrigin,
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
    scriptDraftBackup,
    draftScript,
    undoScriptDraft,
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
  const positiveRef = useRef<HTMLTextAreaElement>(null);

  // 記法チップ: カーソル位置（選択範囲があればそれを包む）へ挿入し、括弧の内側へカーソルを戻す
  const insertIntoPositive = (before: string, after: string) => {
    const el = positiveRef.current;
    const start = el?.selectionStart ?? positiveText.length;
    const end = el?.selectionEnd ?? positiveText.length;
    const selected = positiveText.slice(start, end);
    const next = `${positiveText.slice(0, start)}${before}${selected}${after}${positiveText.slice(end)}`;
    // 同期描画してから選択位置を置く（非同期だと React の再描画でカーソルが末尾へ飛ぶ）
    flushSync(() => setPositiveText(next));
    const caret = start + before.length + selected.length;
    const node = positiveRef.current;
    if (node) {
      node.focus();
      node.setSelectionRange(caret, caret);
    }
  };
  const insertPanelNumber = () => {
    const el = positiveRef.current;
    const start = el?.selectionStart ?? positiveText.length;
    const used = Array.from(
      positiveText.matchAll(/[\u2460-\u2473]/g),
      (m) => m[0].charCodeAt(0) - CIRCLED_ONE + 1,
    );
    const nextNumber = Math.min(
      (used.length ? Math.max(...used) : 0) + 1,
      CIRCLED_MAX,
    );
    const mark = String.fromCharCode(CIRCLED_ONE + nextNumber - 1);
    const atLineStart = start === 0 || positiveText[start - 1] === "\n";
    insertIntoPositive(`${atLineStart ? "" : "\n"}${mark}`, "");
  };

  const isV45 = !isV5ImageModel(settings.image_model);
  const mangaSupported = supportsMangaMode(settings.image_model);
  const busy = expanding || generating || draftingScript;
  // LLM でプロンプト化／ネーム下書きしている欄は読み取り専用にして処理中を示す
  const positiveBusy = expandingTarget === "positive" || draftingScript;
  const negativeBusy = expandingTarget === "negative";
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
  const positiveExpandReason = expandDisabledReason(positiveText);
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

  // 精密参照セクションの要約（閉じていても状態が分かるように）
  const referenceKindLabel = reference
    ? t(`promptExpander.composer.sourceKind.${reference.kind}`)
    : null;
  const referenceTypeLabel = t(
    `promptExpander.composer.referenceType.${referenceTypeI18nKey(settings.reference_type)}`,
  );
  const referenceSummary = !referenceSupported
    ? t("promptExpander.composer.referenceSummaryUnsupported")
    : !settings.use_precise_reference
      ? t("promptExpander.composer.referenceSummaryOff")
      : !reference
        ? t("promptExpander.composer.referenceSummaryNoImage")
        : t("promptExpander.composer.referenceSummaryOn", {
            type: referenceTypeLabel,
            strength: settings.reference_strength.toFixed(2),
            fidelity: settings.reference_fidelity.toFixed(2),
            cost: options.anlasPerReference,
          });
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

  const renderFieldToolbar = (
    target: PromptExpanderExpansionTarget,
    extra?: ReactNode,
  ) => {
    const isPositive = target === "positive";
    const reason = isPositive ? positiveExpandReason : negativeExpandReason;
    const runningHere = expandingTarget === target;
    return (
      <div
        className="prompt-expander__field-toolbar"
        role="toolbar"
        aria-label={
          isPositive
            ? t("promptExpander.composer.positiveToolbar")
            : t("promptExpander.composer.negativeToolbar")
        }
      >
        <ExpandModeRadio
          name={`prompt-expander-${target}-mode`}
          value={isPositive ? effectivePositiveMode : negativeMode}
          onChange={isPositive ? setPositiveMode : setNegativeMode}
          disabledReason={
            isPositive && mangaActive
              ? t("promptExpander.composer.mangaModeFixedHint")
              : null
          }
        />
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__btn--primary"
          onClick={() =>
            void (isPositive ? expandPositive() : expandNegative())
          }
          disabled={busy || reason !== null}
          title={
            reason ??
            (isPositive
              ? t("promptExpander.composer.expandPositiveTitle")
              : t("promptExpander.composer.expandNegativeTitle"))
          }
        >
          {runningHere
            ? t("promptExpander.composer.expanding")
            : t("promptExpander.composer.expandButton")}
        </button>
        {extra}
      </div>
    );
  };

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

      {/* ③ プロンプト／指示 */}
      <PromptExpanderSection
        id="prompt"
        title={t("promptExpander.composer.sectionPrompt")}
      >
        {/* 正プロンプト */}
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
            {renderFieldToolbar("positive", suggestButton(suggestReason))}
          </div>
          {mangaActive && (
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
                      : insertIntoPositive(chip.open, chip.close)
                  }
                  disabled={positiveBusy}
                  aria-label={t(`promptExpander.composer.notation.${chip.key}`)}
                  title={t(`promptExpander.composer.notation.${chip.key}`)}
                >
                  {chip.label}
                </button>
              ))}
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__btn--primary prompt-expander__notation-draft"
                onClick={() => void draftScript()}
                disabled={busy || !positiveText.trim()}
                title={t("promptExpander.composer.draftScriptTitle")}
              >
                {t("promptExpander.composer.draftScript")}
              </button>
            </div>
          )}
          <textarea
            id="prompt-expander-positive"
            ref={positiveRef}
            className={`prompt-expander__textarea${positiveBusy ? " prompt-expander__textarea--busy" : ""}`}
            rows={5}
            value={positiveText}
            onChange={(e) => setPositiveText(e.target.value)}
            readOnly={positiveBusy}
            aria-busy={positiveBusy}
            placeholder={
              mangaActive
                ? t("promptExpander.composer.promptPlaceholderManga")
                : t("promptExpander.composer.promptPlaceholder")
            }
          />
          {positiveBusy && (
            <PromptExpanderProgress
              label={
                draftingScript
                  ? t("promptExpander.composer.draftingHint")
                  : t("promptExpander.composer.expandingHint")
              }
            />
          )}
          {scriptDraftBackup && positiveText === scriptDraftBackup.script && (
            <p className="prompt-expander__hint prompt-expander__draft-done">
              <span>{t("promptExpander.composer.draftDone")}</span>
              <button
                type="button"
                className="prompt-expander__btn prompt-expander__btn--sm"
                onClick={undoScriptDraft}
              >
                {t("promptExpander.composer.draftUndo")}
              </button>
            </p>
          )}
          {mangaActive && (
            <>
              <p className="prompt-expander__hint">
                {t("promptExpander.composer.mangaNotationHint")}
              </p>
              <p className="prompt-expander__hint">
                {t("promptExpander.composer.mangaModeFixedHint")}
              </p>
            </>
          )}
          {positiveMode === "japanese" && isV45 && (
            <p className="prompt-expander__hint prompt-expander__hint--warning">
              {t("promptExpander.composer.v45JapaneseHint")}
            </p>
          )}
          <TransparentTailPreview target="positive" />
          <ExpansionErrorNotice target="positive" />
          <PromptExpanderExpansionPanel target="positive" />
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
            {renderFieldToolbar("negative")}
          </div>
          <textarea
            id="prompt-expander-negative"
            className={`prompt-expander__textarea${negativeBusy ? " prompt-expander__textarea--busy" : ""}`}
            rows={3}
            value={negativeText}
            onChange={(e) => setNegativeText(e.target.value)}
            readOnly={negativeBusy}
            aria-busy={negativeBusy}
            placeholder={t("promptExpander.composer.negativePlaceholder")}
          />
          {negativeBusy && (
            <PromptExpanderProgress
              label={t("promptExpander.composer.expandingHint")}
            />
          )}
          <TransparentTailPreview target="negative" />
          <ExpansionErrorNotice target="negative" />
          <PromptExpanderExpansionPanel target="negative" />
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

      {/* ⑤ i2i 設定 */}
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
            {t("promptExpander.composer.pickHistory")}
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

      {/* ⑥ インペイント（部分修正）。i2i 元をベース画像に使い、マスクの領域だけ描き直す */}
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
            {t("promptExpander.composer.pickHistory")}
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

      {/* ⑦ 精密参照（V4.5 系のみ）。i2i 元とは別の参照画像で人物の同一性を固定する */}
      <PromptExpanderSection
        id="reference"
        title={t("promptExpander.composer.sectionReference")}
        defaultOpen={false}
        toolbar={
          <>
            <span className="prompt-expander__section-summary">
              {referenceSummary}
            </span>
            <PromptExpanderSwitch
              checked={settings.use_precise_reference}
              onChange={(checked) =>
                void updateSettings({ use_precise_reference: checked })
              }
              label={t("promptExpander.composer.referenceToggle")}
              disabled={!referenceSupported}
              title={
                referenceSupported
                  ? undefined
                  : t("promptExpander.composer.referenceRequiresV45")
              }
            />
          </>
        }
      >
        {!referenceSupported && (
          <p className="prompt-expander__hint prompt-expander__hint--warning">
            {t("promptExpander.composer.referenceRequiresV45")}
          </p>
        )}
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.referenceHint")}
        </p>
        <div className="prompt-expander__source-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openPicker("reference")}
          >
            {t("promptExpander.composer.pickHistory")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => openUpload("reference")}
          >
            {t("promptExpander.composer.uploadImage")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={clearReference}
            disabled={!reference}
            title={
              reference ? undefined : t("promptExpander.composer.referenceNone")
            }
          >
            {t("promptExpander.composer.referenceClear")}
          </button>
        </div>
        <div className="prompt-expander__source-row">
          {reference ? (
            <>
              <img
                className="prompt-expander__thumb"
                src={reference.thumbnailUrl}
                alt=""
              />
              <div className="prompt-expander__source-info">
                <span className="prompt-expander__source-label">
                  {reference.label}
                </span>
                <span className="prompt-expander__badge">
                  {referenceKindLabel}
                </span>
              </div>
            </>
          ) : (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.referenceNone")}
            </span>
          )}
        </div>
        {settings.use_precise_reference && referenceSupported && !reference && (
          <p className="prompt-expander__hint prompt-expander__hint--warning">
            {t("promptExpander.composer.referenceNoImage")}
          </p>
        )}
        <div className="prompt-expander__reference-type">
          <span className="prompt-expander__label">
            {t("promptExpander.composer.referenceTypeLabel")}
          </span>
          <div
            className="prompt-expander__radio-group prompt-expander__radio-group--compact"
            role="radiogroup"
            aria-label={t("promptExpander.composer.referenceTypeLabel")}
          >
            {PROMPT_EXPANDER_REFERENCE_TYPES.map((type) => (
              <label
                key={type}
                className={`prompt-expander__radio ${settings.reference_type === type ? "is-active" : ""}`}
              >
                <input
                  type="radio"
                  name="prompt-expander-reference-type"
                  value={type}
                  checked={settings.reference_type === type}
                  onChange={() => void updateSettings({ reference_type: type })}
                />
                {t(
                  `promptExpander.composer.referenceType.${referenceTypeI18nKey(type)}`,
                )}
              </label>
            ))}
          </div>
        </div>
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-reference-strength"
          >
            {t("promptExpander.composer.referenceStrength")}:{" "}
            {settings.reference_strength.toFixed(2)}
          </label>
          <input
            id="prompt-expander-reference-strength"
            type="range"
            className="prompt-expander__range"
            min={0}
            max={1}
            step={0.05}
            value={settings.reference_strength}
            disabled={!reference}
            title={
              reference
                ? undefined
                : t("promptExpander.composer.referenceDisabledReason")
            }
            onChange={(e) =>
              updateSettingsDebounced({
                reference_strength: Number.parseFloat(e.target.value),
              })
            }
          />
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-reference-fidelity"
          >
            {t("promptExpander.composer.referenceFidelity")}:{" "}
            {settings.reference_fidelity.toFixed(2)}
          </label>
          <input
            id="prompt-expander-reference-fidelity"
            type="range"
            className="prompt-expander__range"
            min={0}
            max={1}
            step={0.05}
            value={settings.reference_fidelity}
            disabled={!reference}
            title={
              reference
                ? undefined
                : t("promptExpander.composer.referenceDisabledReason")
            }
            onChange={(e) =>
              updateSettingsDebounced({
                reference_fidelity: Number.parseFloat(e.target.value),
              })
            }
          />
          {!reference && (
            <span className="prompt-expander__hint">
              {t("promptExpander.composer.referenceDisabledReason")}
            </span>
          )}
        </div>
        <span className="prompt-expander__hint">
          {t("promptExpander.composer.referenceCostHint", {
            cost: options.anlasPerReference,
          })}
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
