/**
 * CharacterPresetPicker - 005 multi-character persistence (T037)
 *
 * Modal-style picker for applying a CharacterPreset to the current session.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  deleteCharacterPreset,
  listCharacterPresets,
} from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import type { CharacterPreset } from "../../types";
import "./CharacterPresetPicker.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CharacterPresetPicker({ open, onClose }: Props) {
  const { t } = useTranslation();
  const { state, applyPresetToCurrentSession, updateSessionCharacterAction } =
    useGame();
  const [presets, setPresets] = useState<CharacterPreset[]>([]);
  const [loading, setLoading] = useState(false);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [applyingProtagonistId, setApplyingProtagonistId] = useState<
    string | null
  >(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const protagonist = state.sessionCharacters.find((c) => c.is_protagonist);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listCharacterPresets()
      .then((items) => {
        if (!cancelled) setPresets(items);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "error");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  const handleDelete = async (preset: CharacterPreset) => {
    if (
      !window.confirm(
        t("character.preset.delete_confirm", "「{{name}}」を削除しますか？", {
          name: preset.name,
        }),
      )
    )
      return;
    setDeletingId(preset.id);
    setError(null);
    try {
      await deleteCharacterPreset(preset.id);
      setPresets((prev) => prev.filter((p) => p.id !== preset.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setDeletingId(null);
    }
  };

  const handleApply = async (preset: CharacterPreset) => {
    setApplyingId(preset.id);
    setError(null);
    try {
      await applyPresetToCurrentSession(preset.id);
      onClose();
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
      setApplyingId(null);
    }
  };

  const handleApplyToProtagonist = async (preset: CharacterPreset) => {
    if (!protagonist) return;
    if (
      !window.confirm(
        t(
          "character.preset.apply_to_protagonist_confirm",
          "「{{preset}}」を主人公「{{name}}」に上書き適用しますか？",
          { preset: preset.name, name: protagonist.name },
        ),
      )
    ) {
      return;
    }
    setApplyingProtagonistId(preset.id);
    setError(null);
    try {
      await updateSessionCharacterAction(protagonist.id, {
        name: preset.name,
        appearance_natural: preset.appearance_natural,
        appearance_tags: preset.appearance_tags,
        position: preset.default_position,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setApplyingProtagonistId(null);
    }
  };

  return (
    <div
      className="character-preset-picker__overlay"
      data-testid="character-preset-picker"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="character-preset-picker__panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="character-preset-picker__header">
          <span className="character-preset-picker__title">
            {t("character.preset.picker_title", "プリセットから追加")}
          </span>
          <button
            type="button"
            className="character-preset-picker__close"
            onClick={onClose}
          >
            {t("character.panel.close", "閉じる")}
          </button>
        </div>
        {loading && (
          <div className="character-preset-picker__status">
            {t("character.preset.loading", "読み込み中…")}
          </div>
        )}
        {error && <div className="character-preset-picker__error">{error}</div>}
        {!loading && presets.length === 0 && !error && (
          <div className="character-preset-picker__status">
            {t("character.preset.empty", "保存済みのプリセットはありません。")}
          </div>
        )}
        <ul className="character-preset-picker__list">
          {presets.map((preset) => (
            <li
              key={preset.id}
              className="character-preset-picker__row"
              data-testid="character-preset-row"
            >
              <span
                className="character-preset-picker__name"
                title={preset.appearance_natural || preset.name}
              >
                {preset.name}
              </span>
              <div className="character-preset-picker__actions">
                <button
                  type="button"
                  className="character-preset-picker__apply"
                  disabled={
                    applyingId === preset.id ||
                    applyingProtagonistId === preset.id ||
                    deletingId === preset.id
                  }
                  onClick={() => void handleApply(preset)}
                >
                  {applyingId === preset.id
                    ? t("character.preset.applying", "適用中…")
                    : t("character.preset.apply", "適用")}
                </button>
                {protagonist && (
                  <button
                    type="button"
                    className="character-preset-picker__apply"
                    disabled={
                      applyingId === preset.id ||
                      applyingProtagonistId === preset.id ||
                      deletingId === preset.id
                    }
                    onClick={() => void handleApplyToProtagonist(preset)}
                    title={t(
                      "character.preset.apply_to_protagonist_title",
                      "現在の主人公の外見をこのプリセットで上書きします",
                    )}
                  >
                    {applyingProtagonistId === preset.id
                      ? t("character.preset.applying", "適用中…")
                      : t(
                          "character.preset.apply_to_protagonist",
                          "主人公に適用",
                        )}
                  </button>
                )}
                <button
                  type="button"
                  className="character-preset-picker__delete"
                  disabled={
                    deletingId === preset.id ||
                    applyingId === preset.id ||
                    applyingProtagonistId === preset.id
                  }
                  onClick={() => void handleDelete(preset)}
                  aria-label={t("character.panel.delete", "削除")}
                >
                  {deletingId === preset.id
                    ? t("character.preset.deleting", "削除中…")
                    : t("character.panel.delete", "削除")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
