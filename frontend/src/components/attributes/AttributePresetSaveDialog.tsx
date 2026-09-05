import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ConfirmDialog from "../ui/ConfirmDialog";

interface AttributePresetSaveDialogProps {
  open: boolean;
  title: string;
  placeholder: string;
  maxLength?: number;
  /** 保存。呼び出し側が保存に成功したら閉じる */
  onSave: (name: string) => void;
  onCancel: () => void;
}

/** 属性プリセットの名前を入力して保存するダイアログ（右パネル / 人物パネル共用） */
export default function AttributePresetSaveDialog({
  open,
  title,
  placeholder,
  maxLength,
  onSave,
  onCancel,
}: AttributePresetSaveDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) setName("");
  }, [open]);

  return (
    <ConfirmDialog
      open={open}
      title={title}
      confirmLabel={t("common.save")}
      cancelLabel={t("common.cancel")}
      confirmDisabled={!name.trim()}
      onConfirm={() => onSave(name.trim())}
      onCancel={onCancel}
    >
      <input
        type="text"
        className="confirm-dialog__input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        autoFocus
      />
    </ConfirmDialog>
  );
}
