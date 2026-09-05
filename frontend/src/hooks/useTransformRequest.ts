import { useCallback, useState } from "react";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "../constants/novelaiImageModels";
import { useChat } from "../contexts/ChatContext";
import { useSettings } from "../contexts/SettingsContext";
import { readStorageFlag, writeStorageFlag } from "../utils/storage";

const ANLAS_WARN_SUPPRESSED_KEY = "anlas_warn_suppressed";

/** play/stream へ送る画像生成オプション(App.handleTransform の options) */
export interface TransformOptions {
  maskImage?: string;
  maskId?: string;
  inpaintStrength?: number;
  inpaintNoise?: number;
  negativePrompt?: string;
  promptOverride?: string;
  imageOnlyTextToImage?: boolean;
  characterReferences?: Array<{
    imageData: string;
    type: string;
    strength: number;
    fidelity: number;
  }>;
}

export type TransformHandler = (
  instruction: string,
  costumeImage?: string,
  transformationType?: string,
  options?: TransformOptions,
  instructionType?: string,
  pendingToken?: string,
  useMemory?: boolean,
) => void;

interface PendingTransform {
  message: string;
  transformationType: string;
  transformOptions: TransformOptions | undefined;
  instructionType?: string;
  useMemory: boolean;
}

/** UI 上の指示種別からバックエンドの transformation_type / instruction_type を決める */
export function resolveTransformKinds(instructionType: string) {
  return {
    transformationType:
      instructionType === "reality_alter" ? "reality" : "costume",
    backendInstructionType:
      instructionType === "action" ? "action" : instructionType,
  };
}

/**
 * 変身(dress_up / reality_alter / action / image_only)の送信前処理。
 * NovelAI の画像オプション(マスク・i2i 強度・精密参照)を組み立て、
 * V5 利用上限の使い切りと精密参照の Anlas 追加消費は確認ダイアログを挟む。
 */
export function useTransformRequest(onTransform: TransformHandler) {
  const { state: settingsState, isNovelaiV5Active } = useSettings();
  const { state: chatState } = useChat();
  const imageProvider = settingsState.imageProvider;
  const inpaintSettings = settingsState.inpaintSettings;
  const { maskDataUrl, selectedMaskId } = settingsState.inpaintMask;
  const anlasBalance = settingsState.anlasBalance;

  // Anlas cost confirmation dialog for precise references
  const [anlasConfirmPending, setAnlasConfirmPending] = useState<
    (PendingTransform & { anlasCost: number }) | null
  >(null);
  // V5 利用上限の使い切り警告ダイアログ(Anlas 消費で生成が続く状態)
  const [usageWarnPending, setUsageWarnPending] =
    useState<PendingTransform | null>(null);

  /** NovelAI のインペイント・i2i・精密参照を含む送信オプション */
  const buildNovelaiOptions = useCallback((): TransformOptions => {
    // V5系モデルは精密参照非対応のため送らない
    const enabledRefs = isNovelaiV5Active
      ? []
      : settingsState.preciseReferences.filter((r) => r.enabled);
    return {
      // Mask only when inpaint is enabled
      ...(settingsState.inpaintEnabled &&
        maskDataUrl && {
          maskImage: maskDataUrl || undefined,
          maskId: selectedMaskId || undefined,
        }),
      // i2i strength and noise are always sent
      inpaintStrength: inpaintSettings.i2iStrength,
      inpaintNoise: inpaintSettings.inpaintNoise,
      negativePrompt: inpaintSettings.negativePrompt || undefined,
      promptOverride: inpaintSettings.promptOverride || undefined,
      // Precise reference images (enabled only)
      ...(enabledRefs.length > 0 && {
        characterReferences: enabledRefs.map((r) => ({
          imageData: r.imageData,
          type: r.type,
          strength: r.strength,
          fidelity: r.fidelity,
        })),
      }),
    };
  }, [
    isNovelaiV5Active,
    settingsState.preciseReferences,
    settingsState.inpaintEnabled,
    maskDataUrl,
    selectedMaskId,
    inpaintSettings,
  ]);

  /**
   * 変身を送信する。確認が要る場合は保留して false を返す(ダイアログの
   * 確定で改めて onTransform する)。
   */
  const submitTransform = useCallback(
    (
      message: string,
      instructionType: string,
      useMemory: boolean,
      tempToken: string,
    ) => {
      const { transformationType, backendInstructionType } =
        resolveTransformKinds(instructionType);

      // NovelAI mode: always send i2i strength and optionally character references
      let transformOptions: TransformOptions | undefined;
      if (imageProvider === "novelai") {
        transformOptions = buildNovelaiOptions();
      }

      // 画像のみモードで「前画像を使わない」が ON なら text-to-image フラグを載せる
      // (確認ダイアログ経由の再送にも transformOptions ごと引き継がれる)
      if (
        backendInstructionType === "image_only" &&
        chatState.imageOnlyTextToImage
      ) {
        transformOptions = {
          ...(transformOptions ?? {}),
          imageOnlyTextToImage: true,
        };
      }

      // V5 利用上限を使い切った状態での生成は Anlas を消費するため警告する
      const usageExhausted =
        anlasBalance?.usage != null &&
        (anlasBalance.usage.percent <= 0 || anlasBalance.usage.isNegative);
      if (
        isNovelaiV5Active &&
        usageExhausted &&
        !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
      ) {
        setUsageWarnPending({
          message,
          transformationType,
          transformOptions,
          instructionType: backendInstructionType,
          useMemory,
        });
        return false; // Wait for user confirmation
      }

      // Anlas warning: if precise references are enabled, show confirmation
      const enabledRefCount = transformOptions?.characterReferences
        ? transformOptions.characterReferences.length
        : 0;
      if (enabledRefCount > 0) {
        if (readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)) {
          onTransform(
            message,
            undefined,
            transformationType,
            transformOptions,
            backendInstructionType,
            undefined,
            useMemory,
          );
          return true;
        }
        setAnlasConfirmPending({
          message,
          transformationType,
          transformOptions,
          anlasCost: enabledRefCount * 5,
          instructionType: backendInstructionType,
          useMemory,
        });
        return false; // Wait for user confirmation
      }

      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        backendInstructionType,
        tempToken,
        useMemory,
      );
      return true;
    },
    [
      imageProvider,
      buildNovelaiOptions,
      chatState.imageOnlyTextToImage,
      anlasBalance,
      isNovelaiV5Active,
      onTransform,
    ],
  );

  // Anlas confirmation dialog handlers
  const handleAnlasConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!anlasConfirmPending) return;
      const {
        message,
        transformationType,
        transformOptions,
        instructionType: pendingInstructionType,
        useMemory,
      } = anlasConfirmPending;
      if (doNotShowAgain) {
        writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
      }
      setAnlasConfirmPending(null);
      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        pendingInstructionType,
        undefined,
        useMemory,
      );
    },
    [anlasConfirmPending, onTransform],
  );

  const handleAnlasCancel = useCallback(() => {
    setAnlasConfirmPending(null);
  }, []);

  // V5 利用上限使い切り警告ダイアログのハンドラー
  const handleUsageWarnConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!usageWarnPending) return;
      const {
        message,
        transformationType,
        transformOptions,
        instructionType: pendingInstructionType,
        useMemory,
      } = usageWarnPending;
      if (doNotShowAgain) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      setUsageWarnPending(null);
      onTransform(
        message,
        undefined,
        transformationType,
        transformOptions,
        pendingInstructionType,
        undefined,
        useMemory,
      );
    },
    [usageWarnPending, onTransform],
  );

  const handleUsageWarnCancel = useCallback(() => {
    setUsageWarnPending(null);
  }, []);

  return {
    submitTransform,
    anlasConfirmPending,
    handleAnlasConfirm,
    handleAnlasCancel,
    usageWarnPending,
    handleUsageWarnConfirm,
    handleUsageWarnCancel,
  };
}
