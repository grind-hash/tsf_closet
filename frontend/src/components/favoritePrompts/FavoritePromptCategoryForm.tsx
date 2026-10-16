/**
 * お気に入りプロンプトのカテゴリー作成 / 編集フォーム。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FavoritePromptCategory } from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import FavoritePromptColorField, {
  DEFAULT_FAVORITE_PROMPT_COLOR,
} from "./FavoritePromptColorField";
import { CloseIcon, TrashIcon } from "./FavoritePromptIcons";

interface FavoritePromptCategoryFormProps {
  titleId: string;
  /** 編集対象。null なら新規作成 */
  category: FavoritePromptCategory | null;
  onDone: () => void;
  onCancel: () => void;
  /** 削除確認を開いている間 true（親の Escape 処理を止めるため） */
  onChildOpenChange: (open: boolean) => void;
}

export default function FavoritePromptCategoryForm({
  titleId,
  category,
  onDone,
  onCancel,
  onChildOpenChange,
}: FavoritePromptCategoryFormProps) {
  const { t } = useTranslation();
  const { createCategory, updateCategory, deleteCategory } =
    useFavoritePrompts();
  const nameId = useId();
  const colorLabelId = useId();
  const nameRef = useRef<HTMLInputElement>(null);

  const [label, setLabel] = useState(category?.label ?? "");
  const [color, setColor] = useState(
    category?.color ?? DEFAULT_FAVORITE_PROMPT_COLOR,
  );
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  useEffect(() => {
    onChildOpenChange(confirmDelete);
  }, [confirmDelete, onChildOpenChange]);

  const canSave = label.trim() !== "" && !busy;

  const handleSubmit = async () => {
    if (!canSave) return;
    setBusy(true);
    const input = { label: label.trim(), color };
    const result = category
      ? await updateCategory(category.id, input)
      : await createCategory(input);
    setBusy(false);
    if (result) onDone();
  };

  const handleDelete = async () => {
    if (!category) return;
    setBusy(true);
    const deleted = await deleteCategory(category.id);
    setBusy(false);
    setConfirmDelete(false);
    if (deleted) onDone();
  };

  return (
    <form
      className="favorite-prompts__form"
      onSubmit={(e) => {
        e.preventDefault();
        void handleSubmit();
      }}
    >
      <header className="favorite-prompts__header">
        <h2 id={titleId} className="favorite-prompts__title">
          {category
            ? t("favoritePrompts.editCategory")
            : t("favoritePrompts.newCategory")}
        </h2>
        <div className="favorite-prompts__header-actions">
          <button
            type="button"
            className="favorite-prompts__icon-btn"
            onClick={onCancel}
            aria-label={t("common.close")}
            title={t("common.close")}
          >
            <CloseIcon size={18} />
          </button>
        </div>
      </header>

      <div className="favorite-prompts__body favorite-prompts__fields">
        <div className="favorite-prompts__field">
          <label className="favorite-prompts__field-label" htmlFor={nameId}>
            {t("favoritePrompts.name")}
          </label>
          <input
            ref={nameRef}
            id={nameId}
            type="text"
            className="favorite-prompts__input"
            value={label}
            maxLength={80}
            placeholder={t("favoritePrompts.categoryNamePlaceholder")}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="favorite-prompts__field">
          <span id={colorLabelId} className="favorite-prompts__field-label">
            {t("favoritePrompts.color")}
          </span>
          <FavoritePromptColorField
            value={color}
            onChange={setColor}
            labelId={colorLabelId}
          />
        </div>
      </div>

      <footer className="favorite-prompts__footer">
        {category && (
          <button
            type="button"
            className="favorite-prompts__delete"
            onClick={() => setConfirmDelete(true)}
            aria-label={t("favoritePrompts.deleteCategory")}
            title={t("favoritePrompts.deleteCategory")}
            disabled={busy}
          >
            <TrashIcon size={16} />
          </button>
        )}
        <div className="favorite-prompts__footer-actions">
          <button
            type="button"
            className="favorite-prompts__btn"
            onClick={onCancel}
            disabled={busy}
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            className="favorite-prompts__btn favorite-prompts__btn--primary"
            disabled={!canSave}
          >
            {t("common.save")}
          </button>
        </div>
      </footer>

      <ConfirmDialog
        open={confirmDelete}
        title={t("favoritePrompts.deleteCategory")}
        confirmLabel={t("common.delete")}
        cancelLabel={t("common.cancel")}
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDelete(false)}
        busy={busy}
      >
        {t("favoritePrompts.deleteCategoryConfirm", {
          name: category?.label ?? "",
        })}
      </ConfirmDialog>
    </form>
  );
}
