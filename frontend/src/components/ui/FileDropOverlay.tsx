/**
 * FileDropOverlay - 画面全体へのファイルドロップ中に出す案内オーバーレイ
 *
 * 表示専用（pointer-events: none）。drop 自体は useWindowFileDrop が window で受ける。
 * 画面を薄いグレーに落とし、中央にアップロードアイコンと「どこに入るか」の文言を出す。
 */

import "./FileDropOverlay.css";

interface FileDropOverlayProps {
  title: string;
  hint?: string;
  /** 受け付けられない状態（理由を title に入れて渡す） */
  unavailable?: boolean;
  testId?: string;
}

export default function FileDropOverlay({
  title,
  hint,
  unavailable = false,
  testId,
}: FileDropOverlayProps) {
  return (
    <div
      className={`file-drop-overlay${unavailable ? " is-unavailable" : ""}`}
      data-testid={testId}
    >
      <div className="file-drop-overlay__card">
        <svg
          className="file-drop-overlay__icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 16V4" />
          <path d="m7 9 5-5 5 5" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>
        <p className="file-drop-overlay__title">{title}</p>
        {hint && <p className="file-drop-overlay__hint">{hint}</p>}
      </div>
    </div>
  );
}
