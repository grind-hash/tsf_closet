/**
 * usePersistedSectionState - 折りたたみセクションの開閉状態を localStorage に保持する
 *
 * 保存形式は { [sectionId]: boolean } の JSON マップ（キー: prompt_expander_sections_open）。
 * localStorage が使えない環境（SSR / プライベートモード等）ではメモリ上の状態のみで動く。
 */

import { useCallback, useState } from "react";

export const PROMPT_EXPANDER_SECTIONS_OPEN_KEY =
  "prompt_expander_sections_open";

type SectionOpenMap = Record<string, boolean>;

function readMap(): SectionOpenMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(PROMPT_EXPANDER_SECTIONS_OPEN_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return parsed as SectionOpenMap;
  } catch {
    return {};
  }
}

function writeEntry(id: string, open: boolean) {
  if (typeof window === "undefined") return;
  try {
    const next = { ...readMap(), [id]: open };
    window.localStorage.setItem(
      PROMPT_EXPANDER_SECTIONS_OPEN_KEY,
      JSON.stringify(next),
    );
  } catch {
    // 保存できなくても UI の開閉は続行する
  }
}

export function usePersistedSectionState(id: string, defaultOpen = true) {
  const [open, setOpenState] = useState<boolean>(() => {
    const saved = readMap()[id];
    return typeof saved === "boolean" ? saved : defaultOpen;
  });

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next);
      writeEntry(id, next);
    },
    [id],
  );

  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);

  return { open, setOpen, toggle };
}
