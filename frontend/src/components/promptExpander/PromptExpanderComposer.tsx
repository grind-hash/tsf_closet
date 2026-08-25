/**
 * PromptExpanderComposer - Prompt Expander の入力欄
 *
 * 上から ① 生成パラメータ ② プロンプト／指示（正 + ネガティブ。各欄の右上に
 * モード切替・拡張・提案のツールバー、拡張結果は欄の直下にインライン表示）
 * ③ キャラクタープロンプト ④ i2i 設定 の開閉セクションと、最下部の「生成」ボタン。
 */

import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
import {
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
  type PromptExpanderImageSize,
  type PromptExpanderMangaLayout,
  type PromptExpanderMangaReadingDirection,
  type PromptExpanderMangaTextLanguage,
  type PromptExpandMode,
  supportsMangaMode,
} from "../../constants/promptExpander";
import {
  type PromptExpanderExpansionTarget,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import PromptExpanderCharacterSlots from "./PromptExpanderCharacterSlots";
import PromptExpanderExpansionPanel from "./PromptExpanderExpansionPanel";
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

export default function PromptExpanderComposer() {
  const { t } = useTranslation();
  const {
    settings,
    options,
    source,
    clearSource,
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
    runGenerate,
    canGenerate,
    generateDisabledReason,
    expanding,
    expandingTarget,
    generating,
    expandPositive,
    expandNegative,
  } = usePromptExpander();

  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [seedDraft, setSeedDraft] = useState<string | null>(null);

  const isV45 = !isV5ImageModel(settings.image_model);
  const mangaSupported = supportsMangaMode(settings.image_model);
  const busy = expanding || generating;
  // LLM でプロンプト化している欄は読み取り専用にして処理中を示す
  const positiveBusy = expandingTarget === "positive";
  const negativeBusy = expandingTarget === "negative";
  const notConfigured = !options.novelaiConfigured;
  const notConfiguredText = t("promptExpander.composer.disabledNotConfigured");

  const disabledReasonText = (() => {
    switch (generateDisabledReason) {
      case "novelai_not_configured":
        return notConfiguredText;
      case "no_session":
        return t("promptExpander.composer.disabledNoSession");
      case "too_many_characters":
        return t("promptExpander.composer.disabledTooMany");
      case "empty_prompt":
        return t("promptExpander.composer.disabledEmptyPrompt");
      case "pending_expansion":
        return t("promptExpander.composer.disabledPendingExpansion");
      default:
        return null;
    }
  })();

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
        ].join(" · ");

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
        </div>
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
          <textarea
            id="prompt-expander-positive"
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
              label={t("promptExpander.composer.expandingHint")}
            />
          )}
          {mangaActive && (
            <p className="prompt-expander__hint">
              {t("promptExpander.composer.mangaModeFixedHint")}
            </p>
          )}
          {positiveMode === "japanese" && isV45 && (
            <p className="prompt-expander__hint prompt-expander__hint--warning">
              {t("promptExpander.composer.v45JapaneseHint")}
            </p>
          )}
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
            onClick={() => setPickerOpen(true)}
          >
            {t("promptExpander.composer.pickHistory")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => setUploadOpen(true)}
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

      {/* 生成ボタン */}
      <div className="prompt-expander__generate-row">
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--primary prompt-expander__generate"
          disabled={!canGenerate}
          onClick={() => void runGenerate()}
          title={disabledReasonText ?? undefined}
        >
          {generating
            ? t("promptExpander.composer.generating")
            : t("promptExpander.composer.generate")}
        </button>
        {disabledReasonText && !busy && (
          <span className="prompt-expander__hint prompt-expander__hint--warning">
            {disabledReasonText}
          </span>
        )}
      </div>

      <PromptExpanderSourcePickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />
      <PromptExpanderUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
      />
      <PromptExpanderSuggestModal
        open={suggestOpen}
        onClose={() => setSuggestOpen(false)}
      />
    </div>
  );
}
