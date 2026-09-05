import { useCallback, useSyncExternalStore } from "react";
import type { AttributePreset } from "../types";

/** 属性プリセットの localStorage キー（RightPanel と CharacterStatePanel で共通） */
export const ATTRIBUTE_PRESET_STORAGE_KEY = "attribute_presets";

const listeners = new Set<() => void>();
let cache: AttributePreset[] | null = null;
const EMPTY: AttributePreset[] = [];

function readPresets(): AttributePreset[] {
  try {
    const saved = localStorage.getItem(ATTRIBUTE_PRESET_STORAGE_KEY);
    const parsed: unknown = saved ? JSON.parse(saved) : [];
    return Array.isArray(parsed) ? (parsed as AttributePreset[]) : EMPTY;
  } catch {
    return EMPTY;
  }
}

function getSnapshot(): AttributePreset[] {
  if (cache === null) cache = readPresets();
  return cache;
}

function emit(): void {
  for (const listener of listeners) listener();
}

function writePresets(next: AttributePreset[]): void {
  cache = next;
  try {
    localStorage.setItem(ATTRIBUTE_PRESET_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // 保存できなくても画面上の一覧は更新する
  }
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // 他タブでの変更も反映する（同一タブ内の変更は emit で伝える）
  const onStorage = (event: StorageEvent) => {
    if (event.key === ATTRIBUTE_PRESET_STORAGE_KEY) {
      cache = null;
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** テスト用: キャッシュを捨てて次回読み込み時に localStorage を読み直す */
export function resetAttributePresetCache(): void {
  cache = null;
}

/**
 * 属性プリセットの一覧と保存・削除。localStorage を唯一の保存先にし、
 * 同じキーを見ているパネル同士（右パネル / 人物パネル）の表示を即座に揃える。
 */
export function useAttributePresets(): {
  presets: AttributePreset[];
  /** 名前と属性の両方があれば保存して返す。どちらかが空なら null */
  savePreset: (name: string, attributes: string[]) => AttributePreset | null;
  deletePreset: (id: string) => void;
} {
  const presets = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const savePreset = useCallback(
    (name: string, attributes: string[]): AttributePreset | null => {
      const trimmed = name.trim();
      if (!trimmed || attributes.length === 0) return null;
      const preset: AttributePreset = {
        id: Date.now().toString(),
        name: trimmed,
        attributes,
        createdAt: new Date().toISOString(),
      };
      writePresets([...getSnapshot(), preset]);
      return preset;
    },
    [],
  );

  const deletePreset = useCallback((id: string) => {
    writePresets(getSnapshot().filter((preset) => preset.id !== id));
  }, []);

  return { presets, savePreset, deletePreset };
}

/** プリセットの属性を順に追加する。1 件の失敗は記録して続行する */
export async function loadPresetAttributes(
  preset: AttributePreset,
  addAttribute: (text: string) => Promise<void>,
): Promise<void> {
  for (const text of preset.attributes) {
    try {
      await addAttribute(text);
    } catch (error) {
      console.error("Failed to add preset attribute:", error);
    }
  }
}
