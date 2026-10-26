/**
 * 3D アバター(VRM)の見せ方の好み(ライティング・カメラの構図)。
 *
 * 閲覧者ごとの見た目の好みなので localStorage に置く。キャラチャット・
 * Adventure・設定のプレビューで同時に表示していても同じ値になるよう、
 * モジュール単位のストアから購読者へ通知する。
 */

import { useCallback, useSyncExternalStore } from "react";
import {
  AVATAR_FRAMING_DEFAULT,
  AVATAR_LIGHTING_DEFAULT,
  type AvatarFraming,
  type AvatarLightingPreset,
  normalizeAvatarFraming,
  normalizeAvatarLighting,
} from "../constants/companionAvatar";
import { readStorage, writeStorage } from "../utils/storage";

export const AVATAR_LIGHTING_KEY = "avatar_lighting_preset";
export const AVATAR_FRAMING_KEY = "avatar_camera_framing";

interface PreferenceStore<T> {
  get: () => T;
  set: (value: T) => void;
  subscribe: (listener: () => void) => () => void;
}

function createPreferenceStore<T extends string>(
  key: string,
  fallback: T,
  normalize: (value: unknown) => T | null,
): PreferenceStore<T> {
  const listeners = new Set<() => void>();
  // 保存できなかったとき(Storage が使えない環境)だけメモリ上の値で動く
  let unsaved: T | null = null;
  return {
    get: () => unsaved ?? normalize(readStorage("local", key)) ?? fallback,
    set: (value) => {
      unsaved = writeStorage("local", key, value) ? null : value;
      for (const listener of listeners) listener();
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const lightingStore = createPreferenceStore<AvatarLightingPreset>(
  AVATAR_LIGHTING_KEY,
  AVATAR_LIGHTING_DEFAULT,
  normalizeAvatarLighting,
);

const framingStore = createPreferenceStore<AvatarFraming>(
  AVATAR_FRAMING_KEY,
  AVATAR_FRAMING_DEFAULT,
  normalizeAvatarFraming,
);

function usePreference<T>(
  store: PreferenceStore<T>,
  fallback: T,
): [T, (value: T) => void] {
  const value = useSyncExternalStore(
    store.subscribe,
    store.get,
    () => fallback,
  );
  const set = useCallback((next: T) => store.set(next), [store]);
  return [value, set];
}

export function useAvatarLighting() {
  return usePreference(lightingStore, AVATAR_LIGHTING_DEFAULT);
}

export function useAvatarFraming() {
  return usePreference(framingStore, AVATAR_FRAMING_DEFAULT);
}
