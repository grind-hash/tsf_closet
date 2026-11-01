/**
 * キャラクターでプレイを始めるダイアログ。自分自身モード・依頼モードを選んで、
 * キャラクターの立ち絵と人物設定からセッションを始め、プレイ画面へ移る。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { getGameSessionPath, ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import PlayStartModeOptions, {
  usePlayStartBlocked,
} from "../chat/PlayStartModeOptions";
import ConfirmDialog from "../ui/ConfirmDialog";

interface CharacterPlayStartDialogProps {
  /** プレイするキャラクター。null の間は閉じている */
  preset: CharacterPreset | null;
  onClose: () => void;
}

export default function CharacterPlayStartDialog({
  preset,
  onClose,
}: CharacterPlayStartDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: gameState, startNewSession, generateRequest } = useGame();
  const { clearMessages } = useChat();
  const needsProfile = usePlayStartBlocked();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasPortrait = Boolean(preset?.portrait_url);

  const handleStart = async () => {
    if (!preset) return;
    setStarting(true);
    setError(null);
    try {
      const sessionId = await startNewSession({
        source: "preset",
        characterId: preset.id,
        selfMode: gameState.selfMode,
      });
      // 前のセッションのチャット表示を新しいプレイへ持ち込まない
      clearMessages();
      // 依頼モード: 開始を待たせず、依頼カードのスピナーを出しながら生成する
      if (gameState.requestMode && !gameState.selfMode) {
        void generateRequest(sessionId, {
          turnLimit: gameState.requestTurnLimit,
        });
      }
      navigate(getGameSessionPath(sessionId));
    } catch (err) {
      console.error("Failed to start play from character", err);
      setError(
        err instanceof Error && err.message
          ? err.message
          : t("characters.play.failed"),
      );
      setStarting(false);
    }
  };

  const handleClose = () => {
    setError(null);
    onClose();
  };

  return (
    <ConfirmDialog
      open={preset !== null}
      title={t("characters.play.title", { name: preset?.name ?? "" })}
      confirmLabel={
        starting ? t("characters.play.starting") : t("characters.play.start")
      }
      cancelLabel={t("characters.cancel")}
      busy={starting}
      confirmDisabled={!hasPortrait || needsProfile}
      dismissible
      onConfirm={() => void handleStart()}
      onCancel={handleClose}
      className="character-play-dialog"
    >
      {!hasPortrait && preset && (
        <p className="character-play-dialog__warning">
          {t("characters.play.noPortrait")}
          <Link to={`${ROUTES.CHARACTERS}/${preset.id}`} onClick={handleClose}>
            {t("characters.play.openEditor")}
          </Link>
        </p>
      )}
      <PlayStartModeOptions />
      {error && (
        <p className="character-play-dialog__error" role="alert">
          {error}
        </p>
      )}
    </ConfirmDialog>
  );
}
