import { useTranslation } from "react-i18next";
import type { UseMessageEditDeleteResult } from "../../hooks/useMessageEditDelete";
import ConfirmDialog from "../ui/ConfirmDialog";

/** メッセージ削除と「修正して再生成」の確認ダイアログ */
export default function MessageEditDeleteDialogs({
  controller,
}: {
  controller: UseMessageEditDeleteResult;
}) {
  const { t } = useTranslation();
  const {
    deleteConfirm,
    deleting,
    confirmDelete,
    cancelDelete,
    editConfirm,
    editing,
    confirmEdit,
    cancelEdit,
  } = controller;
  return (
    <>
      <ConfirmDialog
        open={deleteConfirm !== null}
        title={t("gameplay.deleteMessageTitle")}
        confirmLabel={t("gameplay.deleteMessageAction")}
        cancelLabel={t("gameplay.deleteMessageCancel")}
        busy={deleting}
        dismissible
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
      >
        <p>{t("gameplay.deleteMessageConfirm")}</p>
        {deleteConfirm?.responsePreview && (
          <p className="game-play-screen__delete-modal-preview">
            {t("gameplay.deleteMessageResponsePreview", {
              preview: deleteConfirm.responsePreview,
            })}
          </p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={editConfirm !== null}
        title={t("gameplay.editMessageTitle")}
        confirmLabel={t("gameplay.editMessageAction")}
        cancelLabel={t("gameplay.editMessageCancel")}
        busy={editing}
        dismissible
        onConfirm={confirmEdit}
        onCancel={cancelEdit}
      >
        <p>{t("gameplay.editMessageConfirm")}</p>
        {editConfirm && (
          <p className="game-play-screen__delete-modal-preview">
            {editConfirm.content.slice(0, 60)}
            {editConfirm.content.length > 60 ? "..." : ""}
          </p>
        )}
      </ConfirmDialog>
    </>
  );
}
