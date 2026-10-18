/**
 * お気に入りプロンプト用のアイコン（インライン SVG）。
 *
 * NovelAI のプロンプトチャンクのアイコン（四隅の括弧）と見分けがつくよう、しおり型にする。
 */

import type { ReactNode } from "react";

interface IconProps {
  size?: number;
}

function Svg({ size = 14, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** 挿入: しおり＋行線 */
export function FavoritePromptInsertIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
    </Svg>
  );
}

/** 保存: しおり＋「＋」 */
export function FavoritePromptSaveIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" />
      <path d="M12 7v6" />
      <path d="M9 10h6" />
    </Svg>
  );
}

export function PencilIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </Svg>
  );
}

export function PlusIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </Svg>
  );
}

export function FolderPlusIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M12 10v6" />
      <path d="M9 13h6" />
    </Svg>
  );
}

export function CloseIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </Svg>
  );
}

export function TrashIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
    </Svg>
  );
}

/** すべて開く: 外向きの山形 */
export function ExpandAllIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="m7 15 5 5 5-5" />
      <path d="m7 9 5-5 5 5" />
    </Svg>
  );
}

/** すべて閉じる: 内向きの山形 */
export function CollapseAllIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="m7 20 5-5 5 5" />
      <path d="m7 4 5 5 5-5" />
    </Svg>
  );
}

/** 書き出し・読み込み: 上下の矢印 */
export function FileTransferIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M7 4v13" />
      <path d="m3 13 4 4 4-4" />
      <path d="M17 20V7" />
      <path d="m13 11 4-4 4 4" />
    </Svg>
  );
}

export function DownloadIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </Svg>
  );
}

export function UploadIcon({ size }: IconProps) {
  return (
    <Svg size={size}>
      <path d="M12 21V9" />
      <path d="m7 14 5-5 5 5" />
      <path d="M5 3h14" />
    </Svg>
  );
}
