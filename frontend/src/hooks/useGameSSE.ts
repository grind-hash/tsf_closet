import { useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import { useNotification } from "../contexts/NotificationContext";
import { useSettings } from "../contexts/SettingsContext";
import { useSSE } from "./useSSE";

export function useGameSSE() {
  const { t } = useTranslation();
  const game = useGame();
  const chat = useChat();
  const settings = useSettings();
  const { showNotification, showAchievementNotification } = useNotification();
  const activePendingTokenRef = useRef<string | null>(null);

  const resolvePendingToken = useCallback(() => {
    if (activePendingTokenRef.current) {
      return activePendingTokenRef.current;
    }
    return chat.getLatestPendingIdentity()?.tempToken ?? null;
  }, [chat]);

  const sse = useSSE({
    onText: (chunk) => {
      game.appendFeelingText(chunk);
    },
    onImage: async (_image, historyId, seed) => {
      const tempToken = resolvePendingToken();
      if (tempToken) {
        chat.resolvePendingIdentity(tempToken, historyId);
      }
      game.updateFromSSE({ image: _image, historyId, seed });
      await game.restoreActiveSession();
    },
    onSurroundingsImage: (imageBase64, historyId, seed) => {
      game.setLastSurroundingsImage({ imageBase64, historyId, seed });
    },
    onStats: (stats) => {
      game.updateStats(stats);
    },
    onCritical: (data) => {
      game.appendFeelingText(`\n\n【${data.name}】\n${data.speech}`);
    },
    onEnding: (data) => {
      if (!settings.state.experimentalEndingEnabled) {
        return;
      }
      game.setEnding({
        id: data.ending_id,
        name: data.title,
        description: data.description,
        triggerCondition: "",
        badge: data.badge,
        speech: data.final_speech,
        summary: data.summary,
      });
    },
    onAchievement: (data) => {
      showAchievementNotification({
        id: data.achievement_id,
        name: data.name,
        description: data.description,
        icon: data.icon,
        category: data.category,
        condition_type: "",
        condition_target: "",
        condition_value: 0,
        is_hidden: false,
      });
    },
    onComplete: (historyId, transformationCount) => {
      const tempToken = resolvePendingToken();
      if (tempToken) {
        chat.finalizePendingIdentity(tempToken, historyId);
      }
      activePendingTokenRef.current = null;
      chat.setStreaming(false);
      game.setTransformationCount(transformationCount);
      game.setTransforming(false);
      if (settings.state.playMemoryEnabled) {
        void game.restoreActiveSession();
      }
      // FR-010: 複数人モード時、バックエンドが主人公レコードを
      // 自動 upsert するため、CharacterPanel の表示を最新化する。
      if (
        settings.state.enableMultiplePeople &&
        settings.state.multiCharacterPanelEnabled
      ) {
        void game.loadSessionCharacters();
      }
    },
    onCost: (cost) => {
      settings.addTotalCost(cost);
    },
    onAnlas: (balance) => {
      settings.setAnlasBalance(balance);
    },
    onRealityAttributeAdded: (data) => {
      game.updateAttributesFromSSE({
        id: data.attribute_id,
        text: data.attribute_text,
      });
      if (settings.state.showRealityAttributeNotification) {
        const message =
          t("settings.realityAttributeAddedMsg", {
            attr: data.attribute_text,
          }) +
          "\n" +
          t("settings.realityAttributeAddedLink");
        showNotification(
          "info",
          t("settings.realityAttributeAdded"),
          message,
          8000,
        );
      }
    },
    onError: (message) => {
      const tempToken = resolvePendingToken();
      if (tempToken) {
        chat.failPendingIdentity(tempToken);
      }
      activePendingTokenRef.current = null;
      chat.setStreaming(false);
      game.setError(message);
      game.setTransforming(false);
    },
  });

  const startPostStream = useCallback(
    (url: string, body: Record<string, unknown>, tempToken?: string) => {
      activePendingTokenRef.current = tempToken ?? null;
      chat.setStreaming(true);
      game.clearFeelingText();
      game.setTransforming(true);
      sse.startPostStream(url, body);
    },
    [chat, game, sse],
  );

  const startStream = useCallback(
    (url: string, tempToken?: string) => {
      activePendingTokenRef.current = tempToken ?? null;
      chat.setStreaming(true);
      game.clearFeelingText();
      game.setTransforming(true);
      sse.startStream(url);
    },
    [chat, game, sse],
  );

  return {
    startPostStream,
    startStream,
    stopStream: sse.stopStream,
    isStreaming: sse.isStreaming,
  };
}
