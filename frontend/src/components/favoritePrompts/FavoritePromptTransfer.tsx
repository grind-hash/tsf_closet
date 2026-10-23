/**
 * お気に入りプロンプトの書き出し・読み込みビュー（CSV / JSON）。
 *
 * 読み込みは先にプレビューを取り、上書きされるものがあれば件数・カテゴリー・名前を
 * 確認ダイアログで示してから取り込む。上書きが無ければそのまま取り込む。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  FavoritePromptFileFormat,
  FavoritePromptImportPreview,
} from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import { CloseIcon, DownloadIcon, UploadIcon } from "./FavoritePromptIcons";

interface FavoritePromptTransferProps {
  titleId: string;
  onClose: () => void;
  onBack: () => void;
  /** 上書き確認ダイアログの開閉（開いている間は Escape で親を閉じない） */
  onChildOpenChange: (open: boolean) => void;
}

interface PendingImport {
  file: File;
  preview: FavoritePromptImportPreview;
}

export default function FavoritePromptTransfer({
  titleId,
  onClose,
  onBack,
  onChildOpenChange,
}: FavoritePromptTransferProps) {
  const { t } = useTranslation();
  const {
    prompts,
    categories,
    loaded,
    exportPrompts,
    previewImport,
    importPrompts,
  } = useFavoritePrompts();
  const exportHeadingId = useId();
  const importHeadingId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"export" | "import" | null>(null);
  const [pending, setPending] = useState<PendingImport | null>(null);
  const isEmpty = loaded && prompts.length === 0 && categories.length === 0;

  useEffect(() => {
    onChildOpenChange(pending !== null);
  }, [pending, onChildOpenChange]);

  const handleExport = async (format: FavoritePromptFileFormat) => {
    setBusy("export");
    await exportPrompts(format);
    setBusy(null);
  };

  const runImport = async (file: File) => {
    setBusy("import");
    const result = await importPrompts(file);
    setBusy(null);
    setPending(null);
    if (result) onBack();
  };

  const handleFile = async (file: File) => {
    setBusy("import");
    const preview = await previewImport(file);
    if (!preview) {
      setBusy(null);
      return;
    }
    if (preview.overwrites.length > 0) {
      setBusy(null);
      setPending({ file, preview });
      return;
    }
    await runImport(file);
  };

  const renderStatus = (message: string) => (
    <div className="favorite-prompts__loading" role="status">
      <span className="favorite-prompts__spinner" aria-hidden="true" />
      {message}
    </div>
  );

  return (
    <>
      <header className="favorite-prompts__header">
        <h2 id={titleId} className="favorite-prompts__title">
          {t("favoritePrompts.transfer.title")}
        </h2>
        <div className="favorite-prompts__header-actions">
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

      <div className="favorite-prompts__body favorite-prompts__transfer">
        <section
          className="favorite-prompts__transfer-section"
          aria-labelledby={exportHeadingId}
        >
          <h3
            id={exportHeadingId}
            className="favorite-prompts__transfer-heading"
          >
            {t("favoritePrompts.transfer.exportHeading")}
          </h3>
          <p className="favorite-prompts__transfer-text">
            {t("favoritePrompts.transfer.exportDescription")}
          </p>
          <div className="favorite-prompts__transfer-actions">
            <button
              type="button"
              className="favorite-prompts__btn favorite-prompts__transfer-btn"
              onClick={() => void handleExport("csv")}
              disabled={busy !== null || isEmpty}
            >
              <DownloadIcon size={16} />
              {t("favoritePrompts.transfer.exportCsv")}
            </button>
            <button
              type="button"
              className="favorite-prompts__btn favorite-prompts__transfer-btn"
              onClick={() => void handleExport("json")}
              disabled={busy !== null || isEmpty}
            >
              <DownloadIcon size={16} />
              {t("favoritePrompts.transfer.exportJson")}
            </button>
          </div>
          <p className="favorite-prompts__transfer-hint">
            {isEmpty
              ? t("favoritePrompts.transfer.exportEmpty")
              : t("favoritePrompts.transfer.exportFormatHint")}
          </p>
          {busy === "export" &&
            renderStatus(t("favoritePrompts.transfer.exporting"))}
        </section>

        <section
          className="favorite-prompts__transfer-section"
          aria-labelledby={importHeadingId}
        >
          <h3
            id={importHeadingId}
            className="favorite-prompts__transfer-heading"
          >
            {t("favoritePrompts.transfer.importHeading")}
          </h3>
          <p className="favorite-prompts__transfer-text">
            {t("favoritePrompts.transfer.importDescription")}
          </p>
          <ul className="favorite-prompts__transfer-rules">
            <li>{t("favoritePrompts.transfer.importRuleOverwrite")}</li>
            <li>{t("favoritePrompts.transfer.importRuleCategory")}</li>
          </ul>
          <div className="favorite-prompts__transfer-columns">
            <span className="favorite-prompts__field-label">
              {t("favoritePrompts.transfer.csvColumnsTitle")}
            </span>
            <code className="favorite-prompts__transfer-code">
              {t("favoritePrompts.transfer.csvColumns")}
            </code>
            <p className="favorite-prompts__transfer-hint">
              {t("favoritePrompts.transfer.csvColumnsHint")}
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json,text/csv,application/json"
            className="favorite-prompts__file-input"
            data-testid="favorite-prompts-import-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              // 同じファイルを選び直しても change が届くよう値を戻す
              event.target.value = "";
              if (file) void handleFile(file);
            }}
          />
          <div className="favorite-prompts__transfer-actions">
            <button
              type="button"
              className="favorite-prompts__btn favorite-prompts__transfer-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy !== null}
            >
              <UploadIcon size={16} />
              {t("favoritePrompts.transfer.importButton")}
            </button>
          </div>
          {busy === "import" &&
            !pending &&
            renderStatus(t("favoritePrompts.transfer.importing"))}
        </section>
      </div>

      <footer className="favorite-prompts__footer">
        <div className="favorite-prompts__footer-actions">
          <button
            type="button"
            className="favorite-prompts__btn"
            onClick={onBack}
            disabled={busy !== null}
          >
            {t("favoritePrompts.transfer.back")}
          </button>
        </div>
      </footer>

      <ConfirmDialog
        open={pending !== null}
        title={t("favoritePrompts.transfer.overwriteTitle")}
        confirmLabel={t("favoritePrompts.transfer.overwriteConfirm")}
        cancelLabel={t("common.cancel")}
        onConfirm={() => {
          if (pending) void runImport(pending.file);
        }}
        onCancel={() => setPending(null)}
        busy={busy === "import"}
        className="favorite-prompts__overwrite-confirm"
      >
        {pending && (
          <>
            <p>
              {t("favoritePrompts.transfer.overwriteMessage", {
                count: pending.preview.overwrites.length,
              })}
            </p>
            <ul className="favorite-prompts__overwrite-list">
              {pending.preview.overwrites.map((target) => (
                <li
                  key={`${target.category ?? ""}\u0000${target.label}`}
                  className="favorite-prompts__overwrite-item"
                >
                  <span className="favorite-prompts__overwrite-label">
                    {target.label}
                  </span>
                  <span className="favorite-prompts__overwrite-category">
                    {target.category ?? t("favoritePrompts.uncategorized")}
                  </span>
                </li>
              ))}
            </ul>
            {pending.preview.create_count > 0 && (
              <p>
                {t("favoritePrompts.transfer.overwriteExtra", {
                  count: pending.preview.create_count,
                })}
              </p>
            )}
            {pending.preview.new_categories.length > 0 && (
              <p>
                {t("favoritePrompts.transfer.overwriteNewCategories", {
                  names: pending.preview.new_categories.join(
                    t("favoritePrompts.transfer.listSeparator"),
                  ),
                })}
              </p>
            )}
          </>
        )}
      </ConfirmDialog>
    </>
  );
}
