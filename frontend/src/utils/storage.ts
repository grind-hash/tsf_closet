/**
 * localStorage / sessionStorage への安全なアクセス。
 *
 * プライベートモードや SSR など Storage が使えない環境でも例外を外へ出さず、
 * 読み取りは null、書き込みは false を返す。各モジュールで try/catch を書かず、
 * ここを経由する（React の状態と同期させたい値は hooks/usePersistedState を使う）。
 */

export type StorageKind = "local" | "session";

function resolve(kind: StorageKind): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return kind === "session" ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function readStorage(kind: StorageKind, key: string): string | null {
  try {
    return resolve(kind)?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** 保存できたら true。容量超過や無効化時は false */
export function writeStorage(
  kind: StorageKind,
  key: string,
  value: string,
): boolean {
  try {
    const storage = resolve(kind);
    if (!storage) return false;
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function removeStorage(kind: StorageKind, key: string): void {
  try {
    resolve(kind)?.removeItem(key);
  } catch {
    // 削除できなくても呼び出し側の処理は続ける
  }
}

/** "true" が保存されているときだけ true（未保存・不正値は false） */
export function readStorageFlag(kind: StorageKind, key: string): boolean {
  return readStorage(kind, key) === "true";
}

export function writeStorageFlag(
  kind: StorageKind,
  key: string,
  value: boolean,
): boolean {
  return writeStorage(kind, key, String(value));
}
