/**
 * usePreciseReferenceFiles - 精密参照画像ファイルの検証と追加
 *
 * RightPanel のドロップゾーン/ファイル選択と、プレイ画面全体へのドロップの両方から
 * 同じ検証（形式・容量・上限枚数）と DataURL 変換を使うために切り出している。
 * 追加先は SettingsContext.preciseReferences。
 */

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../contexts/SettingsContext";
import { generateUUID } from "../utils/generateUUID";

export const PRECISE_REFERENCE_ALLOWED_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
];
export const PRECISE_REFERENCE_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
export const PRECISE_REFERENCE_MAX_COUNT = 6;

/** RightPanel 内の精密参照セクションの DOM id（画面ドロップ後のスクロール先） */
export const PRECISE_REFERENCE_SECTION_ID = "precise-reference-section";

export interface PreciseReferenceAddResult {
  /** 実際に追加できた枚数 */
  addedCount: number;
  /** 表示すべき検証エラー文言（上限超過を優先、無ければ null） */
  error: string | null;
}

function readFileAsDataUrl(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve(typeof reader.result === "string" ? reader.result : null);
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(file);
  });
}

export function usePreciseReferenceFiles() {
  const { t } = useTranslation();
  const { state, addPreciseReference } = useSettings();
  const currentCount = state.preciseReferences.length;

  // ファイルを検証し、元の順序を保って追加する
  const addFiles = useCallback(
    async (files: File[]): Promise<PreciseReferenceAddResult> => {
      const validFiles: File[] = [];
      let firstValidationError: string | null = null;
      let hasMaxCountError = false;
      let remainingSlots = Math.max(
        0,
        PRECISE_REFERENCE_MAX_COUNT - currentCount,
      );

      for (const file of files) {
        if (!PRECISE_REFERENCE_ALLOWED_MIME_TYPES.includes(file.type)) {
          firstValidationError ??= t("rightPanel.preciseRefTypeError", {
            name: file.name,
          });
          continue;
        }

        if (file.size > PRECISE_REFERENCE_MAX_FILE_SIZE_BYTES) {
          firstValidationError ??= t("rightPanel.preciseRefSizeError", {
            name: file.name,
          });
          continue;
        }

        if (remainingSlots === 0) {
          hasMaxCountError = true;
          continue;
        }

        validFiles.push(file);
        remainingSlots -= 1;
      }

      const imageDataList = await Promise.all(
        validFiles.map(readFileAsDataUrl),
      );

      let addedCount = 0;
      validFiles.forEach((file, index) => {
        const imageData = imageDataList[index];
        if (!imageData) return;
        addPreciseReference({
          id: generateUUID(),
          imageData,
          fileName: file.name,
          type: "character&style",
          strength: 0.6,
          fidelity: 1.0,
          enabled: true,
        });
        addedCount += 1;
      });

      let error: string | null = null;
      if (hasMaxCountError) {
        error = t("rightPanel.preciseRefMaxError");
      } else if (firstValidationError) {
        error = firstValidationError;
      }

      return { addedCount, error };
    },
    [addPreciseReference, currentCount, t],
  );

  return { addFiles };
}
