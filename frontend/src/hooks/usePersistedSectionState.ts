/**
 * usePersistedSectionState - 折りたたみセクションの開閉状態を localStorage に保持する
 *
 * 保存形式は { [sectionId]: boolean } の JSON マップ（キー: prompt_expander_sections_open）。
 * localStorage が使えない環境（SSR / プライベートモード等）ではメモリ上の状態のみで動く。
 *
 * 「すべて開く / すべて閉じる」を画面下部のコントロールエリアから操作できるよう、
 * 状態はモジュールレベルのストアに置いて購読者へ通知する。対象 ID はマウント中の
 * フックが自分で登録するので、セクションが増えても固定リストを直す必要はない。
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";

export const PROMPT_EXPANDER_SECTIONS_OPEN_KEY =
  "prompt_expander_sections_open";

type SectionOpenMap = Record<string, boolean>;

const listeners = new Set<() => void>();
/** マウント中のセクション ID -> 既定の開閉（「すべて開く / 閉じる」の対象） */
const registered = new Map<string, boolean>();
/** localStorage が使えないときの退避先 */
let memoryMap: SectionOpenMap = {};

function readMap(): SectionOpenMap {
  if (typeof window === "undefined") return memoryMap;
  try {
    const raw = window.localStorage.getItem(PROMPT_EXPANDER_SECTIONS_OPEN_KEY);
    if (!raw) return memoryMap;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return memoryMap;
    }
    return parsed as SectionOpenMap;
  } catch {
    return memoryMap;
  }
}

function writeMap(next: SectionOpenMap) {
  memoryMap = next;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      PROMPT_EXPANDER_SECTIONS_OPEN_KEY,
      JSON.stringify(next),
    );
  } catch {
    // 保存できなくても UI の開閉は続行する
  }
}

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function setSectionOpen(id: string, open: boolean) {
  writeMap({ ...readMap(), [id]: open });
  emit();
}

/** 表示中のセクションをまとめて開閉する（画面下部のコントロールエリアから呼ぶ） */
export function setAllPromptExpanderSections(open: boolean) {
  const next = { ...readMap() };
  for (const id of registered.keys()) next[id] = open;
  writeMap(next);
  emit();
}

/**
 * 表示中のセクションがすべて開いているか（コントロールエリアのトグル文言に使う）。
 * 1 つでも閉じていれば false = 次の操作は「すべて開く」になる。
 */
export function usePromptExpanderSectionsAllOpen(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => {
      const map = readMap();
      for (const [id, defaultOpen] of registered) {
        // 未記録のセクションは、そのセクション自身の既定値で判定する
        if ((map[id] ?? defaultOpen) === false) return false;
      }
      return true;
    },
    () => true,
  );
}

export function usePersistedSectionState(id: string, defaultOpen = true) {
  const open = useSyncExternalStore(
    subscribe,
    () => {
      const saved = readMap()[id];
      return typeof saved === "boolean" ? saved : defaultOpen;
    },
    () => defaultOpen,
  );

  // 「すべて開く / 閉じる」の対象は、いま画面に出ているセクションだけにする
  useEffect(() => {
    registered.set(id, defaultOpen);
    emit();
    return () => {
      registered.delete(id);
      emit();
    };
  }, [id, defaultOpen]);

  const setOpen = useCallback(
    (next: boolean) => {
      setSectionOpen(id, next);
    },
    [id],
  );

  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);

  return { open, setOpen, toggle };
}
