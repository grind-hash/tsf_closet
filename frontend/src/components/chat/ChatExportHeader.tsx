import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import type {
  ChatExportFormat,
  ChatExportProgress,
} from "../../hooks/useSessionExport";
import { formatBytes } from "../../utils/exportChat";

interface ChatExportHeaderProps {
  menuOpen: boolean;
  onToggleMenu: () => void;
  /** 外側クリック判定用。ヘッダ全体を囲む要素に付ける */
  menuRef: RefObject<HTMLDivElement | null>;
  progress: ChatExportProgress | null;
  onExport: (format: ChatExportFormat) => void;
}

/** チャット欄上部のエクスポートボタンとメニュー、画像同梱時の進捗表示 */
export default function ChatExportHeader({
  menuOpen,
  onToggleMenu,
  menuRef,
  progress,
  onExport,
}: ChatExportHeaderProps) {
  const { t } = useTranslation();
  return (
    <div className="chat-export-header" ref={menuRef}>
      {progress && (
        <div
          className="chat-export-header__progress"
          role="status"
          aria-live="polite"
        >
          <span className="chat-export-header__progress-label">
            {progress.format === "markdown_images"
              ? t("chat.export.markdownWithImages")
              : t("chat.export.novelHtmlZip")}{" "}
            {t("chat.export.exporting")}
          </span>
          <div className="chat-export-header__progress-bar">
            <div
              className="chat-export-header__progress-bar-fill"
              data-indeterminate={!progress.total}
              style={
                progress.total
                  ? {
                      width: `${Math.min(
                        100,
                        (progress.loaded / progress.total) * 100,
                      )}%`,
                    }
                  : undefined
              }
            />
          </div>
          <span className="chat-export-header__progress-text">
            {progress.total
              ? `${Math.round((progress.loaded / progress.total) * 100)}%`
              : formatBytes(progress.loaded)}
          </span>
        </div>
      )}
      <button
        className="chat-export-header__btn"
        onClick={onToggleMenu}
        title={t("chat.export.button")}
        data-open={menuOpen}
        disabled={!!progress}
      >
        ↗ {t("chat.export.button")}
      </button>
      {menuOpen && (
        <div className="chat-export-header__menu">
          <button onClick={() => onExport("clipboard")}>
            {t("chat.export.clipboard")}
          </button>
          <hr />
          <button onClick={() => onExport("markdown")}>
            {t("chat.export.markdown")}
          </button>
          <button onClick={() => onExport("csv")}>
            {t("chat.export.csv")}
          </button>
          <button onClick={() => onExport("json")}>
            {t("chat.export.json")}
          </button>
          <hr />
          <button onClick={() => onExport("novel")}>
            {t("chat.export.novel")}
          </button>
          <button onClick={() => onExport("markdown_images")}>
            {t("chat.export.markdownWithImages")}
          </button>
          <button onClick={() => onExport("novel_html_zip")}>
            {t("chat.export.novelHtmlZip")}
          </button>
        </div>
      )}
    </div>
  );
}
