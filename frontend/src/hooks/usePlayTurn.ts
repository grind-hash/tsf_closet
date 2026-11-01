import { useCallback } from "react";
import { useGame } from "../contexts/GameContext";
import { useSettings } from "../contexts/SettingsContext";
import { DEFAULT_INPAINT_SETTINGS } from "../types";
import { API_BASE } from "../utils/api";
import { isHistoryLookbackEnabled } from "../utils/historyLookback";
import { useGameSSE } from "./useGameSSE";
import type { TransformHandler, TransformOptions } from "./useTransformRequest";

/**
 * 手番(着せ替え・現実改変・行動・画像のみ)を /game/play/stream へ送る。
 * 送信内容は設定から組み立て、通常のプレイ画面とサロンの接客画面で共有する。
 * 結果は useGameSSE が GameContext / ChatContext へ反映する。
 */
export function usePlayTurn(): TransformHandler {
  const { state: gameState } = useGame();
  const { state: settingsState, isNovelaiV5Active } = useSettings();
  const sse = useGameSSE();

  return useCallback(
    (
      instruction: string,
      costumeImage?: string,
      transformationType: string = "costume",
      options?: TransformOptions,
      instructionType?: string,
      pendingToken?: string,
      useMemory: boolean = false,
    ) => {
      void pendingToken;
      if (!gameState.sessionId || gameState.isTransforming) return;

      // POST リクエストボディを構築
      const body: Record<string, unknown> = {
        session_id: gameState.sessionId,
        instruction,
        transformation_type: transformationType,
        language: settingsState.language,
      };
      if (instructionType) {
        body.instruction_type = instructionType;
      }
      body.use_history_lookback = isHistoryLookbackEnabled(
        settingsState.historyLookbackTargets,
        instructionType,
      );
      body.use_memory = useMemory;
      body.use_play_memory = settingsState.playMemoryEnabled;
      // Include seed if specified in settings
      if (settingsState.seed !== null) {
        body.seed = settingsState.seed;
      }
      // US3: Include surroundings image generation setting
      if (settingsState.enableSurroundingsImage) {
        body.enable_surroundings_image = true;
        if (settingsState.surroundingsIncludePeople) {
          body.surroundings_include_people = true;
        }
      }
      // Clothing color consistency experimental feature
      if (settingsState.clothingColorConsistency) {
        body.clothing_color_consistency = true;
      }
      if (settingsState.respectClothingLayers) {
        body.respect_clothing_layers = true;
      }

      // Multiple people experimental feature.
      // パネル OFF でも複数人表示自体は維持し、
      // 画像プロンプトへの session_characters 注入のみ use_character_panel でゲートする。
      if (settingsState.enableMultiplePeople) {
        body.enable_multiple_people = true;
      }
      body.use_character_panel = settingsState.multiCharacterPanelEnabled;
      if (costumeImage) {
        body.costume_image = costumeImage;
      }
      if (options?.maskImage) {
        body.mask_image = options.maskImage;
      } else if (options?.maskId) {
        body.mask_id = options.maskId;
      }

      // NovelAI利用時は常にi2i強度とノイズを送信（Image2Image必須）
      // optionsで明示的に指定された場合はそちらを優先、なければデフォルト値を使用
      if (settingsState.imageProvider === "novelai") {
        body.inpaint_strength =
          options?.inpaintStrength ?? DEFAULT_INPAINT_SETTINGS.i2iStrength;
        body.inpaint_noise =
          options?.inpaintNoise ?? DEFAULT_INPAINT_SETTINGS.inpaintNoise;
      } else {
        // NovelAI以外の場合は、明示的に指定された場合のみ送信
        if (options?.inpaintStrength !== undefined) {
          body.inpaint_strength = options.inpaintStrength;
        }
        if (options?.inpaintNoise !== undefined) {
          body.inpaint_noise = options.inpaintNoise;
        }
      }

      if (options?.negativePrompt) {
        body.negative_prompt = options.negativePrompt;
      }
      if (options?.promptOverride) {
        body.prompt_override = options.promptOverride;
      }
      // 画像のみモード: 前画像を使わず text-to-image で生成する
      if (options?.imageOnlyTextToImage) {
        body.image_only_text_to_image = true;
      }
      if (options?.nsfwMode !== undefined) {
        body.nsfw_mode = options.nsfwMode;
      }
      // Build character_references for NovelAI precise reference images
      // (V5系モデルは精密参照非対応のため送らない)
      if (
        !isNovelaiV5Active &&
        options?.characterReferences &&
        options.characterReferences.length > 0
      ) {
        body.character_references = options.characterReferences.map((ref) => {
          // Strip data URL prefix (e.g. "data:image/png;base64,") to get raw base64
          let imageBase64 = ref.imageData;
          if (imageBase64.startsWith("data:")) {
            imageBase64 = imageBase64.split(",", 2)[1] || imageBase64;
          }
          return {
            image: imageBase64,
            type: ref.type,
            strength: ref.strength,
            fidelity: ref.fidelity,
          };
        });
      }

      sse.startPostStream(`${API_BASE}/game/play/stream`, body, pendingToken);
    },
    [
      gameState.sessionId,
      gameState.isTransforming,
      sse,
      settingsState.language,
      settingsState.seed,
      settingsState.enableSurroundingsImage,
      settingsState.surroundingsIncludePeople,
      settingsState.clothingColorConsistency,
      settingsState.respectClothingLayers,
      settingsState.enableMultiplePeople,
      settingsState.multiCharacterPanelEnabled,
      settingsState.imageProvider,
      settingsState.playMemoryEnabled,
      settingsState.historyLookbackTargets,
      isNovelaiV5Active,
    ],
  );
}
