import type { TFunction } from "i18next";
import type { AdventureSpeechStyle } from "../apis/adventure";
import type { AdventureAnlasEstimate } from "./adventureAnlasEstimate";
import { API_BASE } from "./api";

// Adventure 画面の表示用文字列を組み立てる小さなヘルパー。

// Anlas見積もりを表示用文字列にする。min=maxなら単一値、異なれば範囲表記
export function formatAnlasEstimate(
  t: TFunction,
  estimate: AdventureAnlasEstimate,
): string {
  return estimate.min === estimate.max
    ? t("adventure.anlasEstimateExact", { value: estimate.min })
    : t("adventure.anlasEstimateRange", {
        min: estimate.min,
        max: estimate.max,
      });
}

export function mediaUrl(url: string): string {
  if (url.startsWith(`${API_BASE}/`)) return url;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

/** 口調をUIへ1行で出す。custom は自由入力本文、空の攻略対象は「自動」表記 */
export function speechStyleLabel(
  style: AdventureSpeechStyle,
  custom: string,
  t: TFunction,
): string {
  if (style === "custom") {
    return custom.trim() || t("adventure.speechStyles.polite");
  }
  return t(`adventure.speechStyles.${style}`);
}
