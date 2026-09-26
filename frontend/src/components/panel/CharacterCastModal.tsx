/**
 * CharacterCastModal - 登場人物の設定モーダル。
 *
 * 左に登場人物の一覧（登場 ON/OFF・追加）、右に選んだ人物の姿と性格を置く。
 * 姿はセッション・お気に入り・Prompt Expander から選べる（開始セッションと同じピッカー）。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { resolveCharacterSource } from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { SessionCharacter } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import {
  countOnStage,
  getStageLimit,
  MAX_REGISTERED_CHARACTERS,
  overflowCharacterIds,
  sortRoster,
} from "../../utils/characterStage";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
} from "../adventure/AdventureSessionPickerModal";
import CastToggle from "./CastToggle";
import CharacterDetailEditor from "./CharacterDetailEditor";
import CharacterPresetPicker from "./CharacterPresetPicker";
import "./CharacterPanel.css";
import "./CharacterCastModal.css";

interface CharacterCastModalProps {
  onClose: () => void;
  /** 開いたときに選択しておく人物 */
  initialCharacterId?: string | null;
}

export default function CharacterCastModal({
  onClose,
  initialCharacterId = null,
}: CharacterCastModalProps) {
  const { t } = useTranslation();
  const { state, addSessionCharacter, updateSessionCharacterAction } =
    useGame();
  const {
    state: settingsState,
    selfProfile,
    isNovelaiV5Active,
  } = useSettings();

  const characters = useMemo(
    () => sortRoster(state.sessionCharacters),
    [state.sessionCharacters],
  );
  const stageLimit = getStageLimit(isNovelaiV5Active);
  const onStageCount = countOnStage(characters);
  const stageLimitReached = onStageCount >= stageLimit;
  const overflowIds = useMemo(
    () => overflowCharacterIds(characters, stageLimit),
    [characters, stageLimit],
  );
  const nonProtagonistCount = characters.filter(
    (c) => !c.is_protagonist,
  ).length;
  const registeredFull = nonProtagonistCount >= MAX_REGISTERED_CHARACTERS - 1;

  const [selectedId, setSelectedId] = useState<string | null>(
    initialCharacterId,
  );
  // 選択中の人物が消えた（削除・組み合わせの入れ替え）ら先頭へ戻す
  const selected =
    characters.find((c) => c.id === selectedId) ?? characters[0] ?? null;

  const [appearancePickerOpen, setAppearancePickerOpen] = useState(false);
  const [presetPickerOpen, setPresetPickerOpen] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const childOpen = appearancePickerOpen || presetPickerOpen;

  // Esc で閉じる（子のピッカーを開いている間はそちらに任せる）
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !childOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [childOpen, onClose]);

  const displayNameOf = useCallback(
    (character: SessionCharacter) =>
      character.is_protagonist && state.selfMode && selfProfile?.display_name
        ? selfProfile.display_name
        : character.name,
    [state.selfMode, selfProfile?.display_name],
  );

  const errorMessage = (err: unknown): string => {
    const message = err instanceof Error ? err.message : "error";
    return message === "character_limit_exceeded"
      ? t("character.error.limit_exceeded", { max: MAX_REGISTERED_CHARACTERS })
      : message;
  };

  const handleAdd = async () => {
    setAdding(true);
    setError(null);
    try {
      const created = await addSessionCharacter({
        name: t("character.cast.newName", { number: nonProtagonistCount + 1 }),
        on_stage: !stageLimitReached,
      });
      setSelectedId(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAdding(false);
    }
  };

  const handleToggleStage = (character: SessionCharacter, next: boolean) => {
    setError(null);
    void updateSessionCharacterAction(character.id, { on_stage: next }).catch(
      (err) => setError(errorMessage(err)),
    );
  };

  const handleAppearanceSelected = async (
    selection: AdventureSourceSelection,
  ) => {
    setAppearancePickerOpen(false);
    if (!selected) return;
    const target = selected;
    setResolving(true);
    setResolveError(null);
    try {
      const resolved = await resolveCharacterSource(
        selection.origin === "prompt_expander" &&
          selection.promptExpanderEntryId
          ? { prompt_expander_entry_id: selection.promptExpanderEntryId }
          : {
              session_id: selection.sessionId,
              ...(selection.historyId
                ? { history_id: selection.historyId }
                : {}),
            },
      );
      const hasAppearance =
        target.appearance_tags.trim() || target.appearance_natural.trim();
      if (
        hasAppearance &&
        !window.confirm(t("character.cast.overwriteAppearanceConfirm"))
      ) {
        return;
      }
      // 「人物3」のような仮の名前のままなら、ソースの名前に置き換える
      const numbered = target.name.match(/(\d+)$/);
      const placeholderName =
        !!numbered &&
        target.name ===
          t("character.cast.newName", { number: Number(numbered[1]) });
      await updateSessionCharacterAction(target.id, {
        appearance_tags: resolved.appearance_tags,
        appearance_natural: resolved.appearance_natural,
        ...(selection.thumbnailUrl
          ? { thumbnail_url: selection.thumbnailUrl }
          : {}),
        ...(resolved.name && placeholderName && !target.is_protagonist
          ? { name: resolved.name }
          : {}),
      });
    } catch (err) {
      console.error("Failed to resolve character appearance", err);
      setResolveError(t("character.cast.resolveError"));
    } finally {
      setResolving(false);
    }
  };

  const panelEnabled = settingsState.multiCharacterPanelEnabled;

  return (
    <div
      className="character-cast"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !childOpen) onClose();
      }}
    >
      <section
        className="character-cast__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="character-cast-title"
        data-testid="character-cast-modal"
      >
        <header className="character-cast__header">
          <h2 id="character-cast-title">{t("character.cast.title")}</h2>
          <span className="character-cast__counter">
            {t("character.cast.registeredCount", {
              count: nonProtagonistCount + 1,
              max: MAX_REGISTERED_CHARACTERS,
            })}
          </span>
          <span
            className={`character-cast__counter${
              onStageCount > stageLimit ? " character-cast__counter--over" : ""
            }`}
          >
            {t("character.panel.onStageCount", {
              count: onStageCount,
              limit: stageLimit,
            })}
          </span>
          <button
            type="button"
            className="character-cast__close"
            aria-label={t("character.panel.close")}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        {!panelEnabled && (
          <p className="character-cast__warning">
            {t("character.panel.disabledNote")}
          </p>
        )}
        {onStageCount > stageLimit && (
          <p className="character-cast__warning">
            {t("character.panel.overLimit", { limit: stageLimit })}
          </p>
        )}
        {error && <div className="character-panel__error">{error}</div>}

        <div className="character-cast__body">
          <aside className="character-cast__list-column">
            <ul className="character-cast__list">
              {characters.map((character) => {
                const isSelected = selected?.id === character.id;
                const turnOnBlocked = !character.on_stage && stageLimitReached;
                return (
                  <li
                    key={character.id}
                    className={`character-cast__item${
                      isSelected ? " character-cast__item--selected" : ""
                    }${
                      !character.is_protagonist && !character.on_stage
                        ? " character-cast__item--off"
                        : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="character-cast__item-main"
                      onClick={() => setSelectedId(character.id)}
                      aria-current={isSelected ? "true" : undefined}
                      data-testid="character-cast-item"
                    >
                      <span className="character-cast__thumb">
                        {character.thumbnail_url ? (
                          <img src={mediaUrl(character.thumbnail_url)} alt="" />
                        ) : (
                          <span aria-hidden="true">
                            {displayNameOf(character).slice(0, 1)}
                          </span>
                        )}
                      </span>
                      <span className="character-cast__item-name">
                        {displayNameOf(character)}
                      </span>
                      {character.is_protagonist && (
                        <span className="character-panel__badge character-panel__badge--protagonist">
                          {t("character.panel.protagonist_badge")}
                        </span>
                      )}
                      {overflowIds.has(character.id) && (
                        <span
                          className="character-panel__badge character-panel__badge--warn"
                          title={t("character.panel.notUsed", {
                            limit: stageLimit,
                          })}
                        >
                          {t("character.badge.not_used_short")}
                        </span>
                      )}
                    </button>
                    <CastToggle
                      checked={character.is_protagonist || character.on_stage}
                      disabled={character.is_protagonist || turnOnBlocked}
                      title={
                        character.is_protagonist
                          ? t("character.panel.alwaysOnStage")
                          : turnOnBlocked
                            ? t("character.panel.onStageLimitReached", {
                                limit: stageLimit,
                              })
                            : undefined
                      }
                      label={t("character.field.on_stage_of", {
                        name: displayNameOf(character),
                      })}
                      onChange={(next) => handleToggleStage(character, next)}
                      testId="character-cast-on-stage"
                    />
                  </li>
                );
              })}
            </ul>
            <div className="character-cast__list-actions">
              <button
                type="button"
                className="character-panel__btn"
                onClick={() => void handleAdd()}
                disabled={adding || registeredFull}
                title={
                  registeredFull
                    ? t("character.error.limit_exceeded", {
                        max: MAX_REGISTERED_CHARACTERS,
                      })
                    : undefined
                }
                data-testid="character-add-button"
              >
                {adding ? t("character.panel.adding") : t("character.cast.add")}
              </button>
              <button
                type="button"
                className="character-panel__btn"
                onClick={() => setPresetPickerOpen(true)}
                disabled={registeredFull}
                data-testid="character-apply-preset-button"
              >
                {t("character.cast.addFromPreset")}
              </button>
            </div>
          </aside>

          <div className="character-cast__detail-column">
            {selected ? (
              <CharacterDetailEditor
                key={selected.id}
                character={selected}
                displayName={displayNameOf(selected)}
                stageLimitReached={stageLimitReached}
                stageLimit={stageLimit}
                overflow={overflowIds.has(selected.id)}
                onPickAppearance={() => {
                  setResolveError(null);
                  setAppearancePickerOpen(true);
                }}
                resolvingAppearance={resolving}
                resolveError={resolveError}
              />
            ) : (
              <p className="character-cast__note">
                {t("character.panel.empty")}
              </p>
            )}
          </div>
        </div>
      </section>

      {appearancePickerOpen && selected && (
        <AdventureSessionPickerModal
          title={t("character.cast.pickerTitle", {
            name: displayNameOf(selected),
          })}
          selected={null}
          onSelect={(selection) => void handleAppearanceSelected(selection)}
          onClose={() => setAppearancePickerOpen(false)}
          allowPromptExpander={settingsState.experimentalPromptExpanderEnabled}
        />
      )}
      <CharacterPresetPicker
        open={presetPickerOpen}
        onClose={() => setPresetPickerOpen(false)}
        onStage={!stageLimitReached}
        onApplied={(created) => setSelectedId(created.id)}
      />
    </div>
  );
}
