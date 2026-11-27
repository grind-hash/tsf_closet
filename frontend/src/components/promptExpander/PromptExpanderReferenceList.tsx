/**
 * 精密参照（複数枚）のセクション。
 *
 * 画像ごとに種別・衣装・強度・忠実度を持ち、キャラ系の参照には名前と外見タグを付けられる。
 * 名前を付けた参照は登場人物として、プロンプト化（キャラ枠 ON のとき）とネーム下書きに渡る。
 * 項目はモデルで出し分けず、効かない組み合わせは無効表示と注記で伝える。
 */

import { useTranslation } from "react-i18next";
import {
  isCharacterReferenceType,
  PROMPT_EXPANDER_CAST_NAME_MAX_LENGTH,
  PROMPT_EXPANDER_CAST_TAGS_MAX_LENGTH,
  PROMPT_EXPANDER_MULTI_CHARACTER_REFERENCE_STRENGTH,
  PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
  PROMPT_EXPANDER_REFERENCE_TYPES,
  referenceTypeI18nKey,
} from "../../constants/promptExpander";
import {
  type PromptExpanderReference,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import {
  clampReferenceStrength,
  isReferenceTypeSupported,
  PRECISE_REFERENCE_STRENGTH_MAX,
  referenceTypeUsesOutfit,
} from "../../utils/preciseReferences";
import PromptExpanderSection from "./PromptExpanderSection";
import PromptExpanderSwitch from "./PromptExpanderSwitch";

interface PromptExpanderReferenceListProps {
  /** 一覧から選ぶ（ピッカーを精密参照の追加先で開く） */
  onPick: () => void;
  /** アップロードダイアログを精密参照の追加先で開く */
  onUpload: () => void;
}

export default function PromptExpanderReferenceList({
  onPick,
  onUpload,
}: PromptExpanderReferenceListProps) {
  const { t } = useTranslation();
  const {
    settings,
    options,
    characterMode,
    references,
    sendableReferences,
    referenceCast,
    referenceSupported,
    referenceFormat,
    referenceInpaintBlocked,
    referenceAnlasCost,
    updateSettings,
    updateReference,
    clearReferences,
  } = usePromptExpander();

  const atMax = references.length >= PROMPT_EXPANDER_REFERENCE_MAX_COUNT;
  const characterReferences = references.filter((ref) =>
    isCharacterReferenceType(ref.type),
  );
  // 2 人以上のキャラを参照で描き分けるときは、強度を下げた方が混ざりにくい
  const multiCharacter = characterReferences.length >= 2;
  const strengthAboveMulti = characterReferences.some(
    (ref) => ref.strength > PROMPT_EXPANDER_MULTI_CHARACTER_REFERENCE_STRENGTH,
  );
  const hasNamedCharacter = characterReferences.some((ref) => ref.name.trim());

  const summary = !referenceSupported
    ? t("promptExpander.composer.referenceSummaryUnsupported")
    : !settings.use_precise_reference
      ? t("promptExpander.composer.referenceSummaryOff")
      : referenceInpaintBlocked
        ? t("promptExpander.composer.referenceSummaryInpaintV5")
        : references.length === 0
          ? t("promptExpander.composer.referenceSummaryNoImage")
          : sendableReferences.length === 0
            ? t("promptExpander.composer.referenceSummaryCostumeV45")
            : referenceCast.length > 0
              ? t("promptExpander.composer.referenceSummaryCountWithCast", {
                  count: sendableReferences.length,
                  cast: referenceCast.length,
                  cost: referenceAnlasCost,
                })
              : t("promptExpander.composer.referenceSummaryCount", {
                  count: sendableReferences.length,
                  cost: referenceAnlasCost,
                });

  const alignCharacterStrength = () => {
    for (const ref of characterReferences) {
      updateReference(ref.id, {
        strength: PROMPT_EXPANDER_MULTI_CHARACTER_REFERENCE_STRENGTH,
      });
    }
  };

  return (
    <PromptExpanderSection
      id="reference"
      title={t("promptExpander.composer.sectionReference")}
      defaultOpen={false}
      toolbar={
        <>
          <span className="prompt-expander__section-summary">{summary}</span>
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
                : t("promptExpander.composer.referenceUnsupportedModel")
            }
          />
        </>
      }
    >
      {!referenceSupported && (
        <p className="prompt-expander__hint prompt-expander__hint--warning">
          {t("promptExpander.composer.referenceUnsupportedModel")}
        </p>
      )}
      {referenceInpaintBlocked && settings.use_precise_reference && (
        <p className="prompt-expander__hint prompt-expander__hint--warning">
          {t("promptExpander.composer.referenceInpaintV5")}
        </p>
      )}
      <p className="prompt-expander__hint">
        {t("promptExpander.composer.referenceHint", {
          max: PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
        })}
      </p>
      <div className="prompt-expander__source-actions">
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm"
          onClick={onPick}
          disabled={atMax}
          title={
            atMax
              ? t("promptExpander.composer.referenceMaxReached", {
                  max: PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
                })
              : undefined
          }
        >
          {t("promptExpander.composer.pickFromList")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm"
          onClick={onUpload}
          disabled={atMax}
          title={
            atMax
              ? t("promptExpander.composer.referenceMaxReached", {
                  max: PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
                })
              : undefined
          }
        >
          {t("promptExpander.composer.uploadImage")}
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm"
          onClick={clearReferences}
          disabled={references.length === 0}
          title={
            references.length > 0
              ? undefined
              : t("promptExpander.composer.referenceNone")
          }
        >
          {t("promptExpander.composer.referenceClearAll")}
        </button>
        <span className="prompt-expander__hint">
          {t("promptExpander.composer.referenceCount", {
            count: references.length,
            max: PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
          })}
        </span>
      </div>
      {references.length === 0 ? (
        <p className="prompt-expander__hint">
          {t("promptExpander.composer.referenceNone")}
        </p>
      ) : (
        <ul className="prompt-expander__reference-list">
          {references.map((ref, index) => (
            <ReferenceCard key={ref.id} reference={ref} index={index + 1} />
          ))}
        </ul>
      )}
      {settings.use_precise_reference &&
        referenceSupported &&
        references.length === 0 && (
          <p className="prompt-expander__hint prompt-expander__hint--warning">
            {t("promptExpander.composer.referenceNoImage")}
          </p>
        )}
      {multiCharacter && (
        <div className="prompt-expander__reference-multi">
          <span className="prompt-expander__hint">
            {t("promptExpander.composer.referenceMultiCharacterHint", {
              strength: PROMPT_EXPANDER_MULTI_CHARACTER_REFERENCE_STRENGTH,
            })}
          </span>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={alignCharacterStrength}
            disabled={!strengthAboveMulti}
            data-testid="prompt-expander-reference-align-strength"
          >
            {t("promptExpander.composer.referenceAlignStrength", {
              strength: PROMPT_EXPANDER_MULTI_CHARACTER_REFERENCE_STRENGTH,
            })}
          </button>
          {referenceFormat === "v4_5" && (
            <span className="prompt-expander__hint prompt-expander__hint--warning">
              {t("promptExpander.composer.referenceMultiCharacterV45")}
            </span>
          )}
        </div>
      )}
      {hasNamedCharacter && (
        <p className="prompt-expander__hint">
          {characterMode
            ? t("promptExpander.composer.referenceCastHint")
            : t("promptExpander.composer.referenceCastHintNoCharacterMode")}
        </p>
      )}
      <span className="prompt-expander__hint">
        {t("promptExpander.composer.referenceCostHint", {
          cost: options.anlasPerReference,
        })}
      </span>
    </PromptExpanderSection>
  );
}

function ReferenceCard({
  reference,
  index,
}: {
  reference: PromptExpanderReference;
  index: number;
}) {
  const { t } = useTranslation();
  const { referenceFormat, updateReference, removeReference } =
    usePromptExpander();
  const isV5 = referenceFormat === "v5";
  const strengthMax = PRECISE_REFERENCE_STRENGTH_MAX[referenceFormat ?? "v4_5"];
  const usesOutfit = referenceTypeUsesOutfit(reference.type);
  const typeUnsupported =
    referenceFormat !== null &&
    !isReferenceTypeSupported(reference.type, referenceFormat);
  const isCharacter = isCharacterReferenceType(reference.type);
  const idPrefix = `prompt-expander-reference-${reference.id}`;

  return (
    <li
      className="prompt-expander__reference-card"
      data-testid="prompt-expander-reference-card"
    >
      <div className="prompt-expander__reference-card-head">
        <img
          className="prompt-expander__thumb"
          src={reference.thumbnailUrl}
          alt=""
        />
        <div className="prompt-expander__source-info">
          <span className="prompt-expander__source-label">
            {t("promptExpander.composer.referenceIndex", { index })}{" "}
            {reference.label}
          </span>
          <span className="prompt-expander__badge">
            {t(`promptExpander.composer.sourceKind.${reference.kind}`)}
          </span>
        </div>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__btn--sm prompt-expander__reference-remove"
          onClick={() => removeReference(reference.id)}
        >
          {t("promptExpander.composer.referenceRemove")}
        </button>
      </div>
      <div className="prompt-expander__reference-type">
        <span className="prompt-expander__label">
          {t("promptExpander.composer.referenceTypeLabel")}
        </span>
        <div
          className="prompt-expander__radio-group prompt-expander__radio-group--compact"
          role="radiogroup"
          aria-label={t("promptExpander.composer.referenceTypeLabel")}
        >
          {PROMPT_EXPANDER_REFERENCE_TYPES.map((type) => {
            // 衣装の参照は V5 のみ。選択中なら他モデルでも表示だけは残す
            const typeDisabled =
              referenceFormat !== null &&
              !isReferenceTypeSupported(type, referenceFormat) &&
              reference.type !== type;
            return (
              <label
                key={type}
                className={`prompt-expander__radio ${reference.type === type ? "is-active" : ""}`}
              >
                <input
                  type="radio"
                  name={`${idPrefix}-type`}
                  value={type}
                  checked={reference.type === type}
                  disabled={typeDisabled}
                  onChange={() => updateReference(reference.id, { type })}
                />
                {t(
                  `promptExpander.composer.referenceType.${referenceTypeI18nKey(type)}`,
                )}
              </label>
            );
          })}
        </div>
        {typeUnsupported && (
          <span className="prompt-expander__hint prompt-expander__hint--warning">
            {t("promptExpander.composer.referenceCostumeV5Only")}
          </span>
        )}
      </div>
      {isCharacter && (
        <div className="prompt-expander__reference-cast">
          <label
            className="prompt-expander__label"
            htmlFor={`${idPrefix}-name`}
          >
            {t("promptExpander.composer.referenceName")}
          </label>
          <input
            id={`${idPrefix}-name`}
            type="text"
            className="prompt-expander__input"
            value={reference.name}
            maxLength={PROMPT_EXPANDER_CAST_NAME_MAX_LENGTH}
            placeholder={t("promptExpander.composer.referenceNamePlaceholder")}
            onChange={(e) =>
              updateReference(reference.id, { name: e.target.value })
            }
          />
          <label
            className="prompt-expander__label"
            htmlFor={`${idPrefix}-appearance`}
          >
            {t("promptExpander.composer.referenceAppearance")}
          </label>
          <textarea
            id={`${idPrefix}-appearance`}
            className="prompt-expander__textarea prompt-expander__reference-appearance"
            rows={2}
            value={reference.appearanceTags}
            maxLength={PROMPT_EXPANDER_CAST_TAGS_MAX_LENGTH}
            placeholder={t(
              "promptExpander.composer.referenceAppearancePlaceholder",
            )}
            onChange={(e) =>
              updateReference(reference.id, { appearanceTags: e.target.value })
            }
          />
          <span className="prompt-expander__hint">
            {t("promptExpander.composer.referenceAppearanceHint")}
          </span>
        </div>
      )}
      {/* 衣装も参照する（V5 のキャラ系の参照だけ効く。他は無効にして理由を出す） */}
      <div className="prompt-expander__field">
        <PromptExpanderSwitch
          checked={reference.includeOutfit}
          onChange={(checked) =>
            updateReference(reference.id, { includeOutfit: checked })
          }
          label={t("promptExpander.composer.referenceIncludeOutfit")}
          disabled={!isV5 || !usesOutfit}
        />
        <span className="prompt-expander__hint">
          {!usesOutfit
            ? t("promptExpander.composer.referenceIncludeOutfitCharacterOnly")
            : isV5
              ? t("promptExpander.composer.referenceIncludeOutfitHint")
              : t("promptExpander.composer.referenceIncludeOutfitV5Only")}
        </span>
      </div>
      <div className="prompt-expander__field">
        <label
          className="prompt-expander__label"
          htmlFor={`${idPrefix}-strength`}
        >
          {t("promptExpander.composer.referenceStrength")}:{" "}
          {reference.strength.toFixed(2)}
        </label>
        <input
          id={`${idPrefix}-strength`}
          type="range"
          className="prompt-expander__range"
          min={0}
          max={strengthMax}
          step={0.05}
          value={Math.min(reference.strength, strengthMax)}
          onChange={(e) =>
            updateReference(reference.id, {
              strength: Number.parseFloat(e.target.value),
            })
          }
        />
        {referenceFormat !== null && reference.strength > strengthMax && (
          <span className="prompt-expander__hint">
            {t("promptExpander.composer.referenceStrengthClamped", {
              value: clampReferenceStrength(
                reference.strength,
                referenceFormat,
              ).toFixed(2),
            })}
          </span>
        )}
        <label
          className="prompt-expander__label"
          htmlFor={`${idPrefix}-fidelity`}
        >
          {t("promptExpander.composer.referenceFidelity")}:{" "}
          {reference.fidelity.toFixed(2)}
        </label>
        <input
          id={`${idPrefix}-fidelity`}
          type="range"
          className="prompt-expander__range"
          min={0}
          max={1}
          step={0.05}
          value={reference.fidelity}
          disabled={isV5}
          onChange={(e) =>
            updateReference(reference.id, {
              fidelity: Number.parseFloat(e.target.value),
            })
          }
        />
        {isV5 && (
          <span className="prompt-expander__hint">
            {t("promptExpander.composer.referenceFidelityV5Unused")}
          </span>
        )}
      </div>
    </li>
  );
}
