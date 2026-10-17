/**
 * お気に入りプロンプトの一覧ビュー。
 *
 * 未分類のチップ → カテゴリーごとの折りたたみ行の順に並べる。チップをクリックすると
 * 呼び出し元の入力欄へ内容を挿入する。ホバー/フォーカス中のチップは下部に全文を出す。
 */

import { type CSSProperties, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  FavoritePrompt,
  FavoritePromptCategory,
} from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import {
  CloseIcon,
  FavoritePromptInsertIcon,
  FileTransferIcon,
  FolderPlusIcon,
  PencilIcon,
  PlusIcon,
} from "./FavoritePromptIcons";

interface FavoritePromptListProps {
  titleId: string;
  onClose: () => void;
  onAddPrompt: () => void;
  onAddCategory: () => void;
  onOpenTransfer: () => void;
  onEditPrompt: (prompt: FavoritePrompt) => void;
  onEditCategory: (category: FavoritePromptCategory) => void;
}

function colorStyle(color: string): CSSProperties {
  return { "--favorite-prompt-color": color } as CSSProperties;
}

export default function FavoritePromptList({
  titleId,
  onClose,
  onAddPrompt,
  onAddCategory,
  onOpenTransfer,
  onEditPrompt,
  onEditCategory,
}: FavoritePromptListProps) {
  const { t } = useTranslation();
  const { prompts, categories, loaded, loading, insertPrompt } =
    useFavoritePrompts();
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [previewId, setPreviewId] = useState<string | null>(null);

  const { uncategorized, byCategory } = useMemo(() => {
    const known = new Set(categories.map((c) => c.id));
    const grouped = new Map<string, FavoritePrompt[]>();
    const loose: FavoritePrompt[] = [];
    for (const prompt of prompts) {
      if (prompt.category_id && known.has(prompt.category_id)) {
        const list = grouped.get(prompt.category_id) ?? [];
        list.push(prompt);
        grouped.set(prompt.category_id, list);
      } else {
        loose.push(prompt);
      }
    }
    return { uncategorized: loose, byCategory: grouped };
  }, [prompts, categories]);

  const preview = prompts.find((p) => p.id === previewId) ?? null;
  const isEmpty = loaded && prompts.length === 0 && categories.length === 0;

  const toggleCategory = (categoryId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  };

  const renderChips = (items: FavoritePrompt[]) => (
    <ul className="favorite-prompts__chips">
      {items.map((prompt) => (
        <li
          key={prompt.id}
          className="favorite-prompts__chip"
          style={colorStyle(prompt.color)}
        >
          <button
            type="button"
            className="favorite-prompts__chip-main"
            onClick={() => insertPrompt(prompt.content)}
            onMouseEnter={() => setPreviewId(prompt.id)}
            onFocus={() => setPreviewId(prompt.id)}
          >
            <span className="favorite-prompts__dot" aria-hidden="true" />
            <span className="favorite-prompts__chip-label">{prompt.label}</span>
          </button>
          <button
            type="button"
            className="favorite-prompts__chip-edit"
            onClick={() => onEditPrompt(prompt)}
            aria-label={t("favoritePrompts.editItem", { name: prompt.label })}
            title={t("favoritePrompts.editItem", { name: prompt.label })}
          >
            <PencilIcon size={12} />
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <>
      <header className="favorite-prompts__header">
        <h2 id={titleId} className="favorite-prompts__title">
          <FavoritePromptInsertIcon size={18} />
          {t("favoritePrompts.title")}
        </h2>
        <div className="favorite-prompts__header-actions">
          <button
            type="button"
            className="favorite-prompts__icon-btn"
            onClick={onOpenTransfer}
            aria-label={t("favoritePrompts.transfer.open")}
            title={t("favoritePrompts.transfer.open")}
          >
            <FileTransferIcon size={18} />
          </button>
          <button
            type="button"
            className="favorite-prompts__icon-btn"
            onClick={onAddCategory}
            aria-label={t("favoritePrompts.addCategory")}
            title={t("favoritePrompts.addCategory")}
          >
            <FolderPlusIcon size={18} />
          </button>
          <button
            type="button"
            className="favorite-prompts__icon-btn"
            onClick={onAddPrompt}
            aria-label={t("favoritePrompts.addPrompt")}
            title={t("favoritePrompts.addPrompt")}
          >
            <PlusIcon size={18} />
          </button>
          <button
            type="button"
            className="favorite-prompts__icon-btn"
            onClick={onClose}
            aria-label={t("common.close")}
            title={t("common.close")}
          >
            <CloseIcon size={18} />
          </button>
        </div>
      </header>
      <p className="favorite-prompts__note">
        {t("favoritePrompts.storageNote")}
      </p>

      <div className="favorite-prompts__body">
        {!loaded && loading && (
          <div className="favorite-prompts__loading" role="status">
            <span className="favorite-prompts__spinner" aria-hidden="true" />
            {t("common.loading")}
          </div>
        )}
        {isEmpty && (
          <p className="favorite-prompts__empty">
            {t("favoritePrompts.empty")}
          </p>
        )}
        {uncategorized.length > 0 && renderChips(uncategorized)}
        {categories.map((category) => {
          const items = byCategory.get(category.id) ?? [];
          const open = !collapsed.has(category.id);
          return (
            <section
              key={category.id}
              className="favorite-prompts__category"
              style={colorStyle(category.color)}
            >
              <div className="favorite-prompts__category-head">
                <button
                  type="button"
                  className="favorite-prompts__category-toggle"
                  onClick={() => toggleCategory(category.id)}
                  aria-expanded={open}
                  title={t("favoritePrompts.toggleCategory", {
                    name: category.label,
                  })}
                >
                  <span className="favorite-prompts__caret" aria-hidden="true">
                    {open ? "▼" : "▶"}
                  </span>
                  <span className="favorite-prompts__dot" aria-hidden="true" />
                  <span className="favorite-prompts__category-label">
                    {category.label}
                  </span>
                  <span className="favorite-prompts__category-count">
                    {items.length}
                  </span>
                </button>
                <button
                  type="button"
                  className="favorite-prompts__chip-edit"
                  onClick={() => onEditCategory(category)}
                  aria-label={t("favoritePrompts.editItem", {
                    name: category.label,
                  })}
                  title={t("favoritePrompts.editItem", {
                    name: category.label,
                  })}
                >
                  <PencilIcon size={12} />
                </button>
              </div>
              {open &&
                (items.length > 0 ? (
                  renderChips(items)
                ) : (
                  <p className="favorite-prompts__empty-category">
                    {t("favoritePrompts.emptyCategory")}
                  </p>
                ))}
            </section>
          );
        })}
      </div>

      <div className="favorite-prompts__preview" aria-live="polite">
        {preview ? (
          <>
            <div className="favorite-prompts__preview-label">
              {preview.label}
            </div>
            <p className="favorite-prompts__preview-content">
              {preview.content}
            </p>
          </>
        ) : (
          <p className="favorite-prompts__preview-hint">
            {t("favoritePrompts.previewHint")}
          </p>
        )}
      </div>
    </>
  );
}
