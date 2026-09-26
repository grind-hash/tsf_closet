/**
 * CharacterDetailEditor - 登場人物の設定モーダルの右側。1 人分の姿と性格を編集する。
 *
 * 「姿の設定」はユーザーが書く入力で、手番の結果で書き換わることはない。
 * 手番で描いた姿は履歴に残り、「現在の姿」に読み取り専用で出す。
 *
 * テキスト欄は IME 変換が途切れないよう入力値をローカルに持ち、blur 時に保存する。
 * 人物の切り替えやモーダルを閉じたとき（アンマウント時）も未保存の入力を保存する。
 */

import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  createCharacterPreset,
  generateCharacterProfile,
  generateCharacterTags,
  listCharacterPresets,
  updateCharacterPreset,
} from "../../apis/characters";
import { useGame } from "../../contexts/GameContext";
import type {
  CharacterPosition,
  CharacterProfile,
  SessionCharacter,
} from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import ProfileFields, {
  type ProfileFieldsValue,
} from "../settings/ProfileFields";
import CastToggle from "./CastToggle";

export const CHARACTER_POSITIONS: CharacterPosition[] = [
  "left",
  "center-left",
  "center",
  "center-right",
  "right",
];

const EMPTY_PROFILE: CharacterProfile = {
  personality: "",
  reaction_style: "default",
  pronoun: "",
  gender: "",
  interests: [],
  tsf_attitude: "",
  memo: "",
};

type SaveStatus = "saved" | "saving" | "dirty" | "error";

// ---------------------------------------------------------------------------
// 保存状態の表示
// ---------------------------------------------------------------------------

function SaveStatusIcon({ status }: { status: SaveStatus }) {
  const { t } = useTranslation();
  const label = t(`character.save_status.${status}`);
  const icon =
    status === "saving"
      ? "…"
      : status === "dirty"
        ? "●"
        : status === "error"
          ? "!"
          : "✓";
  return (
    <span
      className={`character-panel__save-status character-panel__save-status--${status}`}
      role="status"
      aria-live="polite"
      aria-label={label}
      title={label}
    >
      <span className="character-panel__save-status-icon" aria-hidden="true">
        {icon}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// テキスト欄（blur とアンマウントで保存）
// ---------------------------------------------------------------------------

interface SavedTextFieldProps {
  label: string;
  value: string;
  onSave: (next: string) => Promise<void>;
  multiline?: boolean;
  placeholder?: string;
  maxLength?: number;
  /** 欄の右上に置く操作 */
  action?: ReactNode;
  testId?: string;
  /** 入力中の値を親へ知らせる（保存前の下書きを使う操作のため） */
  onTextChange?: (text: string) => void;
}

function SavedTextField({
  label,
  value,
  onSave,
  multiline = false,
  placeholder,
  maxLength,
  action,
  testId,
  onTextChange,
}: SavedTextFieldProps) {
  const [text, setText] = useState(value);
  const [status, setStatus] = useState<SaveStatus>("saved");

  // 外から値が変わった（再生成・姿の選択など）とき、編集中でなければ取り込む
  const syncedRef = useRef(value);
  useEffect(() => {
    const synced = syncedRef.current;
    if (value !== synced) {
      setText((prev) => (prev === synced ? value : prev));
      syncedRef.current = value;
    }
  }, [value]);

  const textRef = useRef(text);
  textRef.current = text;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  const save = useCallback(async (next: string) => {
    setStatus("saving");
    try {
      await onSaveRef.current(next);
      setStatus("saved");
    } catch (err) {
      console.error("Failed to save character field", err);
      setStatus("error");
    }
  }, []);

  // 人物の切り替え・モーダルを閉じたときは blur が起きないため、ここで保存する
  useEffect(
    () => () => {
      if (textRef.current !== syncedRef.current) {
        void onSaveRef
          .current(textRef.current)
          .catch((err) =>
            console.error("Failed to flush character field", err),
          );
      }
    },
    [],
  );

  const handleBlur = () => {
    if (text !== syncedRef.current) {
      void save(text);
    } else {
      setStatus("saved");
    }
  };

  const handleChange = (next: string) => {
    setText(next);
    setStatus(next === syncedRef.current ? "saved" : "dirty");
    onTextChange?.(next);
  };

  return (
    <div className="character-cast__field">
      <div className="character-cast__field-head">
        <span className="character-cast__field-label">{label}</span>
        <SaveStatusIcon status={status} />
        {action && <div className="character-cast__field-action">{action}</div>}
      </div>
      {multiline ? (
        <textarea
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          maxLength={maxLength}
          aria-label={label}
          data-testid={testId}
        />
      ) : (
        <input
          type="text"
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          maxLength={maxLength}
          aria-label={label}
          data-testid={testId}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 開閉できるセクション（開閉状態は localStorage に保存）
// ---------------------------------------------------------------------------

const SECTION_STORAGE_KEY = "tsf.characterCast.sections";

function readSectionState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(SECTION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function CastSection({
  id,
  title,
  action,
  children,
}: {
  id: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(() => readSectionState()[id] ?? true);
  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(
          SECTION_STORAGE_KEY,
          JSON.stringify({ ...readSectionState(), [id]: next }),
        );
      } catch {
        // 保存できなくても開閉は続ける
      }
      return next;
    });
  };
  return (
    <section className="character-cast__section">
      <div className="character-cast__section-head">
        <button
          type="button"
          className="character-cast__section-toggle"
          aria-expanded={open}
          onClick={toggle}
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          {title}
        </button>
        {action && open && (
          <div className="character-cast__field-action">{action}</div>
        )}
      </div>
      {open && <div className="character-cast__section-body">{children}</div>}
    </section>
  );
}

// ---------------------------------------------------------------------------
// CharacterDetailEditor
// ---------------------------------------------------------------------------

interface CharacterDetailEditorProps {
  character: SessionCharacter;
  /** 一覧・見出しに出す名前（自分自身モードの主人公は表示名） */
  displayName: string;
  /** 登場 OFF の人物を ON にできない（上限に達している） */
  stageLimitReached: boolean;
  stageLimit: number;
  /** 上限を超えていて生成に使われない */
  overflow: boolean;
  /** 「姿を選ぶ」。ピッカーの開閉は親のモーダルが管理する */
  onPickAppearance: () => void;
  resolvingAppearance: boolean;
  resolveError: string | null;
}

export default function CharacterDetailEditor({
  character,
  displayName,
  stageLimitReached,
  stageLimit,
  overflow,
  onPickAppearance,
  resolvingAppearance,
  resolveError,
}: CharacterDetailEditorProps) {
  const { t } = useTranslation();
  const { updateSessionCharacterAction, removeSessionCharacter } = useGame();
  const [error, setError] = useState<string | null>(null);
  const [savingPreset, setSavingPreset] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generatingTags, setGeneratingTags] = useState(false);
  const [tagsError, setTagsError] = useState<string | null>(null);
  // 自然文を保存したのにタグが古いまま（画像にはタグを使うため注意を出す）
  const [naturalAheadOfTags, setNaturalAheadOfTags] = useState(false);
  const naturalDraftRef = useRef(character.appearance_natural);
  const [naturalFilled, setNaturalFilled] = useState(
    Boolean(character.appearance_natural.trim()),
  );
  useEffect(() => {
    // 姿を選んだときなど、保存済みの自然文が外から変わったら下書きも合わせる
    naturalDraftRef.current = character.appearance_natural;
    setNaturalFilled(Boolean(character.appearance_natural.trim()));
  }, [character.appearance_natural]);

  const persist = useCallback(
    async (patch: Parameters<typeof updateSessionCharacterAction>[1]) => {
      await updateSessionCharacterAction(character.id, patch);
    },
    [character.id, updateSessionCharacterAction],
  );

  const persistQuietly = (patch: Parameters<typeof persist>[0]) => {
    setError(null);
    void persist(patch).catch((err) => {
      console.error("Failed to update character", err);
      setError(t("character.save_status.error"));
    });
  };

  // ── 性格プロフィール（ローカル下書き＋確定時に保存） ──
  const savedProfile = character.profile ?? EMPTY_PROFILE;
  const savedProfileKey = JSON.stringify(savedProfile);
  const [profileDraft, setProfileDraft] =
    useState<CharacterProfile>(savedProfile);
  const profileDraftRef = useRef(profileDraft);
  profileDraftRef.current = profileDraft;
  const syncedProfileKeyRef = useRef(savedProfileKey);
  useEffect(() => {
    if (savedProfileKey === syncedProfileKeyRef.current) return;
    const previous = syncedProfileKeyRef.current;
    syncedProfileKeyRef.current = savedProfileKey;
    // 編集中（下書きが前回の保存値と違う）でなければ取り込む
    setProfileDraft((prev) =>
      JSON.stringify(prev) === previous
        ? (JSON.parse(savedProfileKey) as CharacterProfile)
        : prev,
    );
  }, [savedProfileKey]);

  const commitProfile = useCallback(
    (patch: Partial<CharacterProfile>) => {
      const next = { ...profileDraftRef.current, ...patch };
      if (JSON.stringify(next) === syncedProfileKeyRef.current) return;
      setError(null);
      void persist({ profile: next }).catch((err) => {
        console.error("Failed to save character profile", err);
        setError(t("character.save_status.error"));
      });
    },
    [persist, t],
  );

  // 閉じたときに未保存の性格を保存する
  useEffect(
    () => () => {
      const draft = profileDraftRef.current;
      if (JSON.stringify(draft) !== syncedProfileKeyRef.current) {
        void updateSessionCharacterAction(character.id, {
          profile: draft,
        }).catch((err) =>
          console.error("Failed to flush character profile", err),
        );
      }
    },
    [character.id, updateSessionCharacterAction],
  );

  const handleProfileChange = (patch: Partial<ProfileFieldsValue>) => {
    setProfileDraft((prev) => ({
      ...prev,
      ...(patch as Partial<CharacterProfile>),
    }));
  };

  const handleGenerateProfile = async () => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const generated = await generateCharacterProfile({
        name: character.name,
        appearance_natural: character.appearance_natural,
        appearance_tags: character.appearance_tags,
        memo: profileDraftRef.current.memo,
      });
      setProfileDraft(generated);
      commitProfile(generated);
    } catch (err) {
      console.error("Failed to generate character profile", err);
      setGenerateError(t("character.profile.generateError"));
    } finally {
      setGenerating(false);
    }
  };

  // ── 姿の設定: 自然文からタグを作る ──
  const handleGenerateTags = async () => {
    const natural = naturalDraftRef.current.trim();
    if (!natural) return;
    if (
      character.appearance_tags.trim() &&
      !window.confirm(t("character.cast.generateTagsConfirm"))
    ) {
      return;
    }
    setGeneratingTags(true);
    setTagsError(null);
    try {
      const [result] = await generateCharacterTags([
        { id: character.id, name: character.name, natural },
      ]);
      if (!result?.tags) {
        throw new Error("empty_tags");
      }
      await persist({ appearance_tags: result.tags });
      setNaturalAheadOfTags(false);
    } catch (err) {
      console.error("Failed to generate character tags", err);
      setTagsError(t("character.cast.generateTagsError"));
    } finally {
      setGeneratingTags(false);
    }
  };

  // ── 現在の姿: 設定にコピー・設定の姿に戻す ──
  const currentTags = character.current_tags ?? "";
  const lookSource = character.look_source ?? "spec";
  const handleCopyToSpec = () => {
    if (!currentTags) return;
    if (!window.confirm(t("character.cast.copyToSpecConfirm"))) return;
    persistQuietly({ appearance_tags: currentTags });
    setNaturalAheadOfTags(false);
  };
  const currentLookNote =
    lookSource === "fixed"
      ? t("character.cast.currentLookFixed")
      : lookSource === "history"
        ? t("character.cast.currentLookHistory")
        : currentTags
          ? t("character.cast.currentLookSpecNext")
          : t("character.cast.currentLookEmpty");

  // ── 削除・プリセット保存 ──
  const handleDelete = async () => {
    if (
      !window.confirm(t("character.confirm.delete", { name: character.name }))
    ) {
      return;
    }
    try {
      await removeSessionCharacter(character.id);
    } catch (err) {
      console.error("Failed to delete character", err);
      setError(err instanceof Error ? err.message : "error");
    }
  };

  const handleSavePreset = async () => {
    const presetName = window.prompt(
      t("character.preset.save_prompt"),
      character.name,
    );
    const trimmedName = presetName?.trim();
    if (!trimmedName) return;
    setSavingPreset(true);
    setError(null);
    try {
      const existing = await listCharacterPresets();
      const duplicate = existing.find((p) => p.name === trimmedName);
      if (duplicate) {
        const ok = window.confirm(
          t("character.preset.overwrite_confirm", { name: trimmedName }),
        );
        if (!ok) return;
        await updateCharacterPreset(duplicate.id, {
          appearance_natural: character.appearance_natural,
          appearance_tags: character.appearance_tags,
          default_position: character.position,
          negative_tags: character.negative_tags,
          ...(character.profile ? { profile: character.profile } : {}),
          ...(character.thumbnail_url
            ? { thumbnail_url: character.thumbnail_url }
            : {}),
        });
      } else {
        await createCharacterPreset({
          from_character_id: character.id,
          name: trimmedName,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setSavingPreset(false);
    }
  };

  const stageToggleDisabled =
    character.is_protagonist || (!character.on_stage && stageLimitReached);
  const stageToggleTitle = character.is_protagonist
    ? t("character.panel.alwaysOnStage")
    : !character.on_stage && stageLimitReached
      ? t("character.panel.onStageLimitReached", { limit: stageLimit })
      : undefined;

  return (
    <div className="character-cast__detail" data-testid="character-detail">
      <div className="character-cast__detail-head">
        <h3 className="character-cast__detail-name">{displayName}</h3>
        {character.is_protagonist && (
          <span className="character-panel__badge character-panel__badge--protagonist">
            {t("character.panel.protagonist_badge")}
          </span>
        )}
        <CastToggle
          checked={character.is_protagonist || character.on_stage}
          disabled={stageToggleDisabled}
          title={stageToggleTitle}
          label={t("character.field.on_stage")}
          showLabel
          onChange={(next) => persistQuietly({ on_stage: next })}
          testId="character-detail-on-stage"
        />
        {!character.is_protagonist && (
          <button
            type="button"
            className="character-cast__icon-btn character-cast__icon-btn--delete"
            onClick={() => void handleDelete()}
            aria-label={t("character.cast.deleteCharacter")}
            title={t("character.cast.deleteCharacter")}
            data-testid="character-detail-delete"
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
        )}
      </div>
      {overflow && (
        <p className="character-cast__warning">
          {t("character.panel.notUsed", { limit: stageLimit })}
        </p>
      )}
      {error && <div className="character-panel__error">{error}</div>}

      <CastSection
        id="appearance"
        title={t("character.cast.appearanceSection")}
        action={
          <button
            type="button"
            className="character-panel__btn"
            onClick={onPickAppearance}
            disabled={resolvingAppearance}
            data-testid="character-pick-appearance"
          >
            {resolvingAppearance ? (
              <>
                <span className="character-cast__spinner" aria-hidden="true" />
                {t("character.cast.resolving")}
              </>
            ) : (
              t("character.cast.pickAppearance")
            )}
          </button>
        }
      >
        <div className="character-cast__appearance-row">
          <div className="character-cast__thumb character-cast__thumb--large">
            {character.thumbnail_url ? (
              <img src={mediaUrl(character.thumbnail_url)} alt="" />
            ) : (
              <span>{t("character.cast.noThumbnail")}</span>
            )}
          </div>
          <div className="character-cast__appearance-fields">
            <SavedTextField
              label={t("character.field.name")}
              value={character.name}
              onSave={(name) =>
                name.trim() ? persist({ name: name.trim() }) : Promise.resolve()
              }
              maxLength={120}
              testId="character-detail-name"
            />
            <div className="character-cast__field">
              <div className="character-cast__field-head">
                <span className="character-cast__field-label">
                  {t("character.field.position")}
                </span>
              </div>
              <select
                className="character-panel__position"
                aria-label={t("character.field.position")}
                value={character.position}
                onChange={(e) =>
                  persistQuietly({
                    position: e.target.value as CharacterPosition,
                  })
                }
              >
                {CHARACTER_POSITIONS.map((p) => (
                  <option key={p} value={p}>
                    {t(`character.position.${p}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {resolveError && (
          <div className="character-panel__error">{resolveError}</div>
        )}
        <SavedTextField
          label={t("character.field.appearance_natural")}
          value={character.appearance_natural}
          onSave={async (appearance_natural) => {
            await persist({ appearance_natural });
            if (character.appearance_tags.trim()) setNaturalAheadOfTags(true);
          }}
          onTextChange={(text) => {
            naturalDraftRef.current = text;
            setNaturalFilled(Boolean(text.trim()));
          }}
          multiline
          maxLength={1000}
          testId="character-detail-natural"
        />
        <SavedTextField
          label={t("character.field.appearance_tags")}
          value={character.appearance_tags}
          onSave={async (appearance_tags) => {
            await persist({ appearance_tags });
            setNaturalAheadOfTags(false);
          }}
          multiline
          maxLength={2000}
          testId="character-detail-tags"
          action={
            <button
              type="button"
              className="character-panel__btn"
              onClick={() => void handleGenerateTags()}
              disabled={generatingTags || !naturalFilled}
              title={
                naturalFilled
                  ? undefined
                  : t("character.cast.generateTagsNeedNatural")
              }
              data-testid="character-generate-tags"
            >
              {generatingTags ? (
                <>
                  <span
                    className="character-cast__spinner"
                    aria-hidden="true"
                  />
                  {t("character.cast.generatingTags")}
                </>
              ) : (
                t("character.cast.generateTags")
              )}
            </button>
          }
        />
        <p className="character-cast__hint">{t("character.cast.tagsHint")}</p>
        {naturalAheadOfTags && (
          <p className="character-cast__warning" role="status">
            {t("character.cast.naturalChangedHint")}
          </p>
        )}
        {tagsError && <div className="character-panel__error">{tagsError}</div>}
        <SavedTextField
          label={t("character.field.negative_tags")}
          value={character.negative_tags}
          onSave={(negative_tags) => persist({ negative_tags })}
          multiline
          maxLength={400}
          placeholder={t("character.field.negative_tags_placeholder")}
          testId="character-detail-negative"
        />
        <div className="character-cast__toggles">
          <CastToggle
            checked={character.appearance_lock}
            label={t("character.field.appearance_lock")}
            showLabel
            onChange={(next) => persistQuietly({ appearance_lock: next })}
            testId="character-appearance-lock"
          />
          <CastToggle
            checked={character.exclude_from_effects}
            label={t("character.field.exclude_from_effects")}
            showLabel
            onChange={(next) => persistQuietly({ exclude_from_effects: next })}
            testId="character-exclude-from-effects"
          />
        </div>
      </CastSection>

      <CastSection
        id="current-look"
        title={t("character.cast.currentLookSection")}
      >
        <p
          className="character-cast__note"
          data-testid="character-current-note"
        >
          {currentLookNote}
        </p>
        {currentTags && (
          <textarea
            className="character-cast__readonly"
            value={currentTags}
            readOnly
            aria-label={t("character.cast.currentLookSection")}
            data-testid="character-current-tags"
          />
        )}
        <div className="character-cast__current-actions">
          <button
            type="button"
            className="character-panel__btn"
            onClick={handleCopyToSpec}
            disabled={!currentTags}
            data-testid="character-copy-to-spec"
          >
            {t("character.cast.copyToSpec")}
          </button>
          <button
            type="button"
            className="character-panel__btn"
            onClick={() => persistQuietly({ reset_look: true })}
            disabled={lookSource !== "history"}
            title={
              lookSource !== "history"
                ? t("character.cast.resetLookUnavailable")
                : undefined
            }
            data-testid="character-reset-look"
          >
            {t("character.cast.resetLook")}
          </button>
        </div>
      </CastSection>

      <CastSection id="profile" title={t("character.cast.profileSection")}>
        {character.is_protagonist ? (
          <p className="character-cast__note">
            {t("character.cast.protagonistProfileNote")}
          </p>
        ) : (
          <div className="character-cast__profile">
            <div className="character-cast__field">
              <div className="character-cast__field-head">
                <span className="character-cast__field-label">
                  {t("character.profile.memo")}
                </span>
                <div className="character-cast__field-action">
                  <button
                    type="button"
                    className="character-panel__btn"
                    onClick={() => void handleGenerateProfile()}
                    disabled={generating}
                    data-testid="character-generate-profile"
                  >
                    {generating ? (
                      <>
                        <span
                          className="character-cast__spinner"
                          aria-hidden="true"
                        />
                        {t("character.profile.generating")}
                      </>
                    ) : (
                      t("character.profile.generate")
                    )}
                  </button>
                </div>
              </div>
              <textarea
                value={profileDraft.memo}
                onChange={(e) =>
                  setProfileDraft((prev) => ({ ...prev, memo: e.target.value }))
                }
                onBlur={(e) => commitProfile({ memo: e.target.value })}
                placeholder={t("character.profile.memoPlaceholder")}
                maxLength={1000}
                aria-label={t("character.profile.memo")}
                data-testid="character-profile-memo"
              />
              <p className="character-cast__hint">
                {t("character.profile.generateHint")}
              </p>
            </div>
            {generateError && (
              <div className="character-panel__error">{generateError}</div>
            )}
            <ProfileFields
              value={profileDraft}
              onChange={handleProfileChange}
              onCommit={(patch) =>
                commitProfile(patch as Partial<CharacterProfile>)
              }
              allowUnsetGender
            />
          </div>
        )}
      </CastSection>

      <div className="character-cast__detail-footer">
        <button
          type="button"
          className="character-panel__btn"
          onClick={() => void handleSavePreset()}
          disabled={savingPreset}
          data-testid="character-save-preset-button"
        >
          {savingPreset
            ? t("character.preset.saving")
            : t("character.cast.savePreset")}
        </button>
      </div>
    </div>
  );
}
