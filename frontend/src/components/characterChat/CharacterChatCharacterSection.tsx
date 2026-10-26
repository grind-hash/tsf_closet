import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { CharacterChatThread } from "../../apis/characterChat";
import { getCharacterPreset } from "../../apis/characters";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import CharacterPickerModal from "../characters/CharacterPickerModal";
import CharacterSettingsEditor from "../characters/CharacterSettingsEditor";

const SECTION_STORAGE_KEY = "character_chat_character_sections_open";

interface CharacterChatCharacterSectionProps {
  thread: CharacterChatThread;
}

/**
 * 右パネルの「キャラクター設定」。紐づくキャラクター本体をその場で編集する。
 * セッション由来の会話には、キャラクターを作って(または選んで)重ねられる。
 */
export default function CharacterChatCharacterSection({
  thread,
}: CharacterChatCharacterSectionProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { linkCharacter, unlinkCharacter, applyCharacterUpdate } =
    useCharacterChat();
  const character = thread.character ?? null;
  const presetId = character && !character.missing ? character.id : null;
  const [preset, setPreset] = useState<CharacterPreset | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPreset(null);
    setLoadFailed(false);
    if (!presetId) return;
    let cancelled = false;
    getCharacterPreset(presetId)
      .then((loaded) => {
        if (!cancelled) setPreset(loaded);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [presetId]);

  const runLink = async (action: () => Promise<boolean>) => {
    setBusy(true);
    await action();
    setBusy(false);
  };

  const handleSaved = (updated: CharacterPreset) => {
    setPreset(updated);
    applyCharacterUpdate(updated);
  };

  const isSession = thread.kind === "session";

  let body: ReactNode;
  if (thread.kind === "base") {
    body = (
      <p className="character-chat-panel__empty">
        {t("characterChat.panel.characterUnavailableBase")}
      </p>
    );
  } else if (thread.kind === "adventure") {
    body = (
      <p className="character-chat-panel__empty">
        {t("characterChat.panel.characterUnavailableAdventure")}
      </p>
    );
  } else if (presetId) {
    body = (
      <>
        <p className="character-chat-panel__hint">
          {t("characterChat.panel.characterHint")}
        </p>
        <button
          type="button"
          className="character-chat__secondary"
          onClick={() => navigate(`${ROUTES.CHARACTERS}/${presetId}`)}
        >
          {t("characterChat.panel.characterOpen")}
        </button>
        {loadFailed ? (
          <p className="character-chat-panel__empty" role="alert">
            {t("characterChat.panel.characterLoadFailed")}
          </p>
        ) : preset ? (
          <CharacterSettingsEditor
            preset={preset}
            onSaved={handleSaved}
            sectionStorageKey={SECTION_STORAGE_KEY}
            appearanceNote={t("characterChat.panel.characterAppearanceNote")}
          />
        ) : (
          <div className="character-chat__progress" role="status">
            <span />
            {t("characterChat.panel.characterLoading")}
          </div>
        )}
        {isSession && (
          <>
            <button
              type="button"
              className="character-chat__secondary"
              disabled={busy}
              onClick={() => void runLink(unlinkCharacter)}
            >
              {t("characterChat.panel.characterUnlink")}
            </button>
            <p className="character-chat-panel__hint">
              {t("characterChat.panel.characterUnlinkHint")}
            </p>
          </>
        )}
      </>
    );
  } else {
    body = (
      <>
        {character?.missing && (
          <p className="character-chat-panel__empty">
            {t("characterChat.panel.characterMissing")}
          </p>
        )}
        {isSession && (
          <>
            <p className="character-chat-panel__hint">
              {t("characterChat.panel.characterSessionIntro")}
            </p>
            <div className="character-chat__card-buttons">
              <button
                type="button"
                className="character-chat__secondary"
                disabled={busy}
                onClick={() => void runLink(() => linkCharacter())}
              >
                {t("characterChat.panel.characterCreateFromThread")}
              </button>
              <button
                type="button"
                className="character-chat__secondary"
                disabled={busy}
                onClick={() => setPickerOpen(true)}
              >
                {t("characterChat.panel.characterChoose")}
              </button>
            </div>
          </>
        )}
      </>
    );
  }

  return (
    <section className="character-chat-panel__section">
      <h3>{t("characterChat.panel.character")}</h3>
      {body}
      {pickerOpen && (
        <CharacterPickerModal
          title={t("characterChat.panel.characterChoose")}
          onSelect={(selected) => {
            setPickerOpen(false);
            void runLink(() => linkCharacter(selected.id));
          }}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </section>
  );
}
