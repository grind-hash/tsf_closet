import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useRef,
  useState,
} from "react";
import { readStorage, type StorageKind, writeStorage } from "../utils/storage";

export interface PersistedStateOptions<T> {
  /** 既定は localStorage */
  storage?: StorageKind;
  /** 既定は JSON.stringify（boolean は "true" / "false" になる） */
  serialize?: (value: T) => string;
  /** 既定は JSON.parse。例外を投げると初期値に戻す。形式の検証もここで行う */
  deserialize?: (raw: string) => T;
}

/**
 * useState と同じ形で、値を Storage に保持する。
 *
 * 初期化時に一度だけ読み、更新のたびに書く（初期値は書き戻さない）。
 * Storage が使えない環境ではメモリ上の状態だけで動く。
 */
export function usePersistedState<T>(
  key: string,
  initial: T | (() => T),
  options: PersistedStateOptions<T> = {},
): [T, Dispatch<SetStateAction<T>>] {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [value, setValue] = useState<T>(() => {
    const fallback = () =>
      typeof initial === "function" ? (initial as () => T)() : initial;
    const raw = readStorage(options.storage ?? "local", key);
    if (raw === null) return fallback();
    try {
      const deserialize =
        options.deserialize ?? (JSON.parse as (raw: string) => T);
      return deserialize(raw);
    } catch {
      return fallback();
    }
  });

  const set = useCallback<Dispatch<SetStateAction<T>>>(
    (action) => {
      setValue((prev) => {
        const next =
          typeof action === "function"
            ? (action as (prev: T) => T)(prev)
            : action;
        const { storage = "local", serialize = JSON.stringify } =
          optionsRef.current;
        writeStorage(storage, key, serialize(next));
        return next;
      });
    },
    [key],
  );

  return [value, set];
}
