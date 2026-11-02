import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { openCharacterChatForPreset } from "../../apis/characterChat";
import {
  createCharacterPreset,
  deleteCharacterPreset,
  importCustomCharacterPresets,
  listCharacterPresets,
} from "../../apis/characters";
import { useNotification } from "../../contexts/NotificationContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import { API_BASE } from "../../utils/api";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import CharacterPlayStartDialog from "./CharacterPlayStartDialog";
import { EMPTY_CHARACTER_PROFILE } from "./characterMaker";
import TrashIcon from "./TrashIcon";

/** 新規プレイの「作成したキャラクター」(v0.12.0 で削除予定)が残っている数 */
async function countLegacyCustomCharacters(): Promise<number> {
  const response = await fetch(`${API_BASE}/game/custom-characters`);
  if (!response.ok) return 0;
  const data = (await response.json()) as { characters?: unknown[] };
  return data.characters?.length ?? 0;
}

/** キャラクターの一覧。作成・プレイの開始・会話の開始・編集・削除の入口 */
export default function CharacterListView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const { showNotification } = useNotification();
  const chatEnabled = settingsState.characterChatEnabled;
  const [presets, setPresets] = useState<CharacterPreset[] | null>(null);
  const [playTarget, setPlayTarget] = useState<CharacterPreset | null>(null);
  const [legacyCount, setLegacyCount] = useState(0);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [talkingId, setTalkingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CharacterPreset | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      setPresets(await listCharacterPresets());
    } catch (err) {
      console.error("Failed to load characters", err);
      setError(t("characters.errors.loadFailed"));
      setPresets([]);
    }
  }, [t]);

  useEffect(() => {
    void load();
    countLegacyCustomCharacters()
      .then(setLegacyCount)
      .catch(() => setLegacyCount(0));
  }, [load]);

  const handleImportLegacy = async () => {
    setImporting(true);
    setError(null);
    try {
      const imported = await importCustomCharacterPresets();
      setLegacyCount(0);
      showNotification(
        "success",
        imported.length > 0
          ? t("characters.legacy.done", { count: imported.length })
          : t("characters.legacy.none"),
      );
      await load();
    } catch (err) {
      console.error("Failed to import custom characters", err);
      setError(t("characters.legacy.failed"));
    } finally {
      setImporting(false);
    }
  };

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const created = await createCharacterPreset({
        name: t("characters.newName"),
        profile: EMPTY_CHARACTER_PROFILE,
      });
      navigate(`${ROUTES.CHARACTERS}/${created.id}`);
    } catch (err) {
      console.error("Failed to create character", err);
      setError(t("characters.errors.createFailed"));
    } finally {
      setCreating(false);
    }
  };

  const handleTalk = async (preset: CharacterPreset) => {
    setTalkingId(preset.id);
    setError(null);
    try {
      const threadId = await openCharacterChatForPreset(preset.id);
      navigate(`${ROUTES.CHARACTER_CHAT}/${threadId}`);
    } catch (err) {
      console.error("Failed to open character chat", err);
      setError(t("characters.errors.talkFailed"));
      setTalkingId(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteCharacterPreset(deleteTarget.id);
      setPresets((prev) =>
        (prev ?? []).filter((item) => item.id !== deleteTarget.id),
      );
      setDeleteTarget(null);
    } catch (err) {
      console.error("Failed to delete character", err);
      setError(t("characters.errors.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <MainLayout>
      <div className="character-chat characters">
        <header className="character-chat__header characters__header">
          <div>
            <h1>{t("characters.title")}</h1>
            <p className="character-chat__intro">{t("characters.intro")}</p>
          </div>
          <button
            type="button"
            className="character-chat__primary"
            disabled={creating}
            onClick={() => void handleCreate()}
          >
            {creating ? t("characters.creating") : t("characters.create")}
          </button>
        </header>

        {legacyCount > 0 && (
          <div className="characters__legacy">
            <p>{t("characters.legacy.hint", { count: legacyCount })}</p>
            <button
              type="button"
              className="character-chat__secondary"
              disabled={importing}
              onClick={() => void handleImportLegacy()}
            >
              {importing
                ? t("characters.legacy.importing")
                : t("characters.legacy.import")}
            </button>
          </div>
        )}

        {error && (
          <div className="character-chat__error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)}>
              ✕
            </button>
          </div>
        )}

        {presets === null ? (
          <div className="character-chat__progress" role="status">
            <span />
            {t("characters.loading")}
          </div>
        ) : presets.length === 0 ? (
          <p className="character-chat__empty">{t("characters.empty")}</p>
        ) : (
          <ul className="characters__grid">
            {presets.map((preset) => (
              <li key={preset.id} className="characters__card">
                <button
                  type="button"
                  className="characters__card-open"
                  onClick={() => navigate(`${ROUTES.CHARACTERS}/${preset.id}`)}
                >
                  <span className="characters__thumb">
                    {preset.thumbnail_url ? (
                      <img src={mediaUrl(preset.thumbnail_url)} alt="" />
                    ) : (
                      <span aria-hidden>👤</span>
                    )}
                  </span>
                  <span className="characters__card-text">
                    <strong>{preset.name}</strong>
                    <span className="characters__card-personality">
                      {preset.profile?.personality ||
                        t("characters.noPersonality")}
                    </span>
                  </span>
                  <span className="characters__badges">
                    {preset.avatar_model_id && (
                      <span className="character-chat__chip">
                        {t("characters.badgeVrm")}
                      </span>
                    )}
                    {preset.voice && (
                      <span className="character-chat__chip">
                        {t("characters.badgeVoice")}
                      </span>
                    )}
                  </span>
                </button>
                <div className="characters__card-actions">
                  <button
                    type="button"
                    className="character-chat__primary"
                    onClick={() => setPlayTarget(preset)}
                  >
                    {t("characters.play.open")}
                  </button>
                  {chatEnabled && (
                    <button
                      type="button"
                      className="character-chat__secondary"
                      disabled={talkingId !== null}
                      onClick={() => void handleTalk(preset)}
                    >
                      {talkingId === preset.id
                        ? t("characters.talking")
                        : t("characters.talk")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="character-chat__secondary"
                    onClick={() =>
                      navigate(`${ROUTES.CHARACTERS}/${preset.id}`)
                    }
                  >
                    {t("characters.edit")}
                  </button>
                  <button
                    type="button"
                    className="character-chat__delete"
                    aria-label={t("characters.delete")}
                    title={t("characters.delete")}
                    onClick={() => setDeleteTarget(preset)}
                  >
                    <TrashIcon />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <CharacterPlayStartDialog
        preset={playTarget}
        onClose={() => setPlayTarget(null)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("characters.deleteTitle")}
        confirmLabel={t("characters.deleteConfirm")}
        cancelLabel={t("characters.cancel")}
        busy={deleting}
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      >
        {t("characters.deleteBody", { name: deleteTarget?.name ?? "" })}
      </ConfirmDialog>
    </MainLayout>
  );
}
