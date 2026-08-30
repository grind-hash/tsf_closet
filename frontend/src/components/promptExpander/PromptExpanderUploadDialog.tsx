/**
 * PromptExpanderUploadDialog - 画像アップロードダイアログ
 *
 * ファイル選択 + プレビュー、「履歴に残す」「i2i元として使う」（少なくとも一方必須）、
 * 任意のメモ欄。確定で Context の uploadImage を呼ぶ。
 * target="reference" のときは「i2i元として使う」が「精密参照に使う」になり、参照画像の選択状態へ入れる。
 */

import { type ChangeEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type PromptExpanderPickerTarget,
  usePromptExpander,
} from "../../contexts/PromptExpanderContext";
import PromptExpanderModal from "./PromptExpanderModal";
import PromptExpanderSwitch from "./PromptExpanderSwitch";
import "./PromptExpanderShared.css";
import "./PromptExpanderUploadDialog.css";

interface PromptExpanderUploadDialogProps {
  open: boolean;
  onClose: () => void;
  /** 画像の入れ先（既定は i2i 元） */
  target?: PromptExpanderPickerTarget;
}

export default function PromptExpanderUploadDialog({
  open,
  onClose,
  target = "source",
}: PromptExpanderUploadDialogProps) {
  const { t } = useTranslation();
  const { uploadImage, uploading, activeSession } = usePromptExpander();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [keepAsEntry, setKeepAsEntry] = useState(true);
  const [useAsSource, setUseAsSource] = useState(true);
  const [note, setNote] = useState("");

  // 開くたびに初期化
  useEffect(() => {
    if (open) {
      setFile(null);
      setKeepAsEntry(true);
      setUseAsSource(true);
      setNote("");
    }
  }, [open]);

  // プレビュー URL のライフサイクル
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] ?? null;
    setFile(next?.type.startsWith("image/") ? next : null);
  };

  const canConfirm =
    Boolean(file) &&
    (keepAsEntry || useAsSource) &&
    !uploading &&
    (!keepAsEntry || Boolean(activeSession));

  const handleConfirm = async () => {
    if (!file || !canConfirm) return;
    await uploadImage(file, { keepAsEntry, useAsSource, target, note });
    onClose();
  };

  return (
    <PromptExpanderModal
      open={open}
      title={t("promptExpander.upload.title")}
      onClose={onClose}
      closeLabel={t("promptExpander.upload.cancel")}
      size="sm"
      footer={
        <>
          <button
            type="button"
            className="prompt-expander__btn"
            onClick={onClose}
            disabled={uploading}
          >
            {t("promptExpander.upload.cancel")}
          </button>
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--primary"
            onClick={() => void handleConfirm()}
            disabled={!canConfirm}
          >
            {uploading
              ? t("promptExpander.upload.uploading")
              : t("promptExpander.upload.confirm")}
          </button>
        </>
      }
    >
      <div className="prompt-expander__field">
        <label
          className="prompt-expander__label"
          htmlFor="prompt-expander-upload-file"
        >
          {t("promptExpander.upload.choose")}
        </label>
        <input
          id="prompt-expander-upload-file"
          type="file"
          accept="image/*"
          className="prompt-expander__input"
          onChange={handleFileChange}
          disabled={uploading}
        />
      </div>
      {previewUrl && (
        <img
          className="prompt-expander__upload-preview"
          src={previewUrl}
          alt={t("promptExpander.upload.preview")}
        />
      )}
      <div className="prompt-expander__upload-options">
        <PromptExpanderSwitch
          checked={keepAsEntry}
          onChange={setKeepAsEntry}
          label={t("promptExpander.upload.keepAsEntry")}
          disabled={uploading}
        />
        <PromptExpanderSwitch
          checked={useAsSource}
          onChange={setUseAsSource}
          label={
            target === "reference"
              ? t("promptExpander.upload.useAsReference")
              : t("promptExpander.upload.useAsSource")
          }
          disabled={uploading}
        />
      </div>
      {!keepAsEntry && !useAsSource && (
        <p className="prompt-expander__hint prompt-expander__hint--warning">
          {target === "reference"
            ? t("promptExpander.upload.atLeastOneReference")
            : t("promptExpander.upload.atLeastOne")}
        </p>
      )}
      <div className="prompt-expander__field">
        <label
          className="prompt-expander__label"
          htmlFor="prompt-expander-upload-note"
        >
          {t("promptExpander.upload.note")}
        </label>
        <input
          id="prompt-expander-upload-note"
          className="prompt-expander__input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={t("promptExpander.upload.notePlaceholder")}
          maxLength={500}
          disabled={uploading}
        />
      </div>
    </PromptExpanderModal>
  );
}
