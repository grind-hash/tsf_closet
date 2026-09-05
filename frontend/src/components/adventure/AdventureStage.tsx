import type { ComponentProps, ReactNode } from "react";
import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import type {
  AvatarExpressionKey,
  AvatarGestureKey,
} from "../../constants/companionAvatar";
import { useAdventure } from "../../contexts/AdventureContext";
import type { VisemeFrame } from "../../utils/visemeTimeline";
import AdventureBgmControl from "./AdventureBgmControl";

// 3D モデル(VRM)のステージは three.js を含むため遅延読込する
const CompanionAvatarStage = lazy(
  () => import("./avatar/CompanionAvatarStage"),
);

export interface AdventureStageAvatar {
  /** 対面会話モードで 3D モデルを表示するか(URL があり読込失敗していない) */
  show: boolean;
  url: string | null;
  expression: AvatarExpressionKey | null;
  gesture: AvatarGestureKey | null;
  /** 身振りの再生トリガ。同じキーの間は再再生しない */
  gestureKey: string | null;
  getVoiceLevel: () => number;
  getVisemeFrame: () => VisemeFrame | null;
  onError: (caught: unknown) => void;
}

interface AdventureStageProps {
  /** 背景または合成シーン。無ければ無地のステージ */
  imageUrl: string | null;
  /** 白抜き済みの主人公立ち絵(非合成・非対面のみ) */
  portraitUrl: string | null;
  /** 白抜き済みの攻略対象立ち絵(romance 非合成・対面) */
  partnerUrl: string | null;
  isCompositeMode: boolean;
  isCompanion: boolean;
  avatar: AdventureStageAvatar;
  /** ストリーム中で工程が進んでいる間(3D モデル表示中は覆わない) */
  showOverlay: boolean;
  isStageLoading: boolean;
  /** 工程の見なし進捗(0〜1)。null ならスピナー */
  progressRatio: number | null;
  phaseLabel: string;
  viewingPast: boolean;
  onBackToLatest: () => void;
  /** 表示中の過去フレームへ巻き戻せるか */
  canRewindHere: boolean;
  onRewind: () => void;
  /** 表示中フレームの主人公立ち絵生成が失敗している */
  portraitFailed: boolean;
  lightboxDisabled: boolean;
  onOpenLightbox: () => void;
  /** ↻。対面会話モードでは攻略対象の立ち絵だけを描き直す */
  onRegenerate: () => void;
  imageSettingsOpen: boolean;
  onToggleImageSettings: () => void;
  bgmControl: ComponentProps<typeof AdventureBgmControl>;
  /** 画像設定ポップオーバー(開いている間だけ渡す) */
  children?: ReactNode;
}

/** 画像ステージ。背景・立ち絵・3D モデル・進捗・過去閲覧バナーと右上の操作群 */
export default function AdventureStage({
  imageUrl,
  portraitUrl,
  partnerUrl,
  isCompositeMode,
  isCompanion,
  avatar,
  showOverlay,
  isStageLoading,
  progressRatio,
  phaseLabel,
  viewingPast,
  onBackToLatest,
  canRewindHere,
  onRewind,
  portraitFailed,
  lightboxDisabled,
  onOpenLightbox,
  onRegenerate,
  imageSettingsOpen,
  onToggleImageSettings,
  bgmControl,
  children,
}: AdventureStageProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, talking, regenerateImage } = useAdventure();
  if (!activeRun) return null;

  return (
    <section className="adventure-stage" aria-busy={showOverlay}>
      <div
        className={`adventure-stage__frame ${isCompositeMode ? "is-composite" : "is-background"}`}
      >
        <button
          type="button"
          className="adventure-stage__image-button"
          onClick={onOpenLightbox}
          disabled={lightboxDisabled}
          aria-label={t("adventure.viewFullScreen")}
        >
          {imageUrl ? (
            <img
              className={showOverlay ? "is-generating" : undefined}
              src={imageUrl}
              alt={activeRun.title}
            />
          ) : (
            <div className="adventure-stage__backdrop" aria-hidden />
          )}
        </button>
        <div className="adventure-stage__scrim" aria-hidden />
        {portraitUrl && (
          <img
            key={portraitUrl}
            className={`adventure-stage__portrait${
              partnerUrl ? " adventure-stage__portrait--paired" : ""
            }`}
            src={portraitUrl}
            alt={t("adventure.portraitAlt")}
          />
        )}
        {avatar.show && avatar.url ? (
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
        ) : (
          partnerUrl && (
            <img
              key={partnerUrl}
              className={`adventure-stage__portrait ${
                isCompanion
                  ? "adventure-stage__portrait--solo"
                  : "adventure-stage__portrait--partner"
              }`}
              src={partnerUrl}
              alt={t("adventure.romance.partnerPortraitAlt")}
            />
          )
        )}
        {showOverlay && !viewingPast && (
          <div className="adventure-stage__loading" role="status">
            {progressRatio !== null ? (
              <span className="adventure-progressbar" aria-hidden>
                <i style={{ width: `${Math.round(progressRatio * 100)}%` }} />
              </span>
            ) : (
              <span className="adventure-stage__loading-spinner" />
            )}
            <strong>{phaseLabel}</strong>
          </div>
        )}
        {viewingPast && (
          <div className="adventure-stage__past-banner">
            <span>{t("adventure.turnStrip.viewingPast")}</span>
            <button type="button" onClick={onBackToLatest}>
              {t("adventure.turnStrip.backToLatest")}
            </button>
            {canRewindHere && (
              <button
                type="button"
                className="adventure-stage__past-banner-rewind"
                title={t("adventure.turnStrip.rewindHint")}
                onClick={onRewind}
              >
                {t("adventure.turnStrip.rewind")}
              </button>
            )}
          </div>
        )}
        {portraitFailed && !isStageLoading && (
          <div className="adventure-stage__portrait-failed" role="status">
            <span>{t("adventure.portraitFailed")}</span>
            <button
              type="button"
              disabled={streaming || viewingPast}
              onClick={() =>
                regenerateImage({
                  redraw_from_reference: true,
                  target: "portrait",
                })
              }
            >
              {t("adventure.portraitRetry")}
            </button>
          </div>
        )}
        <button
          type="button"
          className="adventure-stage__regenerate"
          onClick={onRegenerate}
          disabled={streaming || talking || viewingPast}
          title={t(
            isCompanion
              ? "adventure.regeneratePartnerPortrait"
              : "adventure.regenerateImage",
          )}
          aria-label={t(
            isCompanion
              ? "adventure.regeneratePartnerPortrait"
              : "adventure.regenerateImage",
          )}
        >
          ↻
        </button>
        <button
          type="button"
          className="adventure-stage__settings"
          onClick={onToggleImageSettings}
          title={t("adventure.imageSettings")}
          aria-label={t("adventure.imageSettings")}
          aria-expanded={imageSettingsOpen}
        >
          ⚙
        </button>
        <AdventureBgmControl {...bgmControl} />
        {imageSettingsOpen && children}
      </div>
    </section>
  );
}
