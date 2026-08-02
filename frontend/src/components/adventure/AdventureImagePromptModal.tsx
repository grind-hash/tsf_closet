import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  AdventureImagePrompt,
  AdventureImageRegenerateOptions,
} from "../../apis/adventure";

interface AdventureImagePromptModalProps {
  isOpen: boolean;
  prompt: AdventureImagePrompt | null;
  onClose: () => void;
  onSubmit: (options: AdventureImageRegenerateOptions) => void;
}

export default function AdventureImagePromptModal({
  isOpen,
  prompt,
  onClose,
  onSubmit,
}: AdventureImagePromptModalProps) {
  const { t } = useTranslation();
  const [sceneTags, setSceneTags] = useState("");
  const [playerTags, setPlayerTags] = useState("");
  const [npcTags, setNpcTags] = useState("");
  const [redrawFromReference, setRedrawFromReference] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setSceneTags(prompt?.scene_tags ?? "");
    setPlayerTags(prompt?.player_tags ?? "");
    setNpcTags((prompt?.npc_tags ?? []).join("\n"));
    setRedrawFromReference(true);
  }, [isOpen, prompt]);

  if (!isOpen) return null;

  const canSubmit = sceneTags.trim().length > 0 && playerTags.trim().length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit({
      scene_tags: sceneTags.trim(),
      player_tags: playerTags.trim(),
      npc_tags: npcTags
        .split("\n")
        .map((tag) => tag.trim())
        .filter((tag) => tag.length > 0)
        .slice(0, 3),
      redraw_from_reference: redrawFromReference,
    });
  };

  return (
    <div
      className="adventure-prompt-modal"
      role="dialog"
      aria-modal="true"
      aria-label={t("adventure.imagePrompt.title")}
    >
      <button
        type="button"
        className="adventure-prompt-modal__backdrop"
        aria-label={t("adventure.imagePrompt.cancel")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel">
        <h2>{t("adventure.imagePrompt.title")}</h2>
        <p className="adventure-prompt-modal__hint">
          {t("adventure.imagePrompt.hint")}
        </p>

        <label htmlFor="adventure-prompt-scene">
          {t("adventure.imagePrompt.sceneTags")}
        </label>
        <textarea
          id="adventure-prompt-scene"
          rows={3}
          maxLength={1800}
          value={sceneTags}
          onChange={(event) => setSceneTags(event.target.value)}
        />

        <label htmlFor="adventure-prompt-player">
          {t("adventure.imagePrompt.playerTags")}
        </label>
        <textarea
          id="adventure-prompt-player"
          rows={3}
          maxLength={1200}
          value={playerTags}
          onChange={(event) => setPlayerTags(event.target.value)}
        />

        <label htmlFor="adventure-prompt-npc">
          {t("adventure.imagePrompt.npcTags")}
        </label>
        <textarea
          id="adventure-prompt-npc"
          rows={3}
          value={npcTags}
          onChange={(event) => setNpcTags(event.target.value)}
          placeholder={t("adventure.imagePrompt.npcHint")}
        />

        <label className="adventure-prompt-modal__toggle">
          <input
            type="checkbox"
            checked={redrawFromReference}
            onChange={(event) => setRedrawFromReference(event.target.checked)}
          />
          <span>
            <strong>{t("adventure.imagePrompt.redrawFromReference")}</strong>
            <small>{t("adventure.imagePrompt.redrawHint")}</small>
          </span>
        </label>

        <div className="adventure-prompt-modal__actions">
          <button type="button" onClick={onClose}>
            {t("adventure.imagePrompt.cancel")}
          </button>
          <button
            type="button"
            className="is-primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {t("adventure.imagePrompt.submit")}
          </button>
        </div>
      </div>
    </div>
  );
}
