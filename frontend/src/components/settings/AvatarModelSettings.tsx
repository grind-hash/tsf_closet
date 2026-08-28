/**
 * 設定画面「3Dモデル (VRM)」セクション。
 *
 * TSFシナリオの対面会話モードで攻略対象の代わりに表示する VRM を登録・一覧・
 * 改名・削除する。アップロードはこのリポジトリで唯一の multipart 送信。
 */

import type { DragEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AvatarApiError,
  type AvatarModel,
  deleteAvatarModel,
  listAvatarModels,
  renameAvatarModel,
  uploadAvatarModel,
} from "../../apis/avatars";
import PromptExpanderDeleteButton from "../promptExpander/PromptExpanderDeleteButton";
import AvatarPreviewModal from "./AvatarPreviewModal";
import "./AvatarModelSettings.css";

/** バックエンド既定の上限(AVATAR_UPLOAD_MAX_BYTES)。表示専用 */
const UPLOAD_LIMIT_MIB = 128;

function formatSize(bytes: number): string {
  const mib = bytes / (1024 * 1024);
  return mib >= 10 ? `${mib.toFixed(0)} MB` : `${mib.toFixed(1)} MB`;
}

function isVrmFile(file: File): boolean {
  return /\.vrm$/i.test(file.name) || file.type === "model/gltf-binary";
}

export default function AvatarModelSettings() {
  const { t, i18n } = useTranslation();
  const [models, setModels] = useState<AvatarModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [previewModel, setPreviewModel] = useState<AvatarModel | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);

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
      if (caught instanceof AvatarApiError) {
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

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      if (!isVrmFile(file)) {
        setError(t("settings.avatar.errors.notVrm"));
        return;
      }
      setUploadingName(file.name);
      try {
        const model = await uploadAvatarModel(file);
        setModels((current) => [model, ...current]);
      } catch (caught) {
        setError(describeError(caught));
      } finally {
        setUploadingName(null);
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
    const file = event.dataTransfer.files?.[0];
    if (file && uploadingName === null) void upload(file);
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

  const handleDelete = async (model: AvatarModel) => {
    if (
      !window.confirm(t("settings.avatar.deleteConfirm", { name: model.name }))
    )
      return;
    try {
      await deleteAvatarModel(model.id);
      setModels((current) => current.filter((item) => item.id !== model.id));
      if (previewModel?.id === model.id) setPreviewModel(null);
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
      <input
        ref={inputRef}
        type="file"
        accept=".vrm,model/gltf-binary"
        style={{ display: "none" }}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void upload(file);
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
        disabled={uploadingName !== null}
        data-testid="avatar-drop-zone"
      >
        {uploadingName !== null ? (
          <span className="avatar-settings__uploading" role="status">
            <span className="avatar-settings__spinner" aria-hidden />
            {t("settings.avatar.uploading", { name: uploadingName })}
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
      {error && (
        <p className="avatar-settings__error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p className="avatar-settings__empty" role="status">
          <span className="avatar-settings__spinner" aria-hidden />
        </p>
      ) : models.length === 0 ? (
        <p className="avatar-settings__empty">{t("settings.avatar.empty")}</p>
      ) : (
        <ul className="avatar-settings__list">
          {models.map((model) => (
            <li key={model.id} className="avatar-settings__row">
              <div className="avatar-settings__main">
                <strong className="avatar-settings__name">{model.name}</strong>
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
                          {model.meta.license ?? model.meta.license_url}
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
