/**
 * 遊び方ガイドの既読フラグ。サイドメニューの未読ドットの表示に使う。
 * ガイド画面を一度開いたら消し、以降は出さない。
 */

export const GUIDE_SEEN_STORAGE_KEY = "guide_seen";

export function readGuideSeen(): boolean {
  try {
    return localStorage.getItem(GUIDE_SEEN_STORAGE_KEY) === "1";
  } catch {
    return true; // 保存できない環境ではドットを出し続けない
  }
}

export function markGuideSeen(): void {
  try {
    localStorage.setItem(GUIDE_SEEN_STORAGE_KEY, "1");
  } catch {
    // 保存できなくてもガイド自体は使える
  }
}
