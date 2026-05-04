/**
 * CharacterPanel - 005 multi-character persistence
 *
 * Displays the persisted session_character roster, allows add/edit/delete,
 * and shows position assignments. Only rendered when
 * SettingsContext.enableMultiplePeople is true.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { createCharacterPreset } from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import type { CharacterPosition, SessionCharacter } from "../../types";
import CharacterPresetPicker from "./CharacterPresetPicker";
import "./CharacterPanel.css";

const POSITIONS: CharacterPosition[] = [
  "left",
  "center-left",
  "center",
  "center-right",
  "right",
];

const CHARACTER_LIMIT = 4;

interface NewCharacterDraft {
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  position: CharacterPosition;
}

const emptyDraft: NewCharacterDraft = {
  name: "",
  appearance_natural: "",
  appearance_tags: "",
  position: "center",
};

export default function CharacterPanel() {
  const { t } = useTranslation();
  const {
    state,
    loadSessionCharacters,
    addSessionCharacter,
    updateSessionCharacterAction,
    removeSessionCharacter,
  } = useGame();

  const [draft, setDraft] = useState<NewCharacterDraft>(emptyDraft);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [savingPresetId, setSavingPresetId] = useState<string | null>(null);

  useEffect(() => {
    if (state.sessionId) {
      void loadSessionCharacters();
    }
  }, [state.sessionId, loadSessionCharacters]);

  const characters: SessionCharacter[] = useMemo(
    () =>
      [...state.sessionCharacters].sort((a, b) => a.slot_index - b.slot_index),
    [state.sessionCharacters],
  );

  const reachedLimit = characters.length >= CHARACTER_LIMIT;

  const handleCreate = async () => {
    setError(null);
    if (!draft.name.trim()) {
      setError(t("character.error.name_required", "名前を入力してください"));
      return;
    }
    setIsAdding(true);
    try {
      await addSessionCharacter({
        name: draft.name.trim(),
        appearance_natural: draft.appearance_natural,
        appearance_tags: draft.appearance_tags,
        position: draft.position,
      });
      setDraft(emptyDraft);
    } catch (err) {
      const message = err instanceof Error ? err.message : "error";
      if (message === "character_limit_exceeded") {
        setError(
          t("character.error.limit_exceeded", "登場人物は最大4人までです"),
        );
      } else {
        setError(message);
      }
    } finally {
      setIsAdding(false);
    }
  };

  const handlePositionChange = async (
    character: SessionCharacter,
    next: CharacterPosition,
  ) => {
    if (next === character.position) return;
    try {
      await updateSessionCharacterAction(character.id, { position: next });
    } catch (err) {
      console.error("Failed to update position", err);
    }
  };

  const handleDelete = async (character: SessionCharacter) => {
    if (
      !window.confirm(
        t("character.confirm.delete", "{{name}}を削除しますか？", {
          name: character.name,
        }),
      )
    ) {
      return;
    }
    try {
      await removeSessionCharacter(character.id);
    } catch (err) {
      console.error("Failed to delete character", err);
    }
  };

  const handleSaveAsPreset = async (character: SessionCharacter) => {
    const presetName = window.prompt(
      t("character.preset.save_prompt", "プリセット名を入力"),
      character.name,
    );
    if (!presetName || !presetName.trim()) return;
    setSavingPresetId(character.id);
    setError(null);
    try {
      await createCharacterPreset({
        from_character_id: character.id,
        name: presetName.trim(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setSavingPresetId(null);
    }
  };

  if (!state.sessionId) {
    return null;
  }

  return (
    <div className="character-panel" data-testid="character-panel">
      <div className="character-panel__header">
        <span className="character-panel__title">
          {t("character.panel.title", "登場人物")}
        </span>
        <span className="character-panel__count">
          {characters.length} / {CHARACTER_LIMIT}
        </span>
        <button
          type="button"
          className="character-panel__btn"
          onClick={() => setPickerOpen(true)}
          disabled={reachedLimit}
          data-testid="character-apply-preset-button"
        >
          {t("character.preset.apply_button", "プリセット")}
        </button>
      </div>

      {characters.length === 0 ? (
        <div className="character-panel__empty">
          {t("character.panel.empty", "まだ登場人物が登録されていません。")}
        </div>
      ) : (
        <div className="character-panel__list">
          {characters.map((character) => (
            <div
              key={character.id}
              className="character-panel__row"
              data-testid="character-row"
            >
              <div className="character-panel__row-header">
                <span className="character-panel__slot">
                  {character.slot_index + 1}.
                </span>
                <span
                  className="character-panel__name"
                  title={character.appearance_natural || character.name}
                >
                  {character.name}
                </span>
                <button
                  type="button"
                  className="character-panel__btn character-panel__btn--danger"
                  onClick={() => void handleDelete(character)}
                >
                  {t("character.panel.delete", "削除")}
                </button>
              </div>
              <div className="character-panel__row-controls">
                <select
                  className="character-panel__position"
                  aria-label={t("character.field.position", "立ち位置")}
                  value={character.position}
                  onChange={(e) =>
                    void handlePositionChange(
                      character,
                      e.target.value as CharacterPosition,
                    )
                  }
                >
                  {POSITIONS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="character-panel__btn"
                  onClick={() =>
                    setEditingId(
                      editingId === character.id ? null : character.id,
                    )
                  }
                >
                  {editingId === character.id
                    ? t("character.panel.close", "閉じる")
                    : t("character.panel.edit", "編集")}
                </button>
              </div>
              {editingId === character.id && (
                <div className="character-panel__row-edit">
                  <input
                    type="text"
                    value={character.name}
                    onChange={(e) =>
                      void updateSessionCharacterAction(character.id, {
                        name: e.target.value,
                      })
                    }
                    placeholder={t("character.field.name", "名前")}
                  />
                  <textarea
                    value={character.appearance_natural || ""}
                    onChange={(e) =>
                      void updateSessionCharacterAction(character.id, {
                        appearance_natural: e.target.value,
                      })
                    }
                    placeholder={t(
                      "character.field.appearance_natural",
                      "外見（自然文）",
                    )}
                  />
                  <textarea
                    value={character.appearance_tags || ""}
                    onChange={(e) =>
                      void updateSessionCharacterAction(character.id, {
                        appearance_tags: e.target.value,
                      })
                    }
                    placeholder={t(
                      "character.field.appearance_tags",
                      "外見タグ (NovelAI 形式)",
                    )}
                  />
                  <button
                    type="button"
                    className="character-panel__btn"
                    onClick={() => void handleSaveAsPreset(character)}
                    disabled={savingPresetId === character.id}
                    data-testid="character-save-preset-button"
                  >
                    {savingPresetId === character.id
                      ? t("character.preset.saving", "保存中…")
                      : t("character.preset.save", "プリセット保存")}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!reachedLimit && (
        <div className="character-panel__add">
          <input
            type="text"
            value={draft.name}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, name: e.target.value }))
            }
            placeholder={t("character.field.name", "名前")}
            data-testid="character-new-name"
          />
          <textarea
            value={draft.appearance_natural}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                appearance_natural: e.target.value,
              }))
            }
            placeholder={t(
              "character.field.appearance_natural",
              "外見（自然文）",
            )}
          />
          <textarea
            value={draft.appearance_tags}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                appearance_tags: e.target.value,
              }))
            }
            placeholder={t(
              "character.field.appearance_tags",
              "外見タグ (NovelAI 形式)",
            )}
          />
          <select
            value={draft.position}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                position: e.target.value as CharacterPosition,
              }))
            }
          >
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          {error && <div className="character-panel__error">{error}</div>}
          <button
            type="button"
            className="character-panel__btn"
            disabled={isAdding}
            onClick={() => void handleCreate()}
            data-testid="character-add-button"
          >
            {isAdding
              ? t("character.panel.adding", "追加中…")
              : t("character.panel.add", "追加")}
          </button>
        </div>
      )}
      <CharacterPresetPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
