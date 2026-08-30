/**
 * 登録済み VRM のプレビュー。表情と身振りを LLM を回さずに確認する。
 * 読み上げは無いので口は動かない(音量レベルは常に 0)。
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AvatarModel, avatarModelFileUrl } from "../../apis/avatars";
import {
  AVATAR_EXPRESSIONS,
  AVATAR_GESTURES,
  type AvatarExpressionKey,
  type AvatarGestureKey,
} from "../../constants/companionAvatar";
import "./AvatarPreviewModal.css";

const CompanionAvatarStage = lazy(
  () => import("../adventure/avatar/CompanionAvatarStage"),
);

const silentLevel = () => 0;

interface AvatarPreviewModalProps {
  model: AvatarModel;
  onClose: () => void;
}

export default function AvatarPreviewModal({
  model,
  onClose,
}: AvatarPreviewModalProps) {
  const { t } = useTranslation();
  const [expression, setExpression] = useState<AvatarExpressionKey>("neutral");
  const [gesture, setGesture] = useState<AvatarGestureKey>("nod");
  const [gestureKey, setGestureKey] = useState<string | null>(null);
  const [playCount, setPlayCount] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const playGesture = () => {
    const next = playCount + 1;
    setPlayCount(next);
    setGestureKey(`preview:${next}`);
  };

  return (
    <div className="avatar-preview__backdrop" onClick={onClose}>
      <div
        className="avatar-preview"
        role="dialog"
        aria-modal="true"
        aria-label={t("settings.avatar.previewTitle")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="avatar-preview__header">
          <h3>
            {t("settings.avatar.previewTitle")}: {model.name}
          </h3>
          <button
            type="button"
            className="avatar-preview__close"
            onClick={onClose}
          >
            {t("settings.avatar.close")}
          </button>
        </header>
        <div className="avatar-preview__stage">
          {failed ? (
            <p className="avatar-preview__error" role="alert">
              {t("adventure.avatar.loadFailed")}
            </p>
          ) : (
            <Suspense fallback={null}>
              <CompanionAvatarStage
                fileUrl={avatarModelFileUrl(model.id)}
                expression={expression}
                gesture={gesture}
                gestureKey={gestureKey}
                getVoiceLevel={silentLevel}
                onError={() => setFailed(true)}
              />
            </Suspense>
          )}
        </div>
        <div className="avatar-preview__controls">
          <label>
            <span>{t("settings.avatar.previewExpression")}</span>
            <select
              value={expression}
              onChange={(event) =>
                setExpression(event.target.value as AvatarExpressionKey)
              }
            >
              {AVATAR_EXPRESSIONS.map((key) => (
                <option key={key} value={key}>
                  {t(`settings.avatar.expressions.${key}`)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("settings.avatar.previewGesture")}</span>
            <select
              value={gesture}
              onChange={(event) =>
                setGesture(event.target.value as AvatarGestureKey)
              }
            >
              {AVATAR_GESTURES.map((key) => (
                <option key={key} value={key}>
                  {t(`settings.avatar.gestures.${key}`)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="avatar-preview__play"
            onClick={playGesture}
            disabled={failed}
          >
            {t("settings.avatar.previewPlay")}
          </button>
        </div>
        <p className="avatar-preview__hint">
          {t("settings.avatar.previewHint")}
        </p>
      </div>
    </div>
  );
}
