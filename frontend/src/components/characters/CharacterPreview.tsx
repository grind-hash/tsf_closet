/**
 * キャラクター画面の右パネル。立ち絵、または 3D モデル(VRM)を表情つきで見せ、
 * 「このキャラと話す」を置く。
 */

import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AvatarModel, listAvatarModels } from "../../apis/avatars";
import { PORTRAIT_ALPHA_OPTIONS } from "../../constants/adventure";
import {
  AVATAR_EXPRESSIONS,
  type AvatarExpressionKey,
} from "../../constants/companionAvatar";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import type { CharacterPreset } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import { isGeneratedPortrait } from "./characterMaker";

// three.js を含むため別チャンクにする
const CompanionAvatarStage = lazy(
  () => import("../adventure/avatar/CompanionAvatarStage"),
);

const silentLevel = () => 0;

interface CharacterPreviewProps {
  preset: CharacterPreset;
  talking: boolean;
  onTalk: () => void;
}

export default function CharacterPreview({
  preset,
  talking,
  onTalk,
}: CharacterPreviewProps) {
  const { t } = useTranslation();
  const [model, setModel] = useState<AvatarModel | null>(null);
  const [avatarFailed, setAvatarFailed] = useState(false);
  const [expression, setExpression] = useState<AvatarExpressionKey>("neutral");
  const avatarId = preset.avatar_model_id;

  useEffect(() => {
    setAvatarFailed(false);
    if (!avatarId) {
      setModel(null);
      return;
    }
    let cancelled = false;
    listAvatarModels()
      .then((items) => {
        if (!cancelled)
          setModel(items.find((item) => item.id === avatarId) ?? null);
      })
      .catch(() => {
        if (!cancelled) setModel(null);
      });
    return () => {
      cancelled = true;
    };
  }, [avatarId]);

  const showVrm = model !== null && !avatarFailed;
  const { url: portraitUrl } = useTransparentImage(
    showVrm || !preset.portrait_url ? null : mediaUrl(preset.portrait_url),
    isGeneratedPortrait(preset.portrait_url),
    PORTRAIT_ALPHA_OPTIONS,
  );

  return (
    <div className="character-preview">
      <h2 className="character-preview__title">
        {t("characters.preview.title")}
      </h2>
      <div className="character-preview__stage">
        {showVrm ? (
          <Suspense fallback={null}>
            <CompanionAvatarStage
              fileUrl={model.file_url}
              expression={expression}
              gesture={null}
              gestureKey={null}
              framing="upper"
              getVoiceLevel={silentLevel}
              onError={() => setAvatarFailed(true)}
            />
          </Suspense>
        ) : portraitUrl ? (
          <img src={portraitUrl} alt={preset.name} />
        ) : (
          <span className="character-preview__empty">
            {t("characters.portrait.none")}
          </span>
        )}
      </div>
      {showVrm && (
        <div className="character-chat__preview-chips">
          {AVATAR_EXPRESSIONS.map((key) => (
            <button
              key={key}
              type="button"
              className={`character-chat__preview-chip${expression === key ? " is-active" : ""}`}
              aria-pressed={expression === key}
              onClick={() => setExpression(key)}
            >
              {t(`settings.avatar.expressions.${key}`)}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        className="character-chat__primary character-preview__talk"
        disabled={talking}
        onClick={onTalk}
      >
        {talking ? t("characters.talking") : t("characters.talk")}
      </button>
      <p className="character-cast__hint">{t("characters.preview.talkHint")}</p>
    </div>
  );
}
