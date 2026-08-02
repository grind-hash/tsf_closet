/**
 * 履歴画像から新規セッション分岐の確認ダイアログ
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import "./BranchSessionDialog.css";

export interface BranchSessionDialogProps {
  isOpen: boolean;
  isLoading: boolean;
  errorMessage?: string | null;
  /** 分岐元が自分自身モードかどうか。開いたときのチェック初期値に使う */
  defaultSelfMode?: boolean;
  onConfirm: (options: { inheritStats: boolean; selfMode: boolean }) => void;
  onCancel: () => void;
}

export default function BranchSessionDialog({
  isOpen,
  isLoading,
  errorMessage,
  defaultSelfMode = false,
  onConfirm,
  onCancel,
}: BranchSessionDialogProps) {
  const { t } = useTranslation();
  const [inheritStats, setInheritStats] = useState(true);
  const [selfMode, setSelfMode] = useState(defaultSelfMode);

  // ダイアログを開くたびに初期値へ戻す（特に自分自身モードは分岐元に合わせる）
  useEffect(() => {
    if (isOpen) {
      setInheritStats(true);
      setSelfMode(defaultSelfMode);
    }
  }, [isOpen, defaultSelfMode]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="branch-session-dialog__overlay"
      onClick={() => {
        if (!isLoading) onCancel();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && !isLoading) onCancel();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="branch-session-dialog-title"
    >
      <div
        className="branch-session-dialog"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={() => {}}
        role="document"
      >
        <h2 id="branch-session-dialog-title">
          {t("branchSession.dialogTitle")}
        </h2>
        <p className="branch-session-dialog__message">
          {t("branchSession.dialogMessage")}
        </p>
        <p className="branch-session-dialog__hint">
          {t("branchSession.dialogWaitHint")}
        </p>

        <label className="branch-session-dialog__checkbox-row">
          <input
            type="checkbox"
            checked={selfMode}
            disabled={isLoading}
            onChange={(e) => setSelfMode(e.target.checked)}
          />
          <span>
            <span className="branch-session-dialog__checkbox-label">
              {t("branchSession.selfModeLabel")}
            </span>
            <span className="branch-session-dialog__checkbox-desc">
              {t("branchSession.selfModeDesc")}
            </span>
          </span>
        </label>

        <label className="branch-session-dialog__checkbox-row">
          <input
            type="checkbox"
            checked={inheritStats}
            disabled={isLoading}
            onChange={(e) => setInheritStats(e.target.checked)}
          />
          <span>
            <span className="branch-session-dialog__checkbox-label">
              {t("branchSession.inheritStatsLabel")}
            </span>
            <span className="branch-session-dialog__checkbox-desc">
              {t("branchSession.inheritStatsDesc")}
            </span>
          </span>
        </label>

        {errorMessage && (
          <p className="branch-session-dialog__error" role="alert">
            {errorMessage}
          </p>
        )}

        {isLoading && (
          <div className="branch-session-dialog__loading" aria-live="polite">
            <span className="branch-session-dialog__spinner" />
            <span>{t("branchSession.loading")}</span>
          </div>
        )}

        <div className="branch-session-dialog__actions">
          <button
            type="button"
            className="branch-session-dialog__confirm"
            disabled={isLoading}
            onClick={() => onConfirm({ inheritStats, selfMode })}
          >
            {isLoading
              ? t("branchSession.loading")
              : t("branchSession.confirm")}
          </button>
          <button
            type="button"
            className="branch-session-dialog__cancel"
            disabled={isLoading}
            onClick={onCancel}
          >
            {t("branchSession.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}
