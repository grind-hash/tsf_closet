/**
 * CharacterGroupPresetModal - 登場人物の組み合わせ（主人公以外の一式）を保存・呼び出す。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createCharacterGroupPreset,
  deleteCharacterGroupPreset,
  listCharacterGroupPresets,
  updateCharacterGroupPreset,
} from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { CharacterGroupPreset } from "../../types";
import { countOnStage, getStageLimit } from "../../utils/characterStage";
import "./CharacterPanel.css";
import "./CharacterCastModal.css";

interface CharacterGroupPresetModalProps {
  onClose: () => void;
}

export default function CharacterGroupPresetModal({
  onClose,
}: CharacterGroupPresetModalProps) {
  const { t } = useTranslation();
  const { state, applyGroupPresetToCurrentSession } = useGame();
  const { isNovelaiV5Active } = useSettings();

  const [groups, setGroups] = useState<CharacterGroupPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const nonProtagonistCount = state.sessionCharacters.filter(
    (c) => !c.is_protagonist,
  ).length;
  const stageLimit = getStageLimit(isNovelaiV5Active);

  useEffect(() => {
    let cancelled = false;
    listCharacterGroupPresets()
      .then((items) => {
        if (!cancelled) setGroups(items);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed || !state.sessionId) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const duplicate = groups.find((g) => g.name === trimmed);
      if (duplicate) {
        if (
          !window.confirm(
            t("character.group.overwriteConfirm", { name: trimmed }),
          )
        ) {
          return;
        }
        const updated = await updateCharacterGroupPreset(duplicate.id, {
          from_session_id: state.sessionId,
        });
        setGroups((prev) =>
          prev.map((g) => (g.id === updated.id ? updated : g)),
        );
      } else {
        const created = await createCharacterGroupPreset({
          name: trimmed,
          from_session_id: state.sessionId,
        });
        setGroups((prev) =>
          [...prev, created].sort((a, b) => a.name.localeCompare(b.name)),
        );
      }
      setName("");
      setNotice(t("character.group.saved", { name: trimmed }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setSaving(false);
    }
  };

  const handleApply = async (group: CharacterGroupPreset) => {
    if (
      !window.confirm(
        t("character.group.applyConfirm", {
          name: group.name,
          count: group.members.length,
        }),
      )
    ) {
      return;
    }
    setBusyId(group.id);
    setError(null);
    setNotice(null);
    try {
      const records = await applyGroupPresetToCurrentSession(group.id);
      const onStage = countOnStage(records);
      setNotice(
        onStage > stageLimit
          ? `${t("character.group.applied", { name: group.name })} ${t(
              "character.panel.overLimit",
              { limit: stageLimit },
            )}`
          : t("character.group.applied", { name: group.name }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (group: CharacterGroupPreset) => {
    if (
      !window.confirm(t("character.group.deleteConfirm", { name: group.name }))
    ) {
      return;
    }
    setBusyId(group.id);
    setError(null);
    try {
      await deleteCharacterGroupPreset(group.id);
      setGroups((prev) => prev.filter((g) => g.id !== group.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="character-cast"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className="character-cast__dialog character-cast__dialog--narrow"
        role="dialog"
        aria-modal="true"
        aria-labelledby="character-group-title"
        data-testid="character-group-modal"
      >
        <header className="character-cast__header">
          <h2 id="character-group-title">{t("character.group.title")}</h2>
          <button
            type="button"
            className="character-cast__close"
            aria-label={t("character.panel.close")}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <p className="character-cast__note">
          {t("character.group.description")}
        </p>

        <div className="character-group__save">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                void handleSave();
              }
            }}
            placeholder={t("character.group.namePlaceholder")}
            maxLength={120}
            aria-label={t("character.group.namePlaceholder")}
            data-testid="character-group-name"
          />
          <button
            type="button"
            className="character-panel__btn"
            onClick={() => void handleSave()}
            disabled={saving || !name.trim() || nonProtagonistCount === 0}
            title={
              nonProtagonistCount === 0
                ? t("character.group.nothingToSave")
                : undefined
            }
            data-testid="character-group-save"
          >
            {saving
              ? t("character.group.saving")
              : t("character.group.saveCurrent")}
          </button>
        </div>
        {nonProtagonistCount === 0 && (
          <p className="character-cast__hint">
            {t("character.group.nothingToSave")}
          </p>
        )}
        {error && <div className="character-panel__error">{error}</div>}
        {notice && (
          <p className="character-cast__notice" role="status">
            {notice}
          </p>
        )}

        {loading ? (
          <p className="character-cast__note">{t("character.group.loading")}</p>
        ) : groups.length === 0 ? (
          <p className="character-cast__note">{t("character.group.empty")}</p>
        ) : (
          <ul className="character-group__list">
            {groups.map((group) => {
              const expanded = expandedId === group.id;
              return (
                <li
                  key={group.id}
                  className="character-group__row"
                  data-testid="character-group-row"
                >
                  <div className="character-group__row-main">
                    <button
                      type="button"
                      className="character-group__name"
                      aria-expanded={expanded}
                      onClick={() => setExpandedId(expanded ? null : group.id)}
                      title={
                        expanded
                          ? t("character.group.hideMembers")
                          : t("character.group.showMembers")
                      }
                    >
                      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
                      <span className="character-group__name-text">
                        {group.name}
                      </span>
                      <span className="character-panel__badge character-group__count">
                        {t("character.group.memberCount", {
                          count: group.members.length,
                        })}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="character-panel__btn"
                      onClick={() => void handleApply(group)}
                      disabled={busyId === group.id}
                      data-testid="character-group-apply"
                    >
                      {busyId === group.id
                        ? t("character.group.applying")
                        : t("character.group.apply")}
                    </button>
                    <button
                      type="button"
                      className="character-cast__icon-btn character-cast__icon-btn--delete"
                      onClick={() => void handleDelete(group)}
                      disabled={busyId === group.id}
                      aria-label={t("character.group.delete", {
                        name: group.name,
                      })}
                      title={t("character.group.delete", { name: group.name })}
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                    </button>
                  </div>
                  {expanded && (
                    <p className="character-group__members">
                      {group.members
                        .map((member) =>
                          member.on_stage
                            ? member.name
                            : `${member.name} (${t("character.group.offStage")})`,
                        )
                        .join(" / ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
