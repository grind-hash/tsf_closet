import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ConfirmDialog from "./ConfirmDialog";

interface AnlasConfirmDialogProps {
  open: boolean;
  /** ダイアログ本文（消費量や状況に応じて呼び出し側が組み立てる） */
  body: ReactNode;
  /** 続行。引数は「ブラウザを閉じるまで表示しない」の値で、保存先は呼び出し側が決める */
  onConfirm: (suppressUntilBrowserClose: boolean) => void;
  onCancel: () => void;
  /** チェック欄の input id（同一画面に複数出すときの区別用） */
  checkboxId?: string;
}

/**
 * Anlas 追加消費の確認ダイアログ。通常ゲーム・Adventure・Prompt Expander で共用し、
 * 見出しとボタン文言は gameplay.anlas* に統一する。
 */
export default function AnlasConfirmDialog({
  open,
  body,
  onConfirm,
  onCancel,
  checkboxId,
}: AnlasConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <ConfirmDialog
      open={open}
      title={t("gameplay.anlasTitle")}
      confirmLabel={t("gameplay.anlasProceed")}
      cancelLabel={t("gameplay.anlasCancel")}
      doNotShowAgainLabel={t("gameplay.anlasDoNotShowAgain")}
      doNotShowAgainId={checkboxId}
      onConfirm={({ doNotShowAgain }) => onConfirm(doNotShowAgain)}
      onCancel={onCancel}
    >
      {body}
    </ConfirmDialog>
  );
}
