/**
 * PromptExpanderEntryCard - エントリ 1 件のカード
 *
 * 画像（クリックでプレビュー）、主テキスト（指示または最終プロンプト。省略表示 + 全文展開）、
 * 行末のバッジ（モデル / サイズ / seed / 拡張モード / 生成元 / アップロード / 精密参照 / 透過）、
 * 操作（欄へ復元 / このプロンプトで再生成 / i2i 元にする / 参照にする / キャラクターにする / TSFシナリオで使う / 削除）。
 * 画像は <button> で包まない（ブラウザの「名前を付けて画像を保存」が効かなくなるため）。
 * 背景透過エントリは表示時にフロントで切り抜く（V4.5 は白背景で保存されている。V5 のネイティブ透過は素通し）。
 * 切り抜き後の画像は「透過PNGを保存」からダウンロードできる。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  createCharacterPreset,
  deleteCharacterPreset,
  importCharacterPresetPortrait,
} from "../../apis/characters";
import {
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import {
  getPromptExpanderImageModelShortLabel,
  PROMPT_EXPANDER_ALPHA_OPTIONS,
  PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
  referenceTypeI18nKey,
} from "../../constants/promptExpander";
import { useNotification } from "../../contexts/NotificationContext";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import { useSettings } from "../../contexts/SettingsContext";
import { revealPromptExpanderSection } from "../../hooks/usePersistedSectionState";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import { ROUTES } from "../../routes";
import { EMPTY_CHARACTER_PROFILE } from "../characters/characterMaker";
import PromptExpanderDeleteButton from "./PromptExpanderDeleteButton";
import "./PromptExpanderShared.css";
import "./PromptExpanderEntryList.css";
import { FavoritePromptSaveButton } from "../favoritePrompts/FavoritePromptButtons";

const MAIN_TEXT_LIMIT = 160;

interface PromptExpanderEntryCardProps {
  entry: PromptExpanderEntry;
  onPreview: (entry: PromptExpanderEntry) => void;
  /** プレビューモーダルで表示中（または直前まで表示していた）エントリか */
  isPreviewed?: boolean;
}

function formatDateTime(iso: string, language: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(language.startsWith("en") ? "en-US" : "ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function PromptExpanderEntryCard({
  entry,
  onPreview,
  isPreviewed = false,
}: PromptExpanderEntryCardProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const { showNotification } = useNotification();
  const {
    restoreEntry,
    regenerateEntry,
    selectEntryAsSource,
    clearSource,
    selectEntryAsReference,
    deleteEntry,
    source,
    references,
    generating,
  } = usePromptExpander();
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [makingCharacter, setMakingCharacter] = useState(false);
  const originalUrl = promptExpanderImageUrl(entry);
  // 透過エントリは表示時に背景を切り抜く（既に透過を持つ V5 画像は素通しされる）
  const { url: transparentUrl, processing } = useTransparentImage(
    originalUrl,
    entry.transparent_background,
    PROMPT_EXPANDER_ALPHA_OPTIONS,
  );
  // 表示中の blob URL は useTransparentImage が保持するため通常は失効しないが、
  // 読み込みに失敗した URL は原本へ戻す（URL 単位で覚える）
  const [brokenUrl, setBrokenUrl] = useState<string | null>(null);
  const cutoutUrl =
    entry.transparent_background &&
    transparentUrl &&
    transparentUrl !== brokenUrl
      ? transparentUrl
      : null;
  const displayUrl = cutoutUrl ?? originalUrl;

  const isUploaded = entry.kind === "uploaded";
  const mainText =
    entry.instruction?.trim() ||
    entry.final_prompt?.trim() ||
    (isUploaded ? t("promptExpander.entry.uploadedNoText") : "");
  const truncated =
    !expanded && mainText.length > MAIN_TEXT_LIMIT
      ? `${mainText.slice(0, MAIN_TEXT_LIMIT)}…`
      : mainText;
  const entryReferences = entry.references ?? [];
  const hasReference = entryReferences.length > 0;
  const hasDetails =
    mainText.length > MAIN_TEXT_LIMIT ||
    Boolean(entry.final_prompt?.trim()) ||
    Boolean(entry.final_negative_prompt?.trim()) ||
    entry.character_prompts.length > 0 ||
    hasReference;
  const isCurrentSource =
    source?.kind === "entry" && source.entryId === entry.id;
  const isCurrentReference = references.some(
    (ref) => ref.kind === "entry" && ref.entryId === entry.id,
  );
  const referenceFull =
    references.length >= PROMPT_EXPANDER_REFERENCE_MAX_COUNT;

  const badges: string[] = [];
  if (entry.image_model) {
    badges.push(getPromptExpanderImageModelShortLabel(entry.image_model));
  }
  if (entry.image_size) {
    badges.push(t(`promptExpander.composer.size.${entry.image_size}`));
  }
  if (entry.seed !== null && entry.seed !== undefined) {
    badges.push(t("promptExpander.entry.seedBadge", { value: entry.seed }));
  }
  if (entry.positive_expand_mode !== "off") {
    badges.push(
      t(`promptExpander.entry.expandBadge.${entry.positive_expand_mode}`),
    );
  }
  if (entry.source_kind && entry.source_kind !== "none") {
    badges.push(t(`promptExpander.composer.sourceKind.${entry.source_kind}`));
  }
  if (isUploaded) {
    badges.push(t("promptExpander.entry.badgeUploaded"));
  }
  // 可変幅のバッジは行末に寄せる
  if (entry.manga_mode) {
    badges.push(
      entry.manga_panel_count
        ? t("promptExpander.entry.mangaBadgeCount", {
            count: entry.manga_panel_count,
          })
        : t("promptExpander.entry.mangaBadge"),
    );
  }
  if (entry.inpaint) {
    badges.push(t("promptExpander.entry.inpaintBadge"));
  }
  if (hasReference) {
    badges.push(
      entryReferences.length > 1
        ? t("promptExpander.entry.referenceBadgeCount", {
            count: entryReferences.length,
          })
        : t("promptExpander.entry.referenceBadge"),
    );
  }
  if (entry.transparent_background) {
    badges.push(t("promptExpander.entry.transparentBadge"));
  }

  // エントリの画像を立ち絵にしたキャラクターを作り、編集画面へ移る。
  // 外見タグは空のキャラクターへの取り込みなのでサーバーがエントリから入れる
  const handleMakeCharacter = async () => {
    setMakingCharacter(true);
    let createdId: string | null = null;
    try {
      const created = await createCharacterPreset({
        name: t("characters.newName"),
        profile: EMPTY_CHARACTER_PROFILE,
      });
      createdId = created.id;
      await importCharacterPresetPortrait(created.id, {
        prompt_expander_entry_id: entry.id,
      });
      navigate(`${ROUTES.CHARACTERS}/${created.id}`);
    } catch (err) {
      console.error("Failed to make a character from the entry", err);
      // 立ち絵の無いキャラクターを残さない
      if (createdId) {
        void deleteCharacterPreset(createdId).catch(() => undefined);
      }
      showNotification("error", t("promptExpander.entry.makeCharacterFailed"));
      setMakingCharacter(false);
    }
  };

  const handleUseInAdventure = () => {
    navigate(`/adventure?pe_entry=${encodeURIComponent(entry.id)}`);
  };

  const handleDelete = async () => {
    if (!window.confirm(t("promptExpander.entry.deleteConfirm"))) return;
    setDeleting(true);
    await deleteEntry(entry.id);
    setDeleting(false);
  };

  return (
    <li
      className={[
        "prompt-expander__entry",
        isCurrentSource ? "prompt-expander__entry--source" : "",
        isPreviewed ? "prompt-expander__entry--previewed" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-entry-id={entry.id}
    >
      <div
        className={[
          "prompt-expander__entry-image-btn",
          entry.transparent_background
            ? "prompt-expander__entry-image-btn--transparent"
            : "",
        ]
          .filter(Boolean)
          .join(" ")}
        role="button"
        tabIndex={0}
        onClick={() => onPreview(entry)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onPreview(entry);
          }
        }}
        aria-label={t("promptExpander.entry.preview")}
      >
        <img
          className="prompt-expander__entry-image"
          src={displayUrl}
          alt=""
          loading="lazy"
          onError={() => setBrokenUrl(displayUrl)}
        />
        {processing && (
          <span
            className="prompt-expander__entry-image-processing"
            role="status"
            aria-label={t("promptExpander.entry.transparentProcessing")}
            title={t("promptExpander.entry.transparentProcessing")}
          >
            <span
              className="prompt-expander__progress-spinner"
              aria-hidden="true"
            />
          </span>
        )}
      </div>
      <div className="prompt-expander__entry-body">
        <div className="prompt-expander__entry-row">
          <p className="prompt-expander__entry-text">{truncated}</p>
          <div className="prompt-expander__entry-badges">
            {badges.map((badge) => (
              <span key={badge} className="prompt-expander__badge">
                {badge}
              </span>
            ))}
          </div>
        </div>
        <div className="prompt-expander__entry-meta">
          <span>{formatDateTime(entry.created_at, i18n.language)}</span>
          {hasDetails && (
            <button
              type="button"
              className="prompt-expander__entry-toggle"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
            >
              {expanded
                ? t("promptExpander.entry.collapse")
                : t("promptExpander.entry.expandFull")}
            </button>
          )}
        </div>
        {expanded && (
          <dl className="prompt-expander__entry-details">
            {/* ネームから作ったエントリは、下書き元のあらすじとネームを分けて見せる */}
            {entry.synopsis?.trim() && (
              <>
                <dt>{t("promptExpander.entry.synopsis")}</dt>
                <dd>{entry.synopsis}</dd>
              </>
            )}
            {entry.instruction?.trim() && (
              <>
                <dt>
                  {entry.synopsis?.trim()
                    ? t("promptExpander.entry.script")
                    : t("promptExpander.entry.instruction")}
                </dt>
                <dd>{entry.instruction}</dd>
              </>
            )}
            {entry.final_prompt?.trim() && (
              <>
                <dt>{t("promptExpander.entry.finalPrompt")}</dt>
                <dd>{entry.final_prompt}</dd>
              </>
            )}
            {entry.character_prompts.length > 0 && (
              <>
                <dt>{t("promptExpander.entry.characterPrompts")}</dt>
                <dd>
                  <ol className="prompt-expander__entry-characters">
                    {entry.character_prompts.map((prompt, index) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: 並び順がスロット番号に対応し、テキストは重複しうる
                      <li key={`cp-${index}`}>{prompt}</li>
                    ))}
                  </ol>
                </dd>
              </>
            )}
            {entry.final_negative_prompt?.trim() && (
              <>
                <dt>{t("promptExpander.entry.negativePrompt")}</dt>
                <dd>{entry.final_negative_prompt}</dd>
              </>
            )}
            {hasReference && (
              <>
                <dt>{t("promptExpander.entry.referenceDetail")}</dt>
                <dd>
                  <ol className="prompt-expander__entry-characters">
                    {entryReferences.map((ref, index) => {
                      const typeName = t(
                        `promptExpander.composer.referenceType.${referenceTypeI18nKey(ref.type)}`,
                      );
                      const strength = ref.strength.toFixed(2);
                      // V5 の参照は忠実度を持たず、衣装の有無を記録している
                      const value =
                        ref.fidelity === null
                          ? t("promptExpander.entry.referenceDetailValueV5", {
                              type: ref.include_outfit
                                ? t(
                                    "promptExpander.composer.referenceTypeWithOutfit",
                                    { type: typeName },
                                  )
                                : typeName,
                              strength,
                            })
                          : t("promptExpander.entry.referenceDetailValue", {
                              type: typeName,
                              strength,
                              fidelity: ref.fidelity.toFixed(2),
                            });
                      return (
                        // 参照は並び順が意味を持ち、同じ内容の参照も並びうるため番号で区別する
                        // biome-ignore lint/suspicious/noArrayIndexKey: 記録済みの参照は並べ替えない
                        <li key={index}>
                          {ref.name
                            ? t("promptExpander.entry.referenceDetailNamed", {
                                name: ref.name,
                                value,
                              })
                            : value}
                        </li>
                      );
                    })}
                  </ol>
                </dd>
              </>
            )}
          </dl>
        )}
        <div className="prompt-expander__entry-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => {
              restoreEntry(entry);
              // 復元した欄へ移り、そのまま書き直せるようプロンプト欄へフォーカスする
              revealPromptExpanderSection("prompt", { focus: false });
              window.requestAnimationFrame(() =>
                document
                  .getElementById("prompt-expander-positive")
                  ?.focus({ preventScroll: true }),
              );
            }}
            disabled={isUploaded && !entry.final_prompt}
          >
            {t("promptExpander.entry.restore")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => void regenerateEntry(entry)}
            disabled={generating || !entry.final_prompt?.trim()}
            title={t("promptExpander.entry.regenerateTitle")}
          >
            {t("promptExpander.entry.regenerate")}
          </button>
          <FavoritePromptSaveButton text={entry.final_prompt ?? ""} />
          <button
            type="button"
            className={`prompt-expander__btn prompt-expander__btn--sm ${isCurrentSource ? "prompt-expander__btn--primary" : ""}`}
            onClick={() =>
              isCurrentSource ? clearSource() : selectEntryAsSource(entry)
            }
          >
            {isCurrentSource
              ? t("promptExpander.entry.clearSource")
              : t("promptExpander.entry.useAsSource")}
          </button>
          <button
            type="button"
            className={`prompt-expander__btn prompt-expander__btn--sm ${isCurrentReference ? "prompt-expander__btn--primary" : ""}`}
            onClick={() => selectEntryAsReference(entry)}
            disabled={!isCurrentReference && referenceFull}
            title={
              !isCurrentReference && referenceFull
                ? t("promptExpander.composer.referenceMaxReached", {
                    max: PROMPT_EXPANDER_REFERENCE_MAX_COUNT,
                  })
                : undefined
            }
          >
            {isCurrentReference
              ? t("promptExpander.entry.removeFromReference")
              : t("promptExpander.entry.useAsReference")}
          </button>
          {entry.transparent_background && (
            // 切り抜き後の blob URL（V5 はサーバーの透過 PNG）をそのまま保存させる
            <a
              className={`prompt-expander__btn prompt-expander__btn--sm ${processing ? "is-disabled" : ""}`}
              href={displayUrl}
              download={`${entry.id}.png`}
              aria-disabled={processing}
              onClick={(e) => {
                if (processing) e.preventDefault();
              }}
            >
              {t("promptExpander.entry.downloadTransparent")}
            </a>
          )}
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => void handleMakeCharacter()}
            disabled={makingCharacter}
            aria-busy={makingCharacter}
          >
            {makingCharacter
              ? t("promptExpander.entry.makingCharacter")
              : t("promptExpander.entry.makeCharacter")}
          </button>
          {settingsState.adventureEnabled && (
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={handleUseInAdventure}
            >
              {t("promptExpander.entry.useInAdventure")}
            </button>
          )}
          <PromptExpanderDeleteButton
            label={t("promptExpander.entry.delete")}
            onClick={handleDelete}
            disabled={deleting}
          />
        </div>
      </div>
    </li>
  );
}
