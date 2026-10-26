/**
 * キャラクター画面の「外見と立ち絵」の節。外見(自然文・タグ)の編集と、
 * 素材の画像の取り込み・外見タグからの立ち絵の生成を行う。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  generateCharacterTags,
  importCharacterPresetPortrait,
  streamCharacterPresetPortrait,
  type UpdateCharacterPresetPayload,
  updateCharacterPreset,
} from "../../apis/characters";
import { useNotification } from "../../contexts/NotificationContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { CharacterPreset } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import { readStorageFlag, writeStorageFlag } from "../../utils/storage";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import SavedTextField from "../panel/SavedTextField";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";

/** 精密参照の Anlas 確認を「ブラウザを閉じるまで出さない」印(sessionStorage) */
const ANLAS_WARN_SUPPRESSED_KEY = "character_maker_anlas_warn_suppressed";

interface CharacterPortraitSectionProps {
  preset: CharacterPreset;
  onSaved: (preset: CharacterPreset) => void;
}

export default function CharacterPortraitSection({
  preset,
  onSaved,
}: CharacterPortraitSectionProps) {
  const { t } = useTranslation();
  const { state: settingsState, addTotalCost } = useSettings();
  const { showNotification } = useNotification();
  const [natural, setNatural] = useState(preset.appearance_natural);
  const [tagsBusy, setTagsBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [usePrecise, setUsePrecise] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preciseAvailable =
    settingsState.imageProvider === "novelai" && Boolean(preset.portrait_url);

  const save = async (payload: UpdateCharacterPresetPayload) => {
    const updated = await updateCharacterPreset(preset.id, payload);
    onSaved(updated);
  };

  const handleGenerateTags = async () => {
    const source = natural.trim();
    if (!source) return;
    if (
      preset.appearance_tags.trim() &&
      !window.confirm(t("characters.generateTagsConfirm"))
    ) {
      return;
    }
    setTagsBusy(true);
    setError(null);
    try {
      const [result] = await generateCharacterTags([
        { id: preset.id, name: preset.name, natural: source },
      ]);
      if (result?.tags) {
        await save({
          appearance_natural: source,
          appearance_tags: result.tags,
        });
      }
    } catch (err) {
      console.error("Failed to generate appearance tags", err);
      setError(t("characters.generateTagsError"));
    } finally {
      setTagsBusy(false);
    }
  };

  const handleImport = async (selection: AdventureSourceSelection) => {
    setPickerOpen(false);
    setError(null);
    const tagsWereEmpty =
      !preset.appearance_tags.trim() && !preset.appearance_natural.trim();
    try {
      const result = await importCharacterPresetPortrait(
        preset.id,
        selection.origin === "prompt_expander"
          ? { prompt_expander_entry_id: selection.promptExpanderEntryId }
          : {
              session_id: selection.sessionId,
              history_id: selection.historyId,
            },
      );
      onSaved(result.preset);
      setNatural(result.preset.appearance_natural);
      showNotification(
        "success",
        tagsWereEmpty && result.preset.appearance_tags
          ? t("characters.portrait.importedWithTags")
          : t("characters.portrait.imported"),
      );
    } catch (err) {
      console.error("Failed to import portrait", err);
      setError(t("characters.errors.importFailed"));
    }
  };

  const runDraw = async (precise: boolean) => {
    setDrawing(true);
    setError(null);
    try {
      await streamCharacterPresetPortrait(
        preset.id,
        (event) => {
          if (event.type === "portrait_image") onSaved(event.data.preset);
          else if (event.type === "cost") addTotalCost(event.data.cost_usd);
          else if (event.type === "error")
            setError(
              event.data.message || t("characters.errors.portraitFailed"),
            );
        },
        { use_precise_reference: precise },
      );
    } catch (err) {
      console.error("Failed to draw portrait", err);
      setError(t("characters.errors.portraitFailed"));
    } finally {
      setDrawing(false);
    }
  };

  const handleDraw = () => {
    const precise = preciseAvailable && usePrecise;
    if (precise && !readStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY)) {
      // 精密参照は Anlas を消費するため、抑止チェック付きの確認を挟む
      setConfirmOpen(true);
      return;
    }
    void runDraw(precise);
  };

  const hasTags = Boolean(preset.appearance_tags.trim());

  return (
    <div className="character-maker__appearance">
      <SavedTextField
        label={t("characters.fields.appearanceNatural")}
        value={preset.appearance_natural}
        multiline
        rows={3}
        maxLength={1000}
        onTextChange={setNatural}
        onSave={(next) => save({ appearance_natural: next })}
        action={
          <button
            type="button"
            className="character-panel__btn"
            disabled={tagsBusy || !natural.trim()}
            title={
              natural.trim()
                ? undefined
                : t("characters.generateTagsNeedNatural")
            }
            onClick={() => void handleGenerateTags()}
          >
            {tagsBusy ? (
              <>
                <span className="character-cast__spinner" aria-hidden />
                {t("characters.generatingTags")}
              </>
            ) : (
              t("characters.generateTags")
            )}
          </button>
        }
      />
      <SavedTextField
        label={t("characters.fields.appearanceTags")}
        value={preset.appearance_tags}
        multiline
        rows={3}
        maxLength={2000}
        favoritePrompt
        hint={t("characters.fields.appearanceTagsHint")}
        onSave={(next) => save({ appearance_tags: next })}
      />

      <div className="character-maker__portrait">
        <div className="character-maker__portrait-frame">
          {preset.portrait_url ? (
            <img src={mediaUrl(preset.portrait_url)} alt="" />
          ) : (
            <span className="character-maker__portrait-empty">
              {t("characters.portrait.none")}
            </span>
          )}
        </div>
        <div className="character-maker__portrait-actions">
          <strong>{t("characters.portrait.title")}</strong>
          <button
            type="button"
            className="character-chat__secondary"
            disabled={drawing}
            onClick={() => setPickerOpen(true)}
          >
            {t("characters.portrait.import")}
          </button>
          <p className="character-cast__hint">
            {t("characters.portrait.importHint")}
          </p>
          <button
            type="button"
            className="character-chat__secondary"
            disabled={drawing || !hasTags}
            onClick={handleDraw}
          >
            {t("characters.portrait.generate")}
          </button>
          {!hasTags && (
            <p className="character-cast__hint">
              {t("characters.portrait.needTags")}
            </p>
          )}
          {preciseAvailable && (
            <label className="character-chat__switch-row">
              <span className="character-chat__switch-info">
                <strong>{t("characters.portrait.precise")}</strong>
                <small>{t("characters.portrait.preciseHint")}</small>
              </span>
              <input
                type="checkbox"
                className="character-chat__switch-input"
                checked={usePrecise}
                onChange={(event) => setUsePrecise(event.target.checked)}
              />
              <span className="character-chat__switch" />
            </label>
          )}
          {drawing && (
            <div className="character-maker__progress" role="status">
              <span className="character-chat__progress">
                <span />
                {t("characters.portrait.generating")}
              </span>
              <small>{t("characters.portrait.generatingHint")}</small>
            </div>
          )}
          {error && (
            <p className="character-maker__error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>

      {pickerOpen && (
        <AdventureSessionPickerModal
          title={t("characters.portrait.importTitle")}
          selected={null}
          onSelect={(selection) => void handleImport(selection)}
          onClose={() => setPickerOpen(false)}
          allowPromptExpander={settingsState.experimentalPromptExpanderEnabled}
        />
      )}

      <AnlasConfirmDialog
        open={confirmOpen}
        body={t("characters.portrait.anlasBody")}
        checkboxId="character-maker-anlas-suppress"
        onConfirm={(suppress) => {
          if (suppress)
            writeStorageFlag("session", ANLAS_WARN_SUPPRESSED_KEY, true);
          setConfirmOpen(false);
          void runDraw(true);
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
