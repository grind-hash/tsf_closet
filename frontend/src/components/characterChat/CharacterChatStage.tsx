import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import type { CharacterChatThread } from "../../apis/characterChat";
import { PORTRAIT_ALPHA_OPTIONS } from "../../constants/adventure";
import type {
  AvatarExpressionKey,
  AvatarGestureKey,
} from "../../constants/companionAvatar";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import type { VisemeFrame } from "../../utils/visemeTimeline";

// three.js を含むため別チャンクにする(Adventure の対面会話モードと同じ)
const CompanionAvatarStage = lazy(
  () => import("../adventure/avatar/CompanionAvatarStage"),
);

export interface CharacterChatStageAvatar {
  url: string;
  expression: AvatarExpressionKey | null;
  gesture: AvatarGestureKey | null;
  gestureKey: string | null;
  getVoiceLevel: () => number;
  getVisemeFrame: () => VisemeFrame | null;
  onError: (error: unknown) => void;
}

interface CharacterChatStageProps {
  thread: CharacterChatThread;
  /** 立ち絵の描き直し・姿の差し替え中 */
  busy: boolean;
  /** 発言の処理が立ち絵工程にいる */
  drawing: boolean;
  onGenerate: () => void;
  /** adventure 種で run に 3D モデル(VRM)が割り当てられていれば立ち絵の代わりに置く */
  avatar?: CharacterChatStageAvatar | null;
}

const BUNDLED_PORTRAIT_FILENAME = "serena.png";

/**
 * 全画面のステージ。Adventure の対面会話モードと同じく、キャラクターを中央に
 * 大きく立たせる。生成した立ち絵(standing)は白抜きし、素材からコピーした
 * 場面画像(scene)は素通しで出す。画像が無ければ案内と生成ボタン。
 * 3D モデル(VRM)があればその枠に CompanionAvatarStage を置く。
 */
export default function CharacterChatStage({
  thread,
  busy,
  drawing,
  onGenerate,
  avatar,
}: CharacterChatStageProps) {
  const { t } = useTranslation();
  const standing = thread.appearance.portrait_kind === "standing";
  const { url, processing } = useTransparentImage(
    avatar ? null : thread.portrait_url,
    standing,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const working = busy || drawing;

  return (
    <div className="character-chat-room__stage" aria-busy={working}>
      <div className="character-chat-room__backdrop" />
      {avatar ? (
        <div className="character-chat-room__avatar">
          <Suspense fallback={null}>
            <CompanionAvatarStage
              fileUrl={avatar.url}
              expression={avatar.expression}
              gesture={avatar.gesture}
              gestureKey={avatar.gestureKey}
              getVoiceLevel={avatar.getVoiceLevel}
              getVisemeFrame={avatar.getVisemeFrame}
              onError={avatar.onError}
            />
          </Suspense>
        </div>
      ) : url ? (
        <img
          className={`character-chat-room__portrait${
            standing ? "" : " character-chat-room__portrait--scene"
          }${working ? " is-working" : ""}`}
          src={url}
          alt={thread.name}
        />
      ) : (
        <div className="character-chat-room__missing">
          <span className="character-chat__placeholder" aria-hidden>
            💬
          </span>
          {thread.portrait_missing && (
            <>
              <p>
                {t("characterChat.room.portraitMissing", {
                  file: BUNDLED_PORTRAIT_FILENAME,
                })}
              </p>
              <button
                type="button"
                className="character-chat__secondary"
                disabled={working}
                onClick={onGenerate}
              >
                {t("characterChat.room.generatePortrait")}
              </button>
            </>
          )}
        </div>
      )}
      <div className="character-chat-room__scrim" />
      {(working || processing) && (
        <div className="character-chat-room__stage-status" role="status">
          <span className="character-chat__progress">
            <span />
            {working
              ? drawing
                ? t("characterChat.room.portraitBusy")
                : t("characterChat.room.appearanceUpdating")
              : ""}
          </span>
          {working && drawing && (
            <small>{t("characterChat.room.portraitBusyHint")}</small>
          )}
        </div>
      )}
    </div>
  );
}
