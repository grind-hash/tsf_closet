/**
 * PromptExpanderDropChooserModal - 画面へドロップした画像の使い道を選ぶダイアログ
 *
 * NovelAI の「この画像で何をしたいですか？」に倣い、プレビューと入れ先ボタン
 * （i2i 元 / インペイントの元 / 精密参照）を並べる。ボタン押下がそのまま確定。
 * 「履歴に残す」とメモは PromptExpanderUploadDialog と同じ意味。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PromptExpanderModal from "./PromptExpanderModal";
import PromptExpanderSwitch from "./PromptExpanderSwitch";
import "./PromptExpanderShared.css";
import "./PromptExpanderUploadDialog.css";
import "./PromptExpanderDropChooserModal.css";

/** 入れ先。コンポーザのセクション ID と一致させる */
export type PromptExpanderDropDestination = "i2i" | "inpaint" | "reference";

export interface PromptExpanderDropChooserOptions {
  keepAsEntry: boolean;
  note: string;
}

interface PromptExpanderDropChooserModalProps {
  /** ドロップされた画像。null なら閉じる */
  file: File | null;
  onClose: () => void;
  onChoose: (
    destination: PromptExpanderDropDestination,
    options: PromptExpanderDropChooserOptions,
  ) => void;
  /** アップロード中はボタンを止める */
  busy: boolean;
  /** 精密参照が使えるモデルか（V4.5 系のみ） */
  referenceSupported: boolean;
}

export default function PromptExpanderDropChooserModal({
  file,
  onClose,
  onChoose,
  busy,
  referenceSupported,
}: PromptExpanderDropChooserModalProps) {
  const { t } = useTranslation();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [keepAsEntry, setKeepAsEntry] = useState(true);
  const [note, setNote] = useState("");

  // 画像が変わるたびに初期化し、プレビュー URL のライフサイクルを管理する
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    setKeepAsEntry(true);
    setNote("");
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const choose = (destination: PromptExpanderDropDestination) => {
    if (busy) return;
    onChoose(destination, { keepAsEntry, note });
  };

  return (
    <PromptExpanderModal
      open={file !== null}
      title={t("promptExpander.drop.title")}
      onClose={onClose}
      closeLabel={t("promptExpander.upload.cancel")}
      size="sm"
      className="prompt-expander-drop-chooser"
    >
      {previewUrl && (
        <img
          className="prompt-expander__upload-preview"
          src={previewUrl}
          alt={t("promptExpander.upload.preview")}
        />
      )}
      <p className="prompt-expander__drop-file">{file?.name}</p>
      <div className="prompt-expander__drop-choices">
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__drop-choice"
          onClick={() => choose("i2i")}
          disabled={busy}
        >
          <span className="prompt-expander__drop-choice-title">
            {t("promptExpander.drop.useAsSource")}
          </span>
          <span className="prompt-expander__drop-choice-desc">
            {t("promptExpander.drop.useAsSourceDesc")}
          </span>
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__drop-choice"
          onClick={() => choose("inpaint")}
          disabled={busy}
        >
          <span className="prompt-expander__drop-choice-title">
            {t("promptExpander.drop.useAsInpaint")}
          </span>
          <span className="prompt-expander__drop-choice-desc">
            {t("promptExpander.drop.useAsInpaintDesc")}
          </span>
        </button>
        <button
          type="button"
          className="prompt-expander__btn prompt-expander__drop-choice"
          onClick={() => choose("reference")}
          disabled={busy || !referenceSupported}
          title={
            referenceSupported
              ? undefined
              : t("promptExpander.composer.referenceRequiresV45")
          }
        >
          <span className="prompt-expander__drop-choice-title">
            {t("promptExpander.drop.useAsReference")}
          </span>
          <span className="prompt-expander__drop-choice-desc">
            {referenceSupported
              ? t("promptExpander.drop.useAsReferenceDesc")
              : t("promptExpander.composer.referenceRequiresV45")}
          </span>
        </button>
      </div>
      <div className="prompt-expander__upload-options">
        <PromptExpanderSwitch
          checked={keepAsEntry}
          onChange={setKeepAsEntry}
          label={t("promptExpander.upload.keepAsEntry")}
          disabled={busy}
        />
      </div>
      <div className="prompt-expander__field">
        <label
          className="prompt-expander__label"
          htmlFor="prompt-expander-drop-note"
        >
          {t("promptExpander.upload.note")}
        </label>
        <input
          id="prompt-expander-drop-note"
          className="prompt-expander__input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={t("promptExpander.upload.notePlaceholder")}
          maxLength={500}
          disabled={busy}
        />
      </div>
      {busy && (
        <p className="prompt-expander__hint">
          {t("promptExpander.upload.uploading")}
        </p>
      )}
    </PromptExpanderModal>
  );
}
