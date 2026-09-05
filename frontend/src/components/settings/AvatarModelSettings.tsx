/**
 * 設定画面「3Dモデル (VRM)」セクション。
 *
 * TSFシナリオの対面会話モードで攻略対象の代わりに表示する VRM を登録・一覧・
 * 改名・削除する。アップロードはこのリポジトリで唯一の multipart 送信で、
 * 複数ファイルを順に登録する。
 * 同じキャラクターの衣装差分は character_name でまとめて表示し、各モデルの
 * 「キャラクターを編集」で付け替える(登録時はファイル名から自動分類される)。
 * キャラクターごとのグループは既定で閉じ、開閉状態は localStorage に保持する
 * (未分類は常に展開)。「ファイル名から自動分類」は未設定の項目だけを埋める。
 */

import type { DragEvent, FormEvent } from "react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  type AvatarModel,
  autoClassifyAvatarModels,
  avatarVariantLabel,
  classifyAvatarFilename,
  deleteAvatarModel,
  groupAvatarModels,
  listAvatarModels,
  renameAvatarModel,
  updateAvatarModel,
  uploadAvatarModel,
} from "../../apis/avatars";
import { usePersistedState } from "../../hooks/usePersistedState";
import { ApiError } from "../../utils/http";
import PromptExpanderDeleteButton from "../promptExpander/PromptExpanderDeleteButton";
import AvatarPreviewModal from "./AvatarPreviewModal";
import "./AvatarModelSettings.css";

/** バックエンド既定の上限(AVATAR_UPLOAD_MAX_BYTES)。表示専用 */
const UPLOAD_LIMIT_MIB = 128;
const CHARACTER_NAME_DATALIST_ID = "avatar-character-names";
/** キャラクターごとの開閉状態 { [character]: boolean }。未記録は閉じる */
export const AVATAR_GROUP_OPEN_KEY = "avatar_settings_group_open";

type GroupOpenMap = Record<string, boolean>;

function parseGroupOpenMap(raw: string): GroupOpenMap {
  const parsed: unknown = JSON.parse(raw);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as GroupOpenMap)
    : {};
}

/** 設定画面のセクション見出しに出す要約。読込中は null */
export interface AvatarModelSummary {
  total: number;
  characters: number;
}

interface AvatarModelSettingsProps {
  onSummaryChange?: (summary: AvatarModelSummary | null) => void;
}

function formatSize(bytes: number): string {
  const mib = bytes / (1024 * 1024);
  return mib >= 10 ? `${mib.toFixed(0)} MB` : `${mib.toFixed(1)} MB`;
}

function isVrmFile(file: File): boolean {
  return /\.vrm$/i.test(file.name) || file.type === "model/gltf-binary";
}

interface UploadProgress {
  name: string;
  index: number;
  total: number;
}

interface CharacterDraft {
  characterName: string;
  variantLabel: string;
}

export default function AvatarModelSettings({
  onSummaryChange,
}: AvatarModelSettingsProps = {}) {
  const { t, i18n } = useTranslation();
  const [models, setModels] = useState<AvatarModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [previewModel, setPreviewModel] = useState<AvatarModel | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CharacterDraft>({
    characterName: "",
    variantLabel: "",
  });
  const [savingId, setSavingId] = useState<string | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [groupOpen, setGroupOpen] = usePersistedState<GroupOpenMap>(
    AVATAR_GROUP_OPEN_KEY,
    {},
    { deserialize: parseGroupOpenMap },
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const groupBodyIdPrefix = useId();

  const groups = useMemo(() => groupAvatarModels(models), [models]);
  const characterNames = useMemo(
    () =>
      groups
        .map((group) => group.character)
        .filter((name): name is string => name !== null),
    [groups],
  );

  // 見出しの要約(件数・キャラクター数)は閉じている間も出すため、親へ知らせる
  const onSummaryChangeRef = useRef(onSummaryChange);
  onSummaryChangeRef.current = onSummaryChange;
  useEffect(() => {
    onSummaryChangeRef.current?.(
      loading
        ? null
        : { total: models.length, characters: characterNames.length },
    );
  }, [loading, models.length, characterNames.length]);

  const setGroupsOpen = useCallback(
    (names: string[], open: boolean) => {
      if (names.length === 0) return;
      setGroupOpen((current) => {
        const next = { ...current };
        for (const name of names) next[name] = open;
        return next;
      });
    },
    [setGroupOpen],
  );

  const refresh = useCallback(async () => {
    try {
      setModels(await listAvatarModels());
    } catch {
      setError(t("settings.avatar.errors.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const describeError = useCallback(
    (caught: unknown): string => {
      if (caught instanceof ApiError) {
        if (caught.code === "invalid_vrm") {
          return t("settings.avatar.errors.notVrm");
        }
        if (caught.code === "file_too_large") {
          return `${t("settings.avatar.errors.tooLarge")} ${caught.message}`;
        }
        return `${t("settings.avatar.errors.failed")} ${caught.message}`;
      }
      return t("settings.avatar.errors.failed");
    },
    [t],
  );

  /** 複数ファイルを順に登録する。失敗したものは飛ばして残りを続ける */
  const uploadFiles = useCallback(
    async (files: File[]) => {
      setError(null);
      const accepted = files.filter(isVrmFile);
      if (accepted.length === 0) {
        setError(t("settings.avatar.errors.notVrm"));
        return;
      }
      const failures: string[] = [];
      let lastError: string | null =
        accepted.length < files.length
          ? t("settings.avatar.errors.notVrm")
          : null;
      for (const [index, file] of accepted.entries()) {
        setUploading({
          name: file.name,
          index: index + 1,
          total: accepted.length,
        });
        try {
          const model = await uploadAvatarModel(file);
          setModels((current) => [model, ...current]);
        } catch (caught) {
          failures.push(file.name);
          lastError = describeError(caught);
        }
      }
      setUploading(null);
      if (failures.length > 0 && accepted.length > 1) {
        setError(
          `${t("settings.avatar.uploadPartialFailure", {
            failed: failures.length,
            names: failures.join(", "),
          })} ${lastError ?? ""}`.trim(),
        );
      } else if (lastError) {
        setError(lastError);
      }
    },
    [describeError, t],
  );

  const handleDragEnter = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    dragDepthRef.current += 1;
    setDragging(true);
  };
  const handleDragOver = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
  };
  const handleDragLeave = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragging(false);
  };
  const handleDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);
    const files = Array.from(event.dataTransfer.files ?? []);
    if (files.length > 0 && uploading === null) void uploadFiles(files);
  };

  const handleRename = async (model: AvatarModel) => {
    const next = window.prompt(t("settings.avatar.renamePrompt"), model.name);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed || trimmed === model.name) return;
    try {
      const renamed = await renameAvatarModel(model.id, trimmed);
      setModels((current) =>
        current.map((item) => (item.id === model.id ? renamed : item)),
      );
    } catch (caught) {
      setError(describeError(caught));
    }
  };

  /** グループ見出しからキャラクター名を一括で付け替える */
  const handleRenameCharacter = async (
    character: string,
    groupModels: AvatarModel[],
  ) => {
    const next = window.prompt(
      t("settings.avatar.renameCharacterPrompt", {
        total: groupModels.length,
      }),
      character,
    );
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed || trimmed === character) return;
    try {
      const updated = await Promise.all(
        groupModels.map((model) =>
          updateAvatarModel(model.id, { character_name: trimmed }),
        ),
      );
      const byId = new Map(updated.map((model) => [model.id, model]));
      setModels((current) => current.map((item) => byId.get(item.id) ?? item));
    } catch (caught) {
      setError(describeError(caught));
      // 一部だけ更新された可能性があるため、一覧を取り直して揃える
      await refresh();
    }
  };

  const startEditCharacter = (model: AvatarModel) => {
    setEditingId(model.id);
    // 未設定の欄はモデル名の規則から先に埋めておく(保存前に直せる)
    const guess = classifyAvatarFilename(model.name);
    setDraft({
      characterName: model.character_name ?? guess?.characterName ?? "",
      variantLabel: model.variant_label ?? guess?.variantLabel ?? "",
    });
  };

  /** 未設定の項目だけをモデル名の規則で埋める(設定済みの分類は変えない) */
  const handleAutoClassify = async () => {
    setClassifying(true);
    setError(null);
    setNotice(null);
    try {
      const result = await autoClassifyAvatarModels();
      setModels(result.items);
      if (result.updated > 0) {
        const touched = new Set(result.updated_ids);
        setGroupsOpen(
          [
            ...new Set(
              result.items
                .filter(
                  (model) => touched.has(model.id) && model.character_name,
                )
                .map((model) => model.character_name as string),
            ),
          ],
          true,
        );
        setNotice(
          t("settings.avatar.autoClassifyDone", { total: result.updated }),
        );
      } else {
        setNotice(t("settings.avatar.autoClassifyNone"));
      }
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setClassifying(false);
    }
  };

  const submitEditCharacter = async (
    event: FormEvent<HTMLFormElement>,
    model: AvatarModel,
  ) => {
    event.preventDefault();
    setSavingId(model.id);
    setError(null);
    try {
      const updated = await updateAvatarModel(model.id, {
        character_name: draft.characterName.trim(),
        variant_label: draft.variantLabel.trim(),
      });
      setModels((current) =>
        current.map((item) => (item.id === model.id ? updated : item)),
      );
      setEditingId(null);
      // 付け替え先のグループを開いて結果を見せる
      if (updated.character_name) setGroupsOpen([updated.character_name], true);
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = async (model: AvatarModel) => {
    if (
      !window.confirm(t("settings.avatar.deleteConfirm", { name: model.name }))
    )
      return;
    try {
      await deleteAvatarModel(model.id);
      setModels((current) => current.filter((item) => item.id !== model.id));
      if (previewModel?.id === model.id) setPreviewModel(null);
      if (editingId === model.id) setEditingId(null);
    } catch (caught) {
      setError(describeError(caught));
    }
  };

  const formatDate = (value: string | null): string => {
    if (!value) return "-";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleDateString(i18n.language);
  };

  return (
    <div className="avatar-settings">
      <p className="avatar-settings__description">
        {t("settings.avatar.description")}
      </p>
      <p className="avatar-settings__description">
        {t("settings.avatar.namingRule")}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".vrm,model/gltf-binary"
        multiple
        style={{ display: "none" }}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length > 0) void uploadFiles(files);
        }}
      />
      <button
        type="button"
        className={`avatar-settings__drop-zone${dragging ? " is-dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        disabled={uploading !== null}
        data-testid="avatar-drop-zone"
      >
        {uploading !== null ? (
          <span className="avatar-settings__uploading" role="status">
            <span className="avatar-settings__spinner" aria-hidden />
            {uploading.total > 1
              ? t("settings.avatar.uploadingProgress", {
                  name: uploading.name,
                  index: uploading.index,
                  total: uploading.total,
                })
              : t("settings.avatar.uploading", { name: uploading.name })}
          </span>
        ) : dragging ? (
          t("settings.avatar.dropActive")
        ) : (
          <>
            <span>{t("settings.avatar.dropZone")}</span>
            <small>
              {t("settings.avatar.limit", { size: UPLOAD_LIMIT_MIB })}
            </small>
          </>
        )}
      </button>
      <div className="avatar-settings__toolbar">
        <button
          type="button"
          className="avatar-settings__action"
          onClick={() => void handleAutoClassify()}
          disabled={classifying || loading || uploading !== null}
        >
          {classifying && (
            <span className="avatar-settings__spinner" aria-hidden />
          )}
          {t("settings.avatar.autoClassify")}
        </button>
        <small className="avatar-settings__toolbar-hint">
          {t("settings.avatar.autoClassifyHint")}
        </small>
      </div>
      {error && (
        <p className="avatar-settings__error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="avatar-settings__notice" role="status">
          {notice}
        </p>
      )}
      {loading ? (
        <p className="avatar-settings__empty" role="status">
          <span className="avatar-settings__spinner" aria-hidden />
        </p>
      ) : models.length === 0 ? (
        <p className="avatar-settings__empty">{t("settings.avatar.empty")}</p>
      ) : (
        <div className="avatar-settings__groups">
          {groups.map((group, groupIndex) => {
            // 未分類は常に展開(分類待ちの行を隠さない)。キャラクターは既定で閉じる
            const open =
              group.character === null || groupOpen[group.character] === true;
            const bodyId = `${groupBodyIdPrefix}-${groupIndex}`;
            return (
              <section
                key={group.character ?? "__ungrouped__"}
                className={`avatar-settings__group${
                  group.character === null ? " is-ungrouped" : ""
                }${open ? " is-open" : " is-collapsed"}`}
                data-testid="avatar-group"
                data-character={group.character ?? ""}
              >
                <header className="avatar-settings__group-header">
                  <h3 className="avatar-settings__group-title">
                    {group.character === null ? (
                      t("settings.avatar.ungrouped")
                    ) : (
                      <button
                        type="button"
                        className="avatar-settings__group-toggle"
                        aria-expanded={open}
                        aria-controls={bodyId}
                        title={t(
                          open
                            ? "settings.avatar.hideVariants"
                            : "settings.avatar.showVariants",
                        )}
                        onClick={() =>
                          setGroupsOpen([group.character as string], !open)
                        }
                      >
                        {group.character}
                      </button>
                    )}
                  </h3>
                  {group.character !== null && (
                    <>
                      <span className="avatar-settings__group-count">
                        {t("settings.avatar.variantCount", {
                          total: group.models.length,
                        })}
                      </span>
                      <button
                        type="button"
                        className="avatar-settings__action"
                        onClick={() =>
                          void handleRenameCharacter(
                            group.character as string,
                            group.models,
                          )
                        }
                      >
                        {t("settings.avatar.renameCharacter")}
                      </button>
                    </>
                  )}
                </header>
                <div
                  id={bodyId}
                  className="avatar-settings__group-body"
                  hidden={!open}
                >
                  {group.character !== null && group.models.length >= 2 && (
                    <p className="avatar-settings__group-hint">
                      {t("settings.avatar.characterGroupHint")}
                    </p>
                  )}
                  <ul className="avatar-settings__list">
                    {group.models.map((model) => (
                      <li key={model.id} className="avatar-settings__row">
                        <div className="avatar-settings__main">
                          <strong className="avatar-settings__name">
                            {group.character === null
                              ? model.name
                              : avatarVariantLabel(model)}
                          </strong>
                          {group.character !== null &&
                            model.variant_label &&
                            model.variant_label !== model.name && (
                              <span className="avatar-settings__subname">
                                {t("settings.avatar.modelName")}: {model.name}
                              </span>
                            )}
                          <dl className="avatar-settings__meta">
                            <div>
                              <dt>{t("settings.avatar.author")}</dt>
                              <dd>{model.meta.author ?? "-"}</dd>
                            </div>
                            <div>
                              <dt>{t("settings.avatar.license")}</dt>
                              <dd>
                                {model.meta.license_url ? (
                                  <a
                                    href={model.meta.license_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {model.meta.license ??
                                      model.meta.license_url}
                                  </a>
                                ) : (
                                  (model.meta.license ?? "-")
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>{t("settings.avatar.size")}</dt>
                              <dd>{formatSize(model.file_size)}</dd>
                            </div>
                            <div>
                              <dt>{t("settings.avatar.registeredAt")}</dt>
                              <dd>{formatDate(model.created_at)}</dd>
                            </div>
                          </dl>
                          {editingId === model.id && (
                            <form
                              className="avatar-settings__edit"
                              onSubmit={(event) =>
                                void submitEditCharacter(event, model)
                              }
                              data-testid="avatar-character-editor"
                            >
                              <label className="avatar-settings__field">
                                <span>
                                  {t("settings.avatar.characterName")}
                                </span>
                                <input
                                  type="text"
                                  list={CHARACTER_NAME_DATALIST_ID}
                                  maxLength={80}
                                  value={draft.characterName}
                                  placeholder={t(
                                    "settings.avatar.characterNamePlaceholder",
                                  )}
                                  onChange={(event) =>
                                    setDraft((current) => ({
                                      ...current,
                                      characterName: event.target.value,
                                    }))
                                  }
                                />
                              </label>
                              <label className="avatar-settings__field">
                                <span>{t("settings.avatar.variantLabel")}</span>
                                <input
                                  type="text"
                                  maxLength={80}
                                  value={draft.variantLabel}
                                  placeholder={t(
                                    "settings.avatar.variantLabelPlaceholder",
                                  )}
                                  onChange={(event) =>
                                    setDraft((current) => ({
                                      ...current,
                                      variantLabel: event.target.value,
                                    }))
                                  }
                                />
                              </label>
                              <small className="avatar-settings__field-hint">
                                {t("settings.avatar.variantLabelHint")}
                              </small>
                              <div className="avatar-settings__edit-actions">
                                <button
                                  type="submit"
                                  className="avatar-settings__action avatar-settings__action--primary"
                                  disabled={savingId === model.id}
                                >
                                  {t("settings.avatar.save")}
                                </button>
                                <button
                                  type="button"
                                  className="avatar-settings__action"
                                  disabled={savingId === model.id}
                                  onClick={() => setEditingId(null)}
                                >
                                  {t("settings.avatar.cancel")}
                                </button>
                              </div>
                            </form>
                          )}
                        </div>
                        <div className="avatar-settings__actions">
                          <button
                            type="button"
                            className="avatar-settings__action"
                            onClick={() => setPreviewModel(model)}
                          >
                            {t("settings.avatar.preview")}
                          </button>
                          <button
                            type="button"
                            className="avatar-settings__action"
                            onClick={() => void handleRename(model)}
                          >
                            {t("settings.avatar.rename")}
                          </button>
                          <button
                            type="button"
                            className="avatar-settings__action"
                            aria-pressed={editingId === model.id}
                            onClick={() =>
                              editingId === model.id
                                ? setEditingId(null)
                                : startEditCharacter(model)
                            }
                          >
                            {t("settings.avatar.editCharacter")}
                          </button>
                          <span className="avatar-settings__badge">
                            {t(
                              model.vrm_spec_version === "1"
                                ? "settings.avatar.spec1"
                                : "settings.avatar.spec0",
                            )}
                          </span>
                          <PromptExpanderDeleteButton
                            label={t("settings.avatar.delete")}
                            onClick={() => void handleDelete(model)}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            );
          })}
          <datalist id={CHARACTER_NAME_DATALIST_ID}>
            {characterNames.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </div>
      )}
      {previewModel && (
        <AvatarPreviewModal
          model={previewModel}
          onClose={() => setPreviewModel(null)}
        />
      )}
    </div>
  );
}
