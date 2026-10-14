/**
 * お気に入りプロンプトの新規作成 / 編集フォーム。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FavoritePrompt } from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import FavoritePromptColorField, {
  DEFAULT_FAVORITE_PROMPT_COLOR,
} from "./FavoritePromptColorField";
import { CloseIcon, TrashIcon } from "./FavoritePromptIcons";

interface FavoritePromptFormProps {
  titleId: string;
  /** 編集対象。null なら新規作成 */
  prompt: FavoritePrompt | null;
  /** 新規作成時の内容の初期値（保存ボタンから開いたときの対象テキスト） */
  initialContent?: string;
  /** 保存・削除が済んだとき */
  onDone: () => void;
  onCancel: () => void;
  /** 削除確認を開いている間 true（親の Escape 処理を止めるため） */
  onChildOpenChange: (open: boolean) => void;
}

export default function FavoritePromptForm({
  titleId,
  prompt,
  initialContent = "",
  onDone,
  onCancel,
  onChildOpenChange,
}: FavoritePromptFormProps) {
  const { t } = useTranslation();
  const { categories, createPrompt, updatePrompt, deletePrompt } =
    useFavoritePrompts();
  const nameId = useId();
  const contentId = useId();
  const categoryId = useId();
  const colorLabelId = useId();
  const nameRef = useRef<HTMLInputElement>(null);

  const [label, setLabel] = useState(prompt?.label ?? "");
  const [content, setContent] = useState(prompt?.content ?? initialContent);
  const [category, setCategory] = useState(prompt?.category_id ?? "");
  const [color, setColor] = useState(
    prompt?.color ?? DEFAULT_FAVORITE_PROMPT_COLOR,
  );
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  useEffect(() => {
    onChildOpenChange(confirmDelete);
  }, [confirmDelete, onChildOpenChange]);

  const canSave = label.trim() !== "" && content.trim() !== "" && !busy;

  const handleSubmit = async () => {
    if (!canSave) return;
    setBusy(true);
    const input = {
      label: label.trim(),
      content,
      color,
      category_id: category || null,
    };
    const result = prompt
      ? await updatePrompt(prompt.id, input)
      : await createPrompt(input);
    setBusy(false);
    if (result) onDone();
  };

  const handleDelete = async () => {
    if (!prompt) return;
    setBusy(true);
    const deleted = await deletePrompt(prompt.id);
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
          {prompt
            ? t("favoritePrompts.editPrompt")
            : t("favoritePrompts.newPrompt")}
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
      <p className="favorite-prompts__note">
        {t("favoritePrompts.storageNote")}
      </p>

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
            placeholder={t("favoritePrompts.namePlaceholder")}
            onChange={(e) => setLabel(e.target.value)}
          />
        </div>
        <div className="favorite-prompts__field">
          <label className="favorite-prompts__field-label" htmlFor={contentId}>
            {t("favoritePrompts.content")}
          </label>
          <textarea
            id={contentId}
            className="favorite-prompts__input favorite-prompts__textarea"
            value={content}
            maxLength={4000}
            rows={4}
            placeholder={t("favoritePrompts.contentPlaceholder")}
            onChange={(e) => setContent(e.target.value)}
          />
        </div>
        <div className="favorite-prompts__field">
          <label className="favorite-prompts__field-label" htmlFor={categoryId}>
            {t("favoritePrompts.category")}
          </label>
          <select
            id={categoryId}
            className="favorite-prompts__input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">{t("favoritePrompts.uncategorized")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
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
        {prompt && (
          <button
            type="button"
            className="favorite-prompts__delete"
            onClick={() => setConfirmDelete(true)}
            aria-label={t("favoritePrompts.deletePrompt")}
            title={t("favoritePrompts.deletePrompt")}
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
        title={t("favoritePrompts.deletePrompt")}
        confirmLabel={t("common.delete")}
        cancelLabel={t("common.cancel")}
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDelete(false)}
        busy={busy}
      >
        {t("favoritePrompts.deletePromptConfirm", {
          name: prompt?.label ?? "",
        })}
      </ConfirmDialog>
    </form>
  );
}
