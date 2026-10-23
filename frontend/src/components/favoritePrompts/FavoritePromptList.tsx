/**
 * お気に入りプロンプトの一覧ビュー。
 *
 * 未分類のチップ → カテゴリーごとの折りたたみ行の順に並べる。カテゴリーの開閉状態は
 * localStorage に保持し、ヘッダーのボタンでまとめて開閉できる。チップをクリックすると
 * 呼び出し元の入力欄へ内容を挿入する。ホバー/フォーカス中のチップは下部に全文を出す。
 * チップはドラッグ＆ドロップで並べ替え・カテゴリー移動ができる（チップの左右どちら寄りか
 * で挿入位置を決め、各グループ末尾の点線枠やカテゴリー見出しへのドロップは末尾に入れる）。
 */

import {
  type CSSProperties,
  type DragEvent,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type {
  FavoritePrompt,
  FavoritePromptCategory,
} from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import { usePersistedState } from "../../hooks/usePersistedState";
import {
  type FavoritePromptDropTarget,
  groupFavoritePrompts,
} from "../../utils/favoritePromptOrder";
import {
  CloseIcon,
  CollapseAllIcon,
  ExpandAllIcon,
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

// ファイルや文字列のドラッグと区別するための独自の形式
const DRAG_TYPE = "application/x-tsf-closet-favorite-prompt";

// 折りたたみ中のカテゴリー ID の配列（未記録のカテゴリーは開いた状態で出す）
const COLLAPSED_STORAGE_KEY = "favorite_prompt_categories_collapsed";

function parseCollapsedIds(raw: string): string[] {
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || !parsed.every((id) => typeof id === "string")) {
    throw new Error("invalid collapsed category ids");
  }
  return parsed;
}

function colorStyle(color: string): CSSProperties {
  return { "--favorite-prompt-color": color } as CSSProperties;
}

function sameTarget(
  a: FavoritePromptDropTarget | null,
  b: FavoritePromptDropTarget | null,
): boolean {
  return a?.categoryId === b?.categoryId && a?.beforeId === b?.beforeId;
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
  const { prompts, categories, loaded, loading, insertPrompt, movePrompt } =
    useFavoritePrompts();
  const [collapsedIds, setCollapsedIds] = usePersistedState<string[]>(
    COLLAPSED_STORAGE_KEY,
    [],
    { deserialize: parseCollapsedIds },
  );
  const [previewId, setPreviewId] = useState<string | null>(null);
  // ドロップ処理は ref を読む（dragover による state 更新の反映を待たない）
  const draggingRef = useRef<string | null>(null);
  const dropTargetRef = useRef<FavoritePromptDropTarget | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<FavoritePromptDropTarget | null>(
    null,
  );

  const { uncategorized, byCategory } = useMemo(
    () => groupFavoritePrompts(prompts, categories),
    [prompts, categories],
  );

  const collapsed = useMemo(() => new Set(collapsedIds), [collapsedIds]);
  const allCategoriesOpen = categories.every((c) => !collapsed.has(c.id));
  const toggleAllLabel = allCategoriesOpen
    ? t("favoritePrompts.collapseAllCategories")
    : t("favoritePrompts.expandAllCategories");

  const preview = prompts.find((p) => p.id === previewId) ?? null;
  const isEmpty = loaded && prompts.length === 0 && categories.length === 0;

  const toggleCategory = (categoryId: string) => {
    setCollapsedIds((prev) => {
      // 削除済みカテゴリーの ID は保存し直すときに落とす
      const kept = prev.filter(
        (id) => id !== categoryId && categories.some((c) => c.id === id),
      );
      return prev.includes(categoryId) ? kept : [...kept, categoryId];
    });
  };

  const toggleAllCategories = () => {
    setCollapsedIds(allCategoriesOpen ? categories.map((c) => c.id) : []);
  };

  const showDropTarget = (target: FavoritePromptDropTarget | null) => {
    dropTargetRef.current = target;
    setDropTarget((prev) => (sameTarget(prev, target) ? prev : target));
  };

  const startDrag = (event: DragEvent<HTMLLIElement>, promptId: string) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(DRAG_TYPE, promptId);
    draggingRef.current = promptId;
    // つかんだ瞬間のドラッグ画像まで半透明にならないよう、見た目は次のタスクで変える
    window.setTimeout(() => setDraggingId(draggingRef.current), 0);
  };

  const endDrag = () => {
    draggingRef.current = null;
    setDraggingId(null);
    showDropTarget(null);
  };

  /** お気に入りプロンプトのドラッグ中ならドロップを受け付け、挿入位置を表示する */
  const acceptDrag = (
    event: DragEvent,
    target: FavoritePromptDropTarget | null,
  ) => {
    if (!draggingRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    showDropTarget(target);
  };

  const dropAt = (
    event: DragEvent,
    target: FavoritePromptDropTarget | null,
  ) => {
    const promptId = draggingRef.current;
    if (!promptId) return;
    event.preventDefault();
    event.stopPropagation();
    endDrag();
    if (target) void movePrompt(promptId, target);
  };

  /** チップの左半分なら直前、右半分なら直後。自分自身の前後は移動しないので null */
  const chipTarget = (
    event: DragEvent<HTMLLIElement>,
    items: FavoritePrompt[],
    index: number,
    categoryId: string | null,
  ): FavoritePromptDropTarget | null => {
    const rect = event.currentTarget.getBoundingClientRect();
    const beforeId =
      event.clientX < rect.left + rect.width / 2
        ? items[index].id
        : (items[index + 1]?.id ?? null);
    if (
      items[index].id === draggingRef.current ||
      beforeId === draggingRef.current
    ) {
      return null;
    }
    return { categoryId, beforeId };
  };

  /** チップの隙間では直前の挿入位置を保つ（別のグループから来たら末尾） */
  const gapTarget = (categoryId: string | null): FavoritePromptDropTarget => {
    const current = dropTargetRef.current;
    return current?.categoryId === categoryId
      ? current
      : { categoryId, beforeId: null };
  };

  /**
   * ドロップ先の要素に付けるハンドラー。dragover だけでなく dragenter でも受け付ける
   * （要素に入った直後の dragover が届かないことがあり、挿入位置の表示が遅れるため）。
   */
  const dropHandlers = <T extends HTMLElement>(
    getTarget: (event: DragEvent<T>) => FavoritePromptDropTarget | null,
  ) => ({
    onDragEnter: (event: DragEvent<T>) => acceptDrag(event, getTarget(event)),
    onDragOver: (event: DragEvent<T>) => acceptDrag(event, getTarget(event)),
    onDrop: (event: DragEvent<T>) => dropAt(event, getTarget(event)),
  });

  const isGroupEnd = (categoryId: string | null) =>
    dropTarget?.categoryId === categoryId && dropTarget.beforeId === null;

  const renderGroup = (items: FavoritePrompt[], categoryId: string | null) => (
    <ul
      className="favorite-prompts__chips"
      {...dropHandlers(() => gapTarget(categoryId))}
    >
      {items.map((prompt, index) => (
        <li
          key={prompt.id}
          className={[
            "favorite-prompts__chip",
            prompt.id === draggingId ? "is-dragging" : "",
            dropTarget?.categoryId === categoryId &&
            dropTarget.beforeId === prompt.id
              ? "is-drop-before"
              : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={colorStyle(prompt.color)}
          draggable
          onDragStart={(event) => startDrag(event, prompt.id)}
          onDragEnd={endDrag}
          {...dropHandlers<HTMLLIElement>((event) =>
            chipTarget(event, items, index, categoryId),
          )}
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
      {draggingId !== null && (
        <li
          className={`favorite-prompts__drop-zone${isGroupEnd(categoryId) ? " is-active" : ""}`}
          {...dropHandlers(() => ({ categoryId, beforeId: null }))}
        >
          {categoryId === null && items.length === 0
            ? t("favoritePrompts.dropToUncategorized")
            : t("favoritePrompts.dropHere")}
        </li>
      )}
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
          {categories.length > 0 && (
            <button
              type="button"
              className="favorite-prompts__icon-btn"
              onClick={toggleAllCategories}
              aria-label={toggleAllLabel}
              title={toggleAllLabel}
            >
              {allCategoriesOpen ? (
                <CollapseAllIcon size={18} />
              ) : (
                <ExpandAllIcon size={18} />
              )}
            </button>
          )}
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

      <div
        className="favorite-prompts__body"
        onDragLeave={(event) => {
          // 一覧の外へ出たら挿入位置の表示を消す
          if (!event.currentTarget.contains(event.relatedTarget as Node)) {
            showDropTarget(null);
          }
        }}
      >
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
        {(uncategorized.length > 0 || draggingId !== null) &&
          renderGroup(uncategorized, null)}
        {categories.map((category) => {
          const items = byCategory.get(category.id) ?? [];
          const open = !collapsed.has(category.id);
          return (
            <section
              key={category.id}
              className="favorite-prompts__category"
              style={colorStyle(category.color)}
            >
              {/* 見出しへのドロップは末尾に入れる（折りたたみ中でも移せるように） */}
              <div
                className={`favorite-prompts__category-head${isGroupEnd(category.id) ? " is-drop-target" : ""}`}
                {...dropHandlers(() => ({
                  categoryId: category.id,
                  beforeId: null,
                }))}
              >
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
                (items.length > 0 || draggingId !== null ? (
                  renderGroup(items, category.id)
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
