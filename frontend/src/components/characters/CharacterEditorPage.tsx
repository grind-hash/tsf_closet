import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { openCharacterChatForPreset } from "../../apis/characterChat";
import {
  deleteCharacterPreset,
  getCharacterPreset,
} from "../../apis/characters";
import { usePersistedState } from "../../hooks/usePersistedState";
import { ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import CharacterPortraitSection from "./CharacterPortraitSection";
import CharacterPreview from "./CharacterPreview";
import CharacterSettingsEditor from "./CharacterSettingsEditor";
import TrashIcon from "./TrashIcon";

const PREVIEW_PANEL_OPEN_KEY = "characters_preview_panel_open";
const SECTION_STORAGE_KEY = "character_maker_sections_open";

interface CharacterEditorPageProps {
  presetId: string;
}

/** 1 人のキャラクターを編集する画面。右パネルにプレビューと「このキャラと話す」 */
export default function CharacterEditorPage({
  presetId,
}: CharacterEditorPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [preset, setPreset] = useState<CharacterPreset | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "missing">(
    "loading",
  );
  const [error, setError] = useState<string | null>(null);
  const [talking, setTalking] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [panelOpen, setPanelOpen] = usePersistedState<boolean>(
    PREVIEW_PANEL_OPEN_KEY,
    true,
  );

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getCharacterPreset(presetId)
      .then((loaded) => {
        if (cancelled) return;
        setPreset(loaded);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("Failed to load character", err);
        setStatus("missing");
      });
    return () => {
      cancelled = true;
    };
  }, [presetId]);

  const handleTalk = async () => {
    setTalking(true);
    setError(null);
    try {
      const threadId = await openCharacterChatForPreset(presetId);
      navigate(`${ROUTES.CHARACTER_CHAT}/${threadId}`);
    } catch (err) {
      console.error("Failed to open character chat", err);
      setError(t("characters.errors.talkFailed"));
      setTalking(false);
    }
  };

  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await deleteCharacterPreset(presetId);
      navigate(ROUTES.CHARACTERS);
    } catch (err) {
      console.error("Failed to delete character", err);
      setError(t("characters.errors.deleteFailed"));
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  if (status === "missing") {
    return (
      <MainLayout>
        <div className="character-chat characters">
          <button
            type="button"
            className="character-chat__secondary characters__back"
            onClick={() => navigate(ROUTES.CHARACTERS)}
          >
            ← {t("characters.back")}
          </button>
          <p className="character-chat__empty">{t("characters.notFound")}</p>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout
      rightPanel={
        preset ? (
          <CharacterPreview
            preset={preset}
            talking={talking}
            onTalk={() => void handleTalk()}
          />
        ) : undefined
      }
      showRightPanel={panelOpen}
      onToggleRightPanel={() => setPanelOpen((prev) => !prev)}
    >
      <div className="character-chat characters">
        <header className="characters__editor-header">
          <button
            type="button"
            className="character-chat__secondary characters__back"
            onClick={() => navigate(ROUTES.CHARACTERS)}
          >
            ← {t("characters.back")}
          </button>
          <h1>{preset?.name ?? t("characters.title")}</h1>
          {preset && (
            <button
              type="button"
              className="character-chat__delete"
              aria-label={t("characters.delete")}
              title={t("characters.delete")}
              onClick={() => setDeleteOpen(true)}
            >
              <TrashIcon />
            </button>
          )}
        </header>

        {error && (
          <div className="character-chat__error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)}>
              ✕
            </button>
          </div>
        )}

        {status === "loading" || !preset ? (
          <div className="character-chat__progress" role="status">
            <span />
            {t("characters.loading")}
          </div>
        ) : (
          <CharacterSettingsEditor
            preset={preset}
            onSaved={setPreset}
            sectionStorageKey={SECTION_STORAGE_KEY}
            appearance={
              <CharacterPortraitSection preset={preset} onSaved={setPreset} />
            }
          />
        )}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title={t("characters.deleteTitle")}
        confirmLabel={t("characters.deleteConfirm")}
        cancelLabel={t("characters.cancel")}
        busy={deleting}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setDeleteOpen(false)}
      >
        {t("characters.deleteBody", { name: preset?.name ?? "" })}
      </ConfirmDialog>
    </MainLayout>
  );
}
