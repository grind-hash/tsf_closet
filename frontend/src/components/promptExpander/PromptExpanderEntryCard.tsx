/**
 * PromptExpanderEntryCard - エントリ 1 件のカード
 *
 * 画像（クリックでプレビュー）、主テキスト（指示または最終プロンプト。省略表示 + 全文展開）、
 * 行末のバッジ（モデル / サイズ / seed / 拡張モード / 生成元 / アップロード）、
 * 操作（欄へ復元 / i2i 元にする / 通常プレイで使う / TSFシナリオで使う / 削除）。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  type PromptExpanderEntry,
  promptExpanderImageUrl,
} from "../../apis/promptExpander";
import { getPromptExpanderImageModelShortLabel } from "../../constants/promptExpander";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import { useSettings } from "../../contexts/SettingsContext";
import PromptExpanderDeleteButton from "./PromptExpanderDeleteButton";
import "./PromptExpanderShared.css";
import "./PromptExpanderEntryList.css";

const MAIN_TEXT_LIMIT = 160;

interface PromptExpanderEntryCardProps {
  entry: PromptExpanderEntry;
  onPreview: (entry: PromptExpanderEntry) => void;
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
}: PromptExpanderEntryCardProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const { clearSession } = useGame();
  const { clearMessages } = useChat();
  const { restoreEntry, selectEntryAsSource, deleteEntry, source } =
    usePromptExpander();
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const isUploaded = entry.kind === "uploaded";
  const mainText =
    entry.instruction?.trim() ||
    entry.final_prompt?.trim() ||
    (isUploaded ? t("promptExpander.entry.uploadedNoText") : "");
  const truncated =
    !expanded && mainText.length > MAIN_TEXT_LIMIT
      ? `${mainText.slice(0, MAIN_TEXT_LIMIT)}…`
      : mainText;
  const hasDetails =
    mainText.length > MAIN_TEXT_LIMIT ||
    Boolean(entry.final_prompt?.trim()) ||
    Boolean(entry.final_negative_prompt?.trim()) ||
    entry.character_prompts.length > 0;
  const isCurrentSource =
    source?.kind === "entry" && source.entryId === entry.id;

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

  const handleUseInGame = () => {
    clearSession();
    clearMessages();
    navigate(`/play/new?pe_entry=${encodeURIComponent(entry.id)}`);
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
      className={`prompt-expander__entry ${isCurrentSource ? "prompt-expander__entry--source" : ""}`}
    >
      <button
        type="button"
        className="prompt-expander__entry-image-btn"
        onClick={() => onPreview(entry)}
        aria-label={t("promptExpander.entry.preview")}
      >
        <img
          className="prompt-expander__entry-image"
          src={promptExpanderImageUrl(entry)}
          alt=""
          loading="lazy"
        />
      </button>
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
            {entry.instruction?.trim() && (
              <>
                <dt>{t("promptExpander.entry.instruction")}</dt>
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
          </dl>
        )}
        <div className="prompt-expander__entry-actions">
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => restoreEntry(entry)}
            disabled={isUploaded && !entry.final_prompt}
          >
            {t("promptExpander.entry.restore")}
          </button>
          <button
            type="button"
            className={`prompt-expander__btn prompt-expander__btn--sm ${isCurrentSource ? "prompt-expander__btn--primary" : ""}`}
            onClick={() => selectEntryAsSource(entry)}
          >
            {t("promptExpander.entry.useAsSource")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={handleUseInGame}
          >
            {t("promptExpander.entry.useInGame")}
          </button>
          {settingsState.experimentalAdventureEnabled && (
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
