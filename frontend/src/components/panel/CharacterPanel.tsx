/**
 * CharacterPanel - 005 multi-character persistence
 *
 * Displays the persisted session_character roster, allows add/edit/delete,
 * and shows position assignments. Only rendered when
 * SettingsContext.enableMultiplePeople is true.
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createCharacterPreset,
  listCharacterPresets,
  updateCharacterPreset,
} from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
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

// ---------------------------------------------------------------------------
// CharacterEditForm
// IME 変換が途切れないよう、入力値はローカル state で管理し
// onBlur 時のみ GameContext (API) へ永続化する。
// ---------------------------------------------------------------------------
interface CharacterEditFormProps {
  character: SessionCharacter;
  onPersist: (
    id: string,
    patch: Partial<
      Pick<
        SessionCharacter,
        | "name"
        | "appearance_natural"
        | "appearance_tags"
        | "appearance_lock"
        | "exclude_from_effects"
      >
    >,
  ) => Promise<void>;
  onSavePreset: (character: SessionCharacter) => void;
  savingPresetId: string | null;
}

const CharacterEditForm = memo(function CharacterEditForm({
  character,
  onPersist,
  onSavePreset,
  savingPresetId,
}: CharacterEditFormProps) {
  const { t } = useTranslation();

  // character.id が変わると親側の key={character.id} によってコンポーネントが
  // 再マウントされるため、useState の初期値が正しく再設定される。
  const [name, setName] = useState(character.name);
  const [naturalText, setNaturalText] = useState(
    character.appearance_natural ?? "",
  );
  const [tags, setTags] = useState(character.appearance_tags ?? "");

  // 各フィールドの保存状態。フォーカスを外した（or チェックボックス変更）時点で
  // バックエンドへ非同期保存されるため、ユーザーに保存有無を視覚的に伝える。
  type SaveStatus = "saved" | "saving" | "dirty" | "error";
  type FieldKey =
    | "appearance_natural"
    | "appearance_tags"
    | "appearance_lock"
    | "exclude_from_effects";
  const [saveStatus, setSaveStatus] = useState<Record<FieldKey, SaveStatus>>({
    appearance_natural: "saved",
    appearance_tags: "saved",
    appearance_lock: "saved",
    exclude_from_effects: "saved",
  });
  const setFieldStatus = useCallback((field: FieldKey, status: SaveStatus) => {
    setSaveStatus((prev) =>
      prev[field] === status ? prev : { ...prev, [field]: status },
    );
  }, []);

  // 再生成や履歴削除によりレコードの値が外部から更新された際、入力欄へ反映させる。
  // 直前に同期した値を ref で保持し、ユーザーが編集中（ローカル値が直前の prop と異なる）
  // の場合は上書きしないようにする。
  const lastSyncedRef = useRef({
    name: character.name,
    natural: character.appearance_natural ?? "",
    tags: character.appearance_tags ?? "",
  });
  useEffect(() => {
    const nextName = character.name;
    const nextNatural = character.appearance_natural ?? "";
    const nextTags = character.appearance_tags ?? "";
    const synced = lastSyncedRef.current;
    if (nextName !== synced.name) {
      // ユーザー編集中（local が直前 prop と一致しない）でなければ取り込む
      setName((prev) => (prev === synced.name ? nextName : prev));
      synced.name = nextName;
    }
    if (nextNatural !== synced.natural) {
      setNaturalText((prev) => (prev === synced.natural ? nextNatural : prev));
      synced.natural = nextNatural;
    }
    if (nextTags !== synced.tags) {
      setTags((prev) => (prev === synced.tags ? nextTags : prev));
      synced.tags = nextTags;
    }
  }, [character.name, character.appearance_natural, character.appearance_tags]);

  const persistField = useCallback(
    async (
      field: FieldKey,
      patch: Partial<
        Pick<
          SessionCharacter,
          | "appearance_natural"
          | "appearance_tags"
          | "appearance_lock"
          | "exclude_from_effects"
        >
      >,
    ) => {
      setFieldStatus(field, "saving");
      try {
        await onPersist(character.id, patch);
        setFieldStatus(field, "saved");
      } catch (err) {
        console.error("Failed to persist character field", field, err);
        setFieldStatus(field, "error");
      }
    },
    [character.id, onPersist, setFieldStatus],
  );

  const persistName = () => {
    if (name !== character.name) void onPersist(character.id, { name });
  };
  const persistNatural = () => {
    if (naturalText !== (character.appearance_natural ?? "")) {
      void persistField("appearance_natural", {
        appearance_natural: naturalText,
      });
    } else {
      // 値が変わっていなければ未保存状態を解消する
      setFieldStatus("appearance_natural", "saved");
    }
  };
  const persistTags = () => {
    if (tags !== (character.appearance_tags ?? "")) {
      void persistField("appearance_tags", { appearance_tags: tags });
    } else {
      setFieldStatus("appearance_tags", "saved");
    }
  };

  const statusLabel = (status: SaveStatus): string => {
    if (status === "saving")
      return t("character.save_status.saving", "保存中…");
    if (status === "dirty") return t("character.save_status.dirty", "未保存");
    if (status === "error") return t("character.save_status.error", "保存失敗");
    return t("character.save_status.saved", "保存済み");
  };
  const statusIcon = (status: SaveStatus): string => {
    if (status === "saving") return "…";
    if (status === "dirty") return "●";
    if (status === "error") return "!";
    return "✓";
  };
  const renderSaveStatus = (field: FieldKey) => {
    const status = saveStatus[field];
    const label = statusLabel(status);
    return (
      <span
        className={`character-panel__save-status character-panel__save-status--${status}`}
        role="status"
        aria-live="polite"
        aria-label={label}
        title={label}
        data-testid={`character-save-status-${field}`}
      >
        <span className="character-panel__save-status-icon" aria-hidden="true">
          {statusIcon(status)}
        </span>
      </span>
    );
  };

  return (
    <div className="character-panel__row-edit">
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={persistName}
        placeholder={t("character.field.name", "名前")}
      />
      <div className="character-panel__field">
        <textarea
          value={naturalText}
          onChange={(e) => {
            setNaturalText(e.target.value);
            setFieldStatus(
              "appearance_natural",
              e.target.value === (character.appearance_natural ?? "")
                ? "saved"
                : "dirty",
            );
          }}
          onBlur={persistNatural}
          placeholder={t(
            "character.field.appearance_natural",
            "外見（自然文）",
          )}
        />
        {renderSaveStatus("appearance_natural")}
      </div>
      <div className="character-panel__field">
        <textarea
          value={tags}
          onChange={(e) => {
            setTags(e.target.value);
            setFieldStatus(
              "appearance_tags",
              e.target.value === (character.appearance_tags ?? "")
                ? "saved"
                : "dirty",
            );
          }}
          onBlur={persistTags}
          placeholder={t(
            "character.field.appearance_tags",
            "外見タグ (NovelAI 形式)",
          )}
        />
        {renderSaveStatus("appearance_tags")}
      </div>
      <label className="character-panel__check">
        <input
          type="checkbox"
          checked={character.appearance_lock}
          onChange={(e) =>
            void persistField("appearance_lock", {
              appearance_lock: e.target.checked,
            })
          }
          data-testid="character-appearance-lock"
        />
        <span>
          {t(
            "character.field.appearance_lock",
            "外見ロック（結果で上書きしない）",
          )}
        </span>
        {renderSaveStatus("appearance_lock")}
      </label>
      <label className="character-panel__check">
        <input
          type="checkbox"
          checked={character.exclude_from_effects}
          onChange={(e) =>
            void persistField("exclude_from_effects", {
              exclude_from_effects: e.target.checked,
            })
          }
          data-testid="character-exclude-from-effects"
        />
        <span>
          {t(
            "character.field.exclude_from_effects",
            "効果対象外（指示の影響を受けない）",
          )}
        </span>
        {renderSaveStatus("exclude_from_effects")}
      </label>
      <button
        type="button"
        className="character-panel__btn"
        onClick={() => void onSavePreset(character)}
        disabled={savingPresetId === character.id}
        data-testid="character-save-preset-button"
      >
        {savingPresetId === character.id
          ? t("character.preset.saving", "保存中…")
          : t("character.preset.save", "プリセット保存")}
      </button>
    </div>
  );
});

// ---------------------------------------------------------------------------
// CharacterAddForm
// draft の更新でキャラクターリスト全体が再レンダリングされないよう分離する。
// ---------------------------------------------------------------------------
interface NewCharacterDraft {
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  position: CharacterPosition;
  appearance_lock: boolean;
  exclude_from_effects: boolean;
}

const emptyDraft: NewCharacterDraft = {
  name: "",
  appearance_natural: "",
  appearance_tags: "",
  position: "center",
  appearance_lock: false,
  exclude_from_effects: false,
};

interface CharacterAddFormProps {
  onAdd: (draft: NewCharacterDraft) => Promise<void>;
  disabled: boolean;
}

const CharacterAddForm = memo(function CharacterAddForm({
  onAdd,
  disabled,
}: CharacterAddFormProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<NewCharacterDraft>(emptyDraft);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    setError(null);
    if (!draft.name.trim()) {
      setError(t("character.error.name_required", "名前を入力してください"));
      return;
    }
    setIsAdding(true);
    try {
      await onAdd(draft);
      setDraft(emptyDraft);
    } catch (err) {
      const message = err instanceof Error ? err.message : "error";
      setError(
        message === "character_limit_exceeded"
          ? t("character.error.limit_exceeded", "登場人物は最大4人までです")
          : message,
      );
    } finally {
      setIsAdding(false);
    }
  };

  return (
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
        placeholder={t("character.field.appearance_natural", "外見（自然文）")}
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
      <label className="character-panel__check">
        <input
          type="checkbox"
          checked={draft.appearance_lock}
          onChange={(e) =>
            setDraft((prev) => ({
              ...prev,
              appearance_lock: e.target.checked,
            }))
          }
        />
        <span>
          {t(
            "character.field.appearance_lock",
            "外見ロック（結果で上書きしない）",
          )}
        </span>
      </label>
      <label className="character-panel__check">
        <input
          type="checkbox"
          checked={draft.exclude_from_effects}
          onChange={(e) =>
            setDraft((prev) => ({
              ...prev,
              exclude_from_effects: e.target.checked,
            }))
          }
        />
        <span>
          {t(
            "character.field.exclude_from_effects",
            "効果対象外（指示の影響を受けない）",
          )}
        </span>
      </label>
      {error && <div className="character-panel__error">{error}</div>}
      <button
        type="button"
        className="character-panel__btn"
        disabled={isAdding || disabled}
        onClick={() => void handleCreate()}
        data-testid="character-add-button"
      >
        {isAdding
          ? t("character.panel.adding", "追加中…")
          : t("character.panel.add", "追加")}
      </button>
    </div>
  );
});

// ---------------------------------------------------------------------------
// CharacterPanel (main)
// ---------------------------------------------------------------------------
export default function CharacterPanel() {
  const { t } = useTranslation();
  const {
    state,
    loadSessionCharacters,
    addSessionCharacter,
    updateSessionCharacterAction,
    removeSessionCharacter,
  } = useGame();
  const {
    selfProfile,
    state: settingsState,
    setMultiCharacterPanelEnabled,
  } = useSettings();
  const panelEnabled = settingsState.multiCharacterPanelEnabled;

  const [editingId, setEditingId] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [savingPresetId, setSavingPresetId] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => {
    if (state.sessionId) {
      void loadSessionCharacters();
    }
  }, [state.sessionId, loadSessionCharacters]);

  const characters: SessionCharacter[] = useMemo(
    () =>
      [...state.sessionCharacters].sort((a, b) => {
        if (a.is_protagonist && !b.is_protagonist) return -1;
        if (!a.is_protagonist && b.is_protagonist) return 1;
        return a.slot_index - b.slot_index;
      }),
    [state.sessionCharacters],
  );

  const nonProtagonistCount = characters.filter(
    (c) => !c.is_protagonist,
  ).length;
  const reachedLimit = nonProtagonistCount >= CHARACTER_LIMIT;

  const handleAdd = useCallback(
    async (draft: NewCharacterDraft) => {
      await addSessionCharacter({
        name: draft.name.trim(),
        appearance_natural: draft.appearance_natural,
        appearance_tags: draft.appearance_tags,
        position: draft.position,
        appearance_lock: draft.appearance_lock,
        exclude_from_effects: draft.exclude_from_effects,
      });
    },
    [addSessionCharacter],
  );

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
    const trimmedName = presetName.trim();
    setSavingPresetId(character.id);
    setListError(null);
    try {
      const existing = await listCharacterPresets();
      const duplicate = existing.find((p) => p.name === trimmedName);
      if (duplicate) {
        const ok = window.confirm(
          t(
            "character.preset.overwrite_confirm",
            "「{{name}}」という名前のプリセットが既に存在します。上書きしますか？",
            { name: trimmedName },
          ),
        );
        if (!ok) return;
        await updateCharacterPreset(duplicate.id, {
          appearance_natural: character.appearance_natural ?? undefined,
          appearance_tags: character.appearance_tags ?? undefined,
          default_position: character.position,
        });
      } else {
        await createCharacterPreset({
          from_character_id: character.id,
          name: trimmedName,
        });
      }
    } catch (err) {
      setListError(err instanceof Error ? err.message : "error");
    } finally {
      setSavingPresetId(null);
    }
  };

  const handlePersistCharacter = useCallback(
    async (
      id: string,
      patch: Partial<
        Pick<
          SessionCharacter,
          | "name"
          | "appearance_natural"
          | "appearance_tags"
          | "appearance_lock"
          | "exclude_from_effects"
        >
      >,
    ) => {
      await updateSessionCharacterAction(id, patch);
    },
    [updateSessionCharacterAction],
  );

  if (!state.sessionId) {
    return null;
  }

  return (
    <div className="character-panel" data-testid="character-panel">
      <div className="character-panel__header">
        <div className="character-panel__title-row">
          <span className="character-panel__title">
            {t("character.panel.title", "登場人物")}
          </span>
          <span
            className="feature-chip-experimental"
            data-feature-version="v0.5.0"
          >
            Experimental
          </span>
        </div>
        <p className="character-panel__description">
          {t(
            "character.panel.description",
            "ここで登録した登場人物の情報は、画像生成時のプロンプトにのみ反映されます（チャット応答の内容には反映されません）。",
          )}
        </p>
        <div className="character-panel__controls">
          <label
            className="character-panel__feature-toggle"
            title={t(
              "character.panel.featureToggleHint",
              "OFFにすると、複数人表示自体はそのまま保ちつつ、このパネルの登場人物情報を画像プロンプトへ注入しなくなります（v0.5.0 以前の旧仕様・不安定ながら動作していた複数人表示の振る舞いに戻る）。",
            )}
          >
            <input
              type="checkbox"
              checked={panelEnabled}
              onChange={(e) => setMultiCharacterPanelEnabled(e.target.checked)}
              data-testid="character-panel-feature-toggle"
            />
            <span>{t("character.panel.featureToggle", "有効")}</span>
          </label>
          <span className="character-panel__count">
            {nonProtagonistCount} / {CHARACTER_LIMIT}
          </span>
          <button
            type="button"
            className="character-panel__btn"
            onClick={() => setPickerOpen(true)}
            disabled={reachedLimit || !panelEnabled}
            data-testid="character-apply-preset-button"
          >
            {t("character.preset.apply_button", "プリセット")}
          </button>
        </div>
      </div>

      <div
        className={
          panelEnabled
            ? "character-panel__body"
            : "character-panel__body character-panel__body--disabled"
        }
        aria-disabled={!panelEnabled}
      >
        {listError && <div className="character-panel__error">{listError}</div>}

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
                    {character.is_protagonist
                      ? t("character.panel.protagonist_badge", "主人公")
                      : `${character.slot_index + 1}.`}
                  </span>
                  <span
                    className="character-panel__name"
                    title={character.appearance_natural || character.name}
                  >
                    {character.is_protagonist &&
                    state.selfMode &&
                    selfProfile?.display_name
                      ? selfProfile.display_name
                      : character.name}
                  </span>
                  {character.appearance_lock && (
                    <span
                      className="character-panel__badge character-panel__badge--lock"
                      title={t(
                        "character.badge.appearance_lock",
                        "外見ロック中：結果で上書きされません",
                      )}
                    >
                      {t("character.badge.lock_short", "ロック")}
                    </span>
                  )}
                  {character.exclude_from_effects && (
                    <span
                      className="character-panel__badge character-panel__badge--bystander"
                      title={t(
                        "character.badge.exclude_from_effects",
                        "効果対象外：指示の影響を受けません",
                      )}
                    >
                      {t("character.badge.bystander_short", "対象外")}
                    </span>
                  )}
                  {!character.is_protagonist && (
                    <button
                      type="button"
                      className="character-panel__btn character-panel__btn--danger"
                      onClick={() => void handleDelete(character)}
                    >
                      {t("character.panel.delete", "削除")}
                    </button>
                  )}
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
                  <CharacterEditForm
                    key={character.id}
                    character={character}
                    onPersist={handlePersistCharacter}
                    onSavePreset={handleSaveAsPreset}
                    savingPresetId={savingPresetId}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {!reachedLimit && (
          <CharacterAddForm onAdd={handleAdd} disabled={reachedLimit} />
        )}

        <CharacterPresetPicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
        />
      </div>
    </div>
  );
}
