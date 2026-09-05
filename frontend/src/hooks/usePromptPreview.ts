import { useCallback, useState } from "react";
import { type PreviewPromptResponse, previewPrompt } from "../apis/game";
import { useChat } from "../contexts/ChatContext";
import { useGame } from "../contexts/GameContext";
import { useSettings } from "../contexts/SettingsContext";
import { isHistoryLookbackEnabled } from "../utils/historyLookback";

/**
 * プロンプトプレビュー(ENABLE_PROMPT_PREVIEW)。入力欄の指示から
 * 画像編集プロンプトと心境プロンプトを取得し、編集して送信できるようにする。
 */
export function usePromptPreview(
  onSendWithPromptOverride?: (override: string) => void,
) {
  const { state: gameState } = useGame();
  const { state: chatState } = useChat();
  const { state: settingsState } = useSettings();
  const [result, setResult] = useState<PreviewPromptResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editedPrompt, setEditedPrompt] = useState("");
  const [showDetail, setShowDetail] = useState(false);

  const generate = useCallback(async () => {
    if (!gameState.sessionId || !chatState.inputText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const instructionType = chatState.instructionType;
      const transformationType =
        instructionType === "reality_alter" ? "reality" : "costume";
      const next = await previewPrompt({
        session_id: gameState.sessionId,
        instruction: chatState.inputText.trim(),
        transformation_type: transformationType,
        instruction_type: instructionType,
        use_play_memory: settingsState.playMemoryEnabled,
        respect_clothing_layers: settingsState.respectClothingLayers,
        use_history_lookback: isHistoryLookbackEnabled(
          settingsState.historyLookbackTargets,
          instructionType,
        ),
      });
      setResult(next);
      setEditedPrompt(next.image_edit_prompt);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "プレビューの取得に失敗しました",
      );
    } finally {
      setLoading(false);
    }
  }, [
    gameState.sessionId,
    chatState.inputText,
    settingsState.respectClothingLayers,
    chatState.instructionType,
    settingsState.playMemoryEnabled,
    settingsState.historyLookbackTargets,
  ]);

  // 編集済みプロンプトで送信
  const sendWithOverride = useCallback(() => {
    if (!editedPrompt.trim() || !onSendWithPromptOverride) return;
    onSendWithPromptOverride(editedPrompt.trim());
    setResult(null);
    setEditedPrompt("");
  }, [editedPrompt, onSendWithPromptOverride]);

  const toggleDetail = useCallback(() => setShowDetail((prev) => !prev), []);

  return {
    result,
    loading,
    error,
    editedPrompt,
    setEditedPrompt,
    showDetail,
    toggleDetail,
    generate,
    sendWithOverride,
    canGenerate: Boolean(gameState.sessionId && chatState.inputText.trim()),
  };
}
