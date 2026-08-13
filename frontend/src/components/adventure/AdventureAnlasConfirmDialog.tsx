import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface AdventureAnlasConfirmDialogProps {
  open: boolean;
  /** ダイアログ本文(ターン送信用と開始用で文言を切り替える) */
  body: string;
  onConfirm: (suppressUntilBrowserClose: boolean) => void;
  onCancel: () => void;
}

/**
 * Anlas追加消費の確認ダイアログ。通常ゲーム(GamePlayScreen)の同名ダイアログと
 * 同じ体裁で、抑止チェックは呼び出し側がsessionStorageへ保存する。
 */
export default function AdventureAnlasConfirmDialog({
  open,
  body,
  onConfirm,
  onCancel,
}: AdventureAnlasConfirmDialogProps) {
  const { t } = useTranslation();
  const [doNotShowAgain, setDoNotShowAgain] = useState(false);

  useEffect(() => {
    if (open) setDoNotShowAgain(false);
  }, [open]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
    >
      <div
        style={{
          background: "var(--bg-secondary, #2a2a2a)",
          borderRadius: 8,
          padding: "1.5rem",
          maxWidth: 400,
          width: "90%",
          boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
        }}
      >
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>
          {t("gameplay.anlasTitle")}
        </h3>
        <p
          style={{
            margin: "0 0 1rem",
            fontSize: "0.9rem",
            lineHeight: 1.5,
          }}
        >
          {body}
        </p>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            margin: "0 0 1rem",
            fontSize: "0.85rem",
            color: "var(--text-secondary, #aaa)",
            cursor: "pointer",
          }}
          onClick={() => setDoNotShowAgain((v) => !v)}
        >
          <input
            type="checkbox"
            id="adventure-anlas-do-not-show-again"
            checked={doNotShowAgain}
            onChange={(e) => setDoNotShowAgain(e.target.checked)}
            style={{ cursor: "pointer" }}
          />
          <label
            htmlFor="adventure-anlas-do-not-show-again"
            style={{ cursor: "pointer", userSelect: "none" }}
          >
            {t("gameplay.anlasDoNotShowAgain")}
          </label>
        </div>
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 4,
              border: "1px solid var(--border-color, #555)",
              background: "transparent",
              color: "var(--text-primary, #eee)",
              cursor: "pointer",
            }}
          >
            {t("gameplay.anlasCancel")}
          </button>
          <button
            type="button"
            onClick={() => onConfirm(doNotShowAgain)}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 4,
              border: "none",
              background: "var(--accent-color, #6366f1)",
              color: "#fff",
              cursor: "pointer",
            }}
          >
            {t("gameplay.anlasProceed")}
          </button>
        </div>
      </div>
    </div>
  );
}
