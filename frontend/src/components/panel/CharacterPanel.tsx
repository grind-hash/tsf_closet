/**
 * CharacterPanel - 005 multi-character persistence
 *
 * 登録済みの登場人物を一覧で見せ、登場 ON/OFF を切り替える要約パネル。
 * 姿・性格の編集は「登場人物の設定」モーダル、組み合わせの保存と呼び出しは
 * 「組み合わせ」モーダルで行う。SettingsContext.enableMultiplePeople が true のときだけ出す。
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { SessionCharacter } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import {
  countOnStage,
  getStageLimit,
  hasLookChanged,
  overflowCharacterIds,
  sortRoster,
} from "../../utils/characterStage";
import CastToggle from "./CastToggle";
import CharacterCastModal from "./CharacterCastModal";
import CharacterGroupPresetModal from "./CharacterGroupPresetModal";
import "./CharacterPanel.css";

export default function CharacterPanel() {
  const { t } = useTranslation();
  const { state, loadSessionCharacters, updateSessionCharacterAction } =
    useGame();
  const {
    selfProfile,
    state: settingsState,
    setMultiCharacterPanelEnabled,
    isNovelaiV5Active,
  } = useSettings();
  const panelEnabled = settingsState.multiCharacterPanelEnabled;

  const [castOpen, setCastOpen] = useState(false);
  const [castInitialId, setCastInitialId] = useState<string | null>(null);
  const [groupOpen, setGroupOpen] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => {
    if (state.sessionId) {
      void loadSessionCharacters();
    }
  }, [state.sessionId, loadSessionCharacters]);

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
  const hasProtagonist = characters.some((c) => c.is_protagonist);

  const displayNameOf = (character: SessionCharacter) =>
    character.is_protagonist && state.selfMode && selfProfile?.display_name
      ? selfProfile.display_name
      : character.name;

  const openCast = (characterId: string | null) => {
    setCastInitialId(characterId);
    setCastOpen(true);
  };

  const handleToggleStage = (character: SessionCharacter, next: boolean) => {
    setListError(null);
    void updateSessionCharacterAction(character.id, { on_stage: next }).catch(
      (err) => setListError(err instanceof Error ? err.message : "error"),
    );
  };

  if (!state.sessionId) {
    return null;
  }

  return (
    <div className="character-panel" data-testid="character-panel">
      <div className="character-panel__header">
        <div className="character-panel__title-row">
          <span className="character-panel__title">
            {t("character.panel.title")}
          </span>
          <span
            className="feature-chip-experimental"
            data-feature-version="v0.5.0"
          >
            Experimental
          </span>
          <span className="character-panel__feature-toggle">
            <CastToggle
              checked={panelEnabled}
              onChange={setMultiCharacterPanelEnabled}
              label={t("character.panel.featureToggle")}
              showLabel
              title={t("character.panel.featureToggleHint")}
              testId="character-panel-feature-toggle"
            />
          </span>
        </div>
        <p className="character-panel__description">
          {t("character.panel.description")}
        </p>
        {!panelEnabled && (
          <p className="character-panel__note">
            {t("character.panel.disabledNote")}
          </p>
        )}
        <div className="character-panel__controls">
          <button
            type="button"
            className="character-panel__btn"
            onClick={() => openCast(null)}
            data-testid="character-open-cast"
          >
            {t("character.panel.editCast")}
          </button>
          <button
            type="button"
            className="character-panel__btn"
            onClick={() => setGroupOpen(true)}
            data-testid="character-open-groups"
          >
            {t("character.panel.groups")}
          </button>
          <span
            className={`character-panel__count${
              onStageCount > stageLimit ? " character-panel__count--over" : ""
            }`}
            data-testid="character-on-stage-count"
          >
            {t("character.panel.onStageCount", {
              count: onStageCount,
              limit: stageLimit,
            })}
          </span>
        </div>
        {onStageCount > stageLimit && (
          <p className="character-panel__warning" role="status">
            {t("character.panel.overLimit", { limit: stageLimit })}
          </p>
        )}
      </div>

      <div className="character-panel__body">
        {listError && <div className="character-panel__error">{listError}</div>}

        {characters.length === 0 ? (
          <div className="character-panel__empty">
            {t("character.panel.empty")}
          </div>
        ) : (
          <ul className="character-panel__list">
            {characters.map((character, index) => {
              const turnOnBlocked = !character.on_stage && stageLimitReached;
              // 主人公以外は 1 から数える（主人公は先頭に並ぶ）
              const number = hasProtagonist ? index : index + 1;
              const off = !character.is_protagonist && !character.on_stage;
              return (
                <li
                  key={character.id}
                  className={`character-panel__row${
                    off ? " character-panel__row--off" : ""
                  }`}
                  data-testid="character-row"
                >
                  <span className="character-panel__slot">
                    {character.is_protagonist
                      ? t("character.panel.protagonist_badge")
                      : `${number}.`}
                  </span>
                  <button
                    type="button"
                    className="character-panel__row-main"
                    onClick={() => openCast(character.id)}
                    title={t("character.panel.editOne", {
                      name: displayNameOf(character),
                    })}
                  >
                    <span className="character-panel__thumb">
                      {character.thumbnail_url ? (
                        <img src={mediaUrl(character.thumbnail_url)} alt="" />
                      ) : (
                        <span aria-hidden="true">
                          {displayNameOf(character).slice(0, 1)}
                        </span>
                      )}
                    </span>
                    <span className="character-panel__name">
                      {displayNameOf(character)}
                    </span>
                    {character.appearance_lock && (
                      <span
                        className="character-panel__badge character-panel__badge--lock"
                        title={t("character.badge.appearance_lock")}
                      >
                        {t("character.badge.lock_short")}
                      </span>
                    )}
                    {character.exclude_from_effects && (
                      <span
                        className="character-panel__badge character-panel__badge--bystander"
                        title={t("character.badge.exclude_from_effects")}
                      >
                        {t("character.badge.bystander_short")}
                      </span>
                    )}
                    {character.profile && !character.is_protagonist && (
                      <span
                        className="character-panel__badge character-panel__badge--profile"
                        title={t("character.badge.profile")}
                      >
                        {t("character.badge.profile_short")}
                      </span>
                    )}
                    {hasLookChanged(character) && (
                      <span
                        className="character-panel__badge character-panel__badge--changed"
                        title={t("character.badge.look_changed")}
                        data-testid="character-look-changed"
                      >
                        {t("character.badge.look_changed_short")}
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
                    testId="character-row-on-stage"
                  />
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {castOpen && (
        <CharacterCastModal
          initialCharacterId={castInitialId}
          onClose={() => setCastOpen(false)}
        />
      )}
      {groupOpen && (
        <CharacterGroupPresetModal onClose={() => setGroupOpen(false)} />
      )}
    </div>
  );
}
