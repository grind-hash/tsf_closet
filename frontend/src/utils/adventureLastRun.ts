/**
 * 直前にプレイした Adventure run ID の永続化。
 *
 * 通常ゲームの current_session_id と同様に、最後に開いた/作成した run を
 * localStorage に覚えておき、Hub の「中断したシナリオを再開」バナーと
 * SideMenu の「直前のシナリオへ」から 1 クリックで戻れるようにする。
 * ID だけを保存し、タイトル・進捗・状態は常に最新の runs 一覧から引く。
 *
 * SideMenu は AdventureProvider の外側でも描画されるため、Context ではなく
 * このモジュールの購読 API (useSyncExternalStore 向け) で同期する。
 */

export const LAST_RUN_STORAGE_KEY = "adventure_last_run_id";
const LAST_RUN_CHANGE_EVENT = "adventure-last-run-change";

export function readLastAdventureRunId(): string | null {
  try {
    const value = localStorage.getItem(LAST_RUN_STORAGE_KEY);
    return value?.trim() ? value : null;
  } catch {
    return null;
  }
}

function notifyChange(): void {
  try {
    window.dispatchEvent(new Event(LAST_RUN_CHANGE_EVENT));
  } catch {
    // イベントを飛ばせない環境では購読側が次の描画で読み直す
  }
}

export function saveLastAdventureRunId(runId: string): void {
  try {
    localStorage.setItem(LAST_RUN_STORAGE_KEY, runId);
  } catch {
    // localStorage が利用できない環境では無視する
  }
  notifyChange();
}

/** 保存済み ID を消す。runId を渡したときは一致する場合だけ消す */
export function clearLastAdventureRunId(runId?: string): void {
  try {
    if (
      runId !== undefined &&
      localStorage.getItem(LAST_RUN_STORAGE_KEY) !== runId
    ) {
      return;
    }
    localStorage.removeItem(LAST_RUN_STORAGE_KEY);
  } catch {
    // localStorage が利用できない環境では無視する
  }
  notifyChange();
}

/** useSyncExternalStore 用の購読。別タブの storage イベントと同一タブの変更通知を拾う */
export function subscribeLastAdventureRunId(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === LAST_RUN_STORAGE_KEY) callback();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(LAST_RUN_CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(LAST_RUN_CHANGE_EVENT, callback);
  };
}
