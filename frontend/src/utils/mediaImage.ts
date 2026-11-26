/**
 * API が配信する画像(履歴・Prompt Expander・キャラクターの立ち絵など)を
 * Blob / File / data URL として取り込むヘルパー。
 *
 * 選択モーダルで選んだ画像を、アップロードと同じ経路(精密参照の追加、
 * Prompt Expander の upload)へ渡すために使う。
 */

import { mediaUrl } from "./adventureFormat";

/** 配信 URL(API 相対パス可)から画像を取得する。HTTP エラーは例外にする */
export async function fetchMediaBlob(path: string): Promise<Blob> {
  if (!path) throw new Error("image url is empty");
  const res = await fetch(mediaUrl(path));
  if (!res.ok) {
    throw new Error(`image fetch failed: ${res.status}`);
  }
  return res.blob();
}

/** 画像を取得して File にする。Content-Type が無いときは PNG とみなす */
export async function fetchMediaAsFile(
  path: string,
  fileName: string,
): Promise<File> {
  const blob = await fetchMediaBlob(path);
  return new File([blob], fileName, { type: blob.type || "image/png" });
}

/** Blob を data URL に変換する */
export function readBlobAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("read failed"));
      }
    };
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}
