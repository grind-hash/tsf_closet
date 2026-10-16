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
