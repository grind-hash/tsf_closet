/**
 * 秒数を m:ss 形式へ整形する。NaN や負値は 0:00 に倒す
 * （メタデータ未読込の HTMLAudioElement.duration は NaN になるため）。
 */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
