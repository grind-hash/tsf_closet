/**
 * Memory Generate Confirm Modal Component
 *
 * メモリ生成バッチを開始する前に、対象件数と推定所要時間、
 * 再生成オプションの状態を表示して確認を取るモーダル。
 */

import { useTranslation } from "react-i18next";
import "./MemoryGenerateConfirmModal.css";

interface MemoryGenerateConfirmModalProps {
  sessionCount: number;
  regenerateExisting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function MemoryGenerateConfirmModal({
  sessionCount,
  regenerateExisting,
  onConfirm,
  onCancel,
}: MemoryGenerateConfirmModalProps) {
  const { t } = useTranslation();
  const estimatedMinutes = Math.max(1, Math.ceil((sessionCount * 20) / 60));

  return (
    <div className="memory-confirm-overlay">
      <div className="memory-confirm-modal">
        <h2>{t("settings.memory.confirmTitle")}</h2>

        <div className="memory-confirm-content">
          <p>{t("settings.memory.confirmDescription")}</p>
          {regenerateExisting && (
            <p className="memory-confirm-note">
              {t("settings.memory.confirmRegenerateNote")}
            </p>
          )}
          <p className="memory-confirm-estimate">
            {t("settings.memory.confirmEstimate", {
              minutes: estimatedMinutes,
              count: sessionCount,
            })}
          </p>
        </div>

        <div className="memory-confirm-actions">
          <button
            type="button"
            className="memory-confirm-cancel"
            onClick={onCancel}
          >
            {t("settings.memory.confirmCancel")}
          </button>
          <button
            type="button"
            className="memory-confirm-start"
            onClick={onConfirm}
          >
            {t("settings.memory.confirmStart")}
          </button>
        </div>
      </div>
    </div>
  );
}
