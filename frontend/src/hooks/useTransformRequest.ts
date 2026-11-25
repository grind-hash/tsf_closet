import { useCallback, useState } from "react";
import {
  isV5ImageModel,
  preciseReferenceFormat,
  resolveEffectiveNovelaiImageModel,
  V5_USAGE_WARN_SUPPRESSED_KEY,
} from "../constants/novelaiImageModels";
import { useChat } from "../contexts/ChatContext";
import { useSettings } from "../contexts/SettingsContext";
import type { PreciseReferenceType } from "../types";
import {
  ANLAS_PER_PRECISE_REFERENCE,
  resolveSendablePreciseReferences,
} from "../utils/preciseReferences";
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
  /** NSFW モードをこの手番だけ上書きする(サロンは run の過激施術に合わせる) */
  nsfwMode?: boolean;
  /**
   * 複数人表示をこの手番だけ上書きする。サロンの体験の場面は相手役と主人公の
   * タグを書き分けるため、設定によらず ON にする
   */
  enableMultiplePeople?: boolean;
  characterReferences?: Array<{
    imageData: string;
    type: PreciseReferenceType;
    /** キャラ系の参照で衣装も参照するか（V5 のみ有効） */
    includeOutfit?: boolean;
    strength: number;
    fidelity: number;
  }>;
}

export interface TransformRequestConfig {
  /**
   * 手番ごとの送信オプションの上書き（サロンの過激施術に合わせた NSFW・接客範囲のマスク等）。
   * 精密参照の送信可否と Anlas の枚数は、上書きを合成した後のモデルとマスクで決める
   */
  resolveTurnOverrides?: (instructionType: string) => TransformOptions;
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
  /** 送信済みのユーザーメッセージに紐づく pending identity のトークン */
  tempToken: string;
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
 * V5 利用上限の使い切りと精密参照の Anlas 追加消費は確認ダイアログを挟む
 * (両方に当たる手番は上限警告 → Anlas 確認の順に出す)。
 * ダイアログをキャンセルした場合は、積んだユーザーメッセージを取り下げて文面を入力欄へ戻す。
 */
export function useTransformRequest(
  onTransform: TransformHandler,
  config: TransformRequestConfig = {},
) {
  const { resolveTurnOverrides } = config;
  const { state: settingsState } = useSettings();
  const { state: chatState, discardPendingIdentity, setInputText } = useChat();
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

  /** NovelAI のインペイント・i2i を含む送信オプション（精密参照は後で決める） */
  const buildNovelaiOptions = useCallback(
    (): TransformOptions => ({
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
    }),
    [
      settingsState.inpaintEnabled,
      maskDataUrl,
      selectedMaskId,
      inpaintSettings,
    ],
  );

  /** この手番で実際に使われる NovelAI 画像モデル（手番の NSFW 上書きを反映） */
  const resolveTurnImageModel = useCallback(
    (options: TransformOptions | undefined) =>
      resolveEffectiveNovelaiImageModel({
        nsfwMode: options?.nsfwMode ?? settingsState.nsfwMode,
        novelaiImageModel: settingsState.novelaiImageModel,
        novelaiCuratedImageModel: settingsState.novelaiCuratedImageModel,
      }),
    [
      settingsState.nsfwMode,
      settingsState.novelaiImageModel,
      settingsState.novelaiCuratedImageModel,
    ],
  );

  const sendNow = useCallback(
    (pending: PendingTransform) => {
      onTransform(
        pending.message,
        undefined,
        pending.transformationType,
        pending.transformOptions,
        pending.instructionType,
        pending.tempToken,
        pending.useMemory,
      );
    },
    [onTransform],
  );

  /** 精密参照を送る手番なら Anlas の確認を挟んで送る。保留したら false を返す */
  const sendWithAnlasCheck = useCallback(
    (pending: PendingTransform) => {
      const referenceCount =
        pending.transformOptions?.characterReferences?.length ?? 0;
      if (
        referenceCount > 0 &&
        !readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)
      ) {
        setAnlasConfirmPending({
          ...pending,
          anlasCost: referenceCount * ANLAS_PER_PRECISE_REFERENCE,
        });
        return false; // Wait for user confirmation
      }
      sendNow(pending);
      return true;
    },
    [sendNow],
  );

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

      const overrides = resolveTurnOverrides?.(backendInstructionType);
      if (overrides) {
        transformOptions = { ...(transformOptions ?? {}), ...overrides };
      }

      const turnImageModel = resolveTurnImageModel(transformOptions);
      if (imageProvider === "novelai") {
        // text-to-image の手番はバックエンドがマスクを使わない
        const maskActive =
          Boolean(transformOptions?.maskImage || transformOptions?.maskId) &&
          !transformOptions?.imageOnlyTextToImage;
        const { references } = resolveSendablePreciseReferences(
          settingsState.preciseReferences,
          { format: preciseReferenceFormat(turnImageModel), maskActive },
        );
        if (references.length > 0) {
          transformOptions = {
            ...(transformOptions ?? {}),
            characterReferences: references,
          };
        }
      }

      const pending: PendingTransform = {
        message,
        transformationType,
        transformOptions,
        instructionType: backendInstructionType,
        useMemory,
        tempToken,
      };

      // V5 利用上限を使い切った状態での生成は Anlas を消費するため警告する
      const usageExhausted =
        anlasBalance?.usage != null &&
        (anlasBalance.usage.percent <= 0 || anlasBalance.usage.isNegative);
      if (
        imageProvider === "novelai" &&
        isV5ImageModel(turnImageModel) &&
        usageExhausted &&
        !readStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY)
      ) {
        setUsageWarnPending(pending);
        return false; // Wait for user confirmation
      }

      return sendWithAnlasCheck(pending);
    },
    [
      imageProvider,
      buildNovelaiOptions,
      chatState.imageOnlyTextToImage,
      resolveTurnOverrides,
      resolveTurnImageModel,
      settingsState.preciseReferences,
      anlasBalance,
      sendWithAnlasCheck,
    ],
  );

  /** 確認ダイアログのキャンセル: 送信前のユーザーメッセージを取り下げ、文面を入力欄へ戻す */
  const restoreCancelledMessage = useCallback(
    ({ message, tempToken }: PendingTransform) => {
      discardPendingIdentity(tempToken);
      setInputText(message);
    },
    [discardPendingIdentity, setInputText],
  );

  // Anlas confirmation dialog handlers
  const handleAnlasConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!anlasConfirmPending) return;
      const { anlasCost: _anlasCost, ...pending } = anlasConfirmPending;
      if (doNotShowAgain) {
        writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
      }
      setAnlasConfirmPending(null);
      sendNow(pending);
    },
    [anlasConfirmPending, sendNow],
  );

  const handleAnlasCancel = useCallback(() => {
    if (anlasConfirmPending) {
      restoreCancelledMessage(anlasConfirmPending);
    }
    setAnlasConfirmPending(null);
  }, [anlasConfirmPending, restoreCancelledMessage]);

  // V5 利用上限使い切り警告ダイアログのハンドラー。精密参照も送る手番なら、
  // 続けて Anlas の確認へ進む
  const handleUsageWarnConfirm = useCallback(
    (doNotShowAgain: boolean) => {
      if (!usageWarnPending) return;
      if (doNotShowAgain) {
        writeStorageFlag("session", V5_USAGE_WARN_SUPPRESSED_KEY, true);
      }
      setUsageWarnPending(null);
      sendWithAnlasCheck(usageWarnPending);
    },
    [usageWarnPending, sendWithAnlasCheck],
  );

  const handleUsageWarnCancel = useCallback(() => {
    if (usageWarnPending) {
      restoreCancelledMessage(usageWarnPending);
    }
    setUsageWarnPending(null);
  }, [usageWarnPending, restoreCancelledMessage]);

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
