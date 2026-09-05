import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { AdventureSim } from "../../apis/adventure";
import { PORTRAIT_ALPHA_OPTIONS } from "../../constants/adventure";
import { useAdventure } from "../../contexts/AdventureContext";
import type { AdventureLightboxView } from "../../hooks/useAdventureFrameNavigation";
import { useTransparentImage } from "../../hooks/useTransparentImage";
import {
  type AdventureStageFrame,
  frameDaySlot,
  partnerPortraitReasonKey,
} from "../../utils/adventureFrames";
import ImagePreviewModal from "../ImagePreviewModal";
import {
  formatInventoryLogEntry,
  keyedInventoryEntries,
} from "./AdventureInventoryPanel";

interface AdventureFramePreviewModalProps {
  frames: AdventureStageFrame[];
  /** モーダル内の位置。null なら閉じている */
  lightboxIndex: number | null;
  lightboxFrame: AdventureStageFrame | undefined;
  view: AdventureLightboxView;
  onViewChange: (view: AdventureLightboxView) => void;
  /** 前後送り。ステージ側の閲覧位置は動かさない */
  onNavigate: (index: number) => void;
  onClose: () => void;
  onRewind: (turnNumber: number) => void;
  /** romance の公開シミュ状態。他プリセットでは null */
  sim: AdventureSim | null;
  isCompanion: boolean;
}

/**
 * フレームのライトボックス。シーン / 背景 / 立ち絵 / 攻略対象 / 概要を切り替え、
 * 右側に手番の詳細(行動・本文・持ち物の変化・現在地)を出す。
 */
export default function AdventureFramePreviewModal({
  frames,
  lightboxIndex,
  lightboxFrame,
  view,
  onViewChange,
  onNavigate,
  onClose,
  onRewind,
  sim,
  isCompanion,
}: AdventureFramePreviewModalProps) {
  const { t } = useTranslation();
  const { activeRun, streaming } = useAdventure();
  // モーダルを開いた時に選択中のビュー切替チップへフォーカスを移すための参照
  const viewsRef = useRef<HTMLDivElement>(null);
  const open = lightboxFrame !== undefined;
  // タブ的なチップ列なので、モーダルを開いた時点で選択中のチップへ
  // キーボードフォーカスを移し、そのまま操作できるようにする
  useEffect(() => {
    if (!open) return;
    viewsRef.current
      ?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]')
      ?.focus();
  }, [open]);

  // romance のターン詳細用。開幕フレーム(手番0)には日付が無い。
  // 導出はサーバの scene_day/scene_slot に一本化し、HUD と食い違わせない
  const lightboxDaySlot = frameDaySlot(lightboxFrame);
  const canShowBackground = Boolean(lightboxFrame?.backgroundUrl);
  const canShowPortrait = Boolean(lightboxFrame?.portraitUrl);
  // romance: そのフレーム時点の攻略対象立ち絵があれば過去手番でも切替可能
  const canShowPartner =
    activeRun?.preset === "romance" && Boolean(lightboxFrame?.partnerUrl);
  // 非合成モードのシーン表示は、ステージと同じく背景に白抜きの立ち絵を重ねる。
  // 概要ビューは画像をシーンのまま維持し、右側の詳細だけを差し替える
  const needsComposite =
    (view === "scene" || view === "overview") &&
    (lightboxFrame?.kind === "portrait" || lightboxFrame?.kind === "partner") &&
    Boolean(lightboxFrame.backgroundUrl);
  // ステージ用の白抜き画像はモーダルと別フレームを指しうるので流用しない。
  // 同一 src なら utils/imageAlpha のモジュールキャッシュに当たるため追加コストは無い。
  const { url: lightboxPortraitUrl } = useTransparentImage(
    needsComposite ? lightboxFrame?.portraitUrl : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const { url: lightboxPartnerUrl } = useTransparentImage(
    needsComposite && canShowPartner ? lightboxFrame?.partnerUrl : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const lightboxImageUrl =
    view === "partner"
      ? (lightboxFrame?.partnerUrl ?? null)
      : view === "portrait"
        ? (lightboxFrame?.portraitUrl ?? null)
        : view === "background"
          ? (lightboxFrame?.backgroundUrl ?? null)
          : (lightboxFrame?.sceneUrl ??
            lightboxFrame?.backgroundUrl ??
            lightboxFrame?.imageUrl ??
            null);

  if (!activeRun) return null;

  return (
    <ImagePreviewModal
      isOpen={open}
      className={sim ? "adventure-preview--romance" : undefined}
      imageUrl={lightboxImageUrl}
      onClose={onClose}
      alt={
        view === "partner"
          ? t("adventure.romance.partnerPortraitAlt")
          : t("adventure.preview.sceneAlt")
      }
      onPrev={() => onNavigate((lightboxIndex ?? 0) - 1)}
      onNext={() => onNavigate((lightboxIndex ?? 0) + 1)}
      hasPrev={lightboxIndex !== null && lightboxIndex > 0}
      hasNext={lightboxIndex !== null && lightboxIndex < frames.length - 1}
      captionPlacement="side"
      media={
        needsComposite && lightboxFrame?.backgroundUrl ? (
          <div className="adventure-scene-preview">
            <img
              className="adventure-scene-preview__background"
              src={lightboxFrame.backgroundUrl}
              alt={t("adventure.preview.backgroundAlt")}
            />
            {lightboxPortraitUrl && (
              <img
                className={`adventure-scene-preview__portrait${
                  lightboxPartnerUrl
                    ? " adventure-scene-preview__portrait--paired"
                    : ""
                }`}
                src={lightboxPortraitUrl}
                alt={t("adventure.portraitAlt")}
              />
            )}
            {lightboxPartnerUrl && (
              <img
                className="adventure-scene-preview__portrait adventure-scene-preview__portrait--partner"
                src={lightboxPartnerUrl}
                alt={t("adventure.romance.partnerPortraitAlt")}
              />
            )}
          </div>
        ) : undefined
      }
      caption={
        lightboxFrame && (
          <div className="image-preview-modal__detail">
            <header className="adventure-preview__header">
              <p>{activeRun.title}</p>
              <h2>
                <b>{t("adventure.goal")}</b>
                <span>{activeRun.objective}</span>
              </h2>
            </header>
            {/* 概要は常に選べるため、切替チップ列は常時表示する */}
            <div
              ref={viewsRef}
              className="adventure-preview__views"
              role="group"
              aria-label={t("adventure.preview.viewSwitch")}
            >
              {/* シナリオ定義(舞台・制約・日数)の全文表示。先頭に置く */}
              <button
                type="button"
                aria-pressed={view === "overview"}
                onClick={() => onViewChange("overview")}
              >
                {t("adventure.preview.viewOverview")}
              </button>
              <button
                type="button"
                aria-pressed={view === "scene"}
                onClick={() => onViewChange("scene")}
              >
                {t("adventure.preview.viewScene")}
              </button>
              {canShowBackground && (
                <button
                  type="button"
                  aria-pressed={view === "background"}
                  onClick={() => onViewChange("background")}
                >
                  {t("adventure.preview.viewBackground")}
                </button>
              )}
              {canShowPortrait && (
                <button
                  type="button"
                  aria-pressed={view === "portrait"}
                  onClick={() => onViewChange("portrait")}
                >
                  {t("adventure.preview.viewPortrait")}
                </button>
              )}
              {canShowPartner && (
                <button
                  type="button"
                  aria-pressed={view === "partner"}
                  onClick={() => onViewChange("partner")}
                >
                  {t("adventure.romance.partnerLabel")}
                </button>
              )}
            </div>

            {view === "overview" ? (
              // 概要: シナリオ定義の全文を既存セクションと同じ様式で表示する。
              // タイトルとゴールは直上のヘッダに常時表示のため重複させない
              <>
                {activeRun.setting && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.setting")}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {activeRun.setting}
                    </p>
                  </section>
                )}
                {activeRun.constraints.length > 0 && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.constraints")}
                    </h2>
                    <ul className="adventure-preview__constraints">
                      {activeRun.constraints.map((item) => (
                        <li
                          key={item}
                          className="image-preview-modal__detail-text"
                        >
                          {item}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                {sim && !isCompanion && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.romance.days")}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {t("adventure.scenarioDeadline", {
                        days: sim.total_days,
                      })}
                    </p>
                  </section>
                )}
              </>
            ) : (
              <>
                {/* そのフレーム確定時点の sim だけを使う。activeRun.sim への
                フォールバックは過去手番に現在の好感度を出してしまうため行わない */}
                {sim && lightboxFrame.sim && (
                  <section className="image-preview-modal__detail-section adventure-preview-partner">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.romance.partnerLabel")}
                    </h2>
                    <p className="adventure-preview-partner__name">
                      {lightboxFrame.sim.partner_name}
                    </p>
                    <div
                      className={`adventure-preview-partner__affection is-${lightboxFrame.sim.stage}`}
                      title={t(
                        `adventure.romance.stages.${lightboxFrame.sim.stage}`,
                      )}
                    >
                      <svg
                        className="adventure-preview-partner__heart"
                        viewBox="0 0 24 24"
                        aria-hidden
                      >
                        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                      </svg>
                      <strong>
                        {lightboxFrame.sim.affection}
                        <i>/100</i>
                      </strong>
                      <span
                        className="adventure-preview-partner__gauge"
                        aria-hidden
                      >
                        <i
                          style={{ width: `${lightboxFrame.sim.affection}%` }}
                        />
                      </span>
                      <em className="adventure-preview-partner__stage">
                        {t(
                          `adventure.romance.stages.${lightboxFrame.sim.stage}`,
                        )}
                      </em>
                    </div>
                    {lightboxFrame.partnerNote && (
                      <p className="image-preview-modal__detail-text">
                        {lightboxFrame.partnerNote}
                      </p>
                    )}
                    {lightboxFrame.partnerInherited && (
                      <p className="image-preview-modal__detail-text adventure-preview-partner__portrait-note">
                        {t("adventure.partnerPortrait.note", {
                          reason: t(
                            `adventure.partnerPortrait.reason.${partnerPortraitReasonKey(
                              lightboxFrame.partnerStatus,
                            )}`,
                          ),
                        })}
                      </p>
                    )}
                  </section>
                )}

                <section className="image-preview-modal__detail-section">
                  <h2 className="image-preview-modal__detail-label">
                    {t("adventure.preview.turnLabel")}
                  </h2>
                  <p className="image-preview-modal__detail-text">
                    {lightboxFrame.turnNumber === 0
                      ? t("adventure.turnStrip.opening")
                      : sim && lightboxDaySlot && !isCompanion
                        ? lightboxFrame.sim?.epilogue
                          ? t("adventure.romance.previewTurnEpilogue", {
                              day: lightboxDaySlot.day,
                              slot: t(
                                `adventure.romance.slot.${lightboxDaySlot.slot}`,
                              ),
                              turn: lightboxFrame.turnNumber,
                            })
                          : t("adventure.romance.previewTurn", {
                              day: lightboxDaySlot.day,
                              total: sim.total_days,
                              slot: t(
                                `adventure.romance.slot.${lightboxDaySlot.slot}`,
                              ),
                              turn: lightboxFrame.turnNumber,
                              max: activeRun.max_turns,
                            })
                        : `${lightboxFrame.turnNumber} / ${activeRun.max_turns}`}
                  </p>
                  {lightboxFrame.turnNumber < activeRun.turn_count &&
                    (lightboxFrame.turnNumber > 0 ||
                      activeRun.can_rewind_to_opening) && (
                      <button
                        type="button"
                        className="adventure-preview__rewind"
                        disabled={streaming}
                        title={t("adventure.turnStrip.rewindHint")}
                        onClick={() => onRewind(lightboxFrame.turnNumber)}
                      >
                        {t("adventure.turnStrip.rewind")}
                      </button>
                    )}
                </section>

                {lightboxFrame.userInput && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.preview.actionLabel")}
                      {lightboxFrame.inputKind && (
                        <span className="adventure-preview__kind">
                          {t(
                            `adventure.preview.inputKind.${lightboxFrame.inputKind}`,
                          )}
                        </span>
                      )}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {lightboxFrame.userInput}
                    </p>
                  </section>
                )}

                <section className="image-preview-modal__detail-section">
                  <h2 className="image-preview-modal__detail-label">
                    {t("adventure.preview.narrativeLabel")}
                  </h2>
                  <p className="image-preview-modal__detail-text">
                    {lightboxFrame.narrative}
                  </p>
                </section>

                {(lightboxFrame.worldEvents?.length ?? 0) > 0 && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.inventoryChanges")}
                    </h2>
                    <ul className="adventure-preview__inventory-events">
                      {keyedInventoryEntries(
                        lightboxFrame.worldEvents ?? [],
                      ).map(({ key, entry }) => (
                        <li key={key}>{formatInventoryLogEntry(entry, t)}</li>
                      ))}
                    </ul>
                  </section>
                )}

                {lightboxFrame.location && (
                  <section className="image-preview-modal__detail-section">
                    <h2 className="image-preview-modal__detail-label">
                      {t("adventure.currentLocation")}
                    </h2>
                    <p className="image-preview-modal__detail-text">
                      {lightboxFrame.location}
                    </p>
                  </section>
                )}
              </>
            )}
          </div>
        )
      }
    />
  );
}
