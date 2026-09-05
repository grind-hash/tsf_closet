import { type ReactNode, useEffect, useId, useState } from "react";
import "./ConfirmDialog.css";

export interface ConfirmDialogResult {
  /** 「次回から表示しない」チェックの値（チェック欄を出していないときは false） */
  doNotShowAgain: boolean;
}

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  /** 本文。文字列でも要素（入力欄など）でもよい */
  children?: ReactNode;
  confirmLabel: ReactNode;
  cancelLabel: ReactNode;
  onConfirm: (result: ConfirmDialogResult) => void;
  onCancel: () => void;
  /** 指定するとチェック欄を表示する（Anlas 確認の抑止など） */
  doNotShowAgainLabel?: ReactNode;
  /** チェック欄の input id（未指定なら自動生成） */
  doNotShowAgainId?: string;
  /** 確定ボタンだけを無効化する（入力が空のときなど） */
  confirmDisabled?: boolean;
  /** 処理中。両ボタンを無効化し、オーバーレイ / Escape でも閉じない */
  busy?: boolean;
  /** オーバーレイクリックと Escape をキャンセル扱いにする（既定は明示操作のみ） */
  dismissible?: boolean;
  className?: string;
  testId?: string;
}

/**
 * 共通の確認ダイアログ。開いている間だけ描画し、開くたびにチェック欄をリセットする。
 * ボタンは左がキャンセル、右が確定。
 */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  doNotShowAgainLabel,
  doNotShowAgainId,
  confirmDisabled = false,
  busy = false,
  dismissible = false,
  className,
  testId,
}: ConfirmDialogProps) {
  const titleId = useId();
  const generatedCheckId = useId();
  const checkId = doNotShowAgainId ?? generatedCheckId;
  const [doNotShowAgain, setDoNotShowAgain] = useState(false);

  useEffect(() => {
    if (open) setDoNotShowAgain(false);
  }, [open]);

  if (!open) return null;

  const canDismiss = dismissible && !busy;

  return (
    <div
      className="confirm-dialog-overlay"
      onClick={() => {
        if (canDismiss) onCancel();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && canDismiss) onCancel();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-testid={testId}
    >
      <div
        className={className ? `confirm-dialog ${className}` : "confirm-dialog"}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={() => {}}
        role="document"
      >
        <h3 id={titleId} className="confirm-dialog__title">
          {title}
        </h3>
        {children !== undefined && children !== null && (
          <div className="confirm-dialog__body">{children}</div>
        )}
        {doNotShowAgainLabel !== undefined && (
          <label className="confirm-dialog__check" htmlFor={checkId}>
            <input
              type="checkbox"
              id={checkId}
              checked={doNotShowAgain}
              onChange={(e) => setDoNotShowAgain(e.target.checked)}
            />
            <span>{doNotShowAgainLabel}</span>
          </label>
        )}
        <div className="confirm-dialog__actions">
          <button
            type="button"
            className="confirm-dialog__cancel"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="confirm-dialog__confirm"
            onClick={() => onConfirm({ doNotShowAgain })}
            disabled={busy || confirmDisabled}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
