import { useTranslation } from "react-i18next";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureProtagonistDockProps {
  onClose: () => void;
  /** 白抜き済みの最新の主人公立ち絵。無ければ図版を出さない */
  portraitUrl: string | null;
  /** romance のみ。白抜き済みの最新の攻略対象立ち絵 */
  partnerUrl: string | null;
  partnerClothing: string;
  /** フレームが無い間は全画面表示ボタンを無効化する */
  framesAvailable: boolean;
  onOpenPortrait: () => void;
  onOpenPartner: () => void;
}

/** 左レールの主人公ドック。常に最新の外見・服装を見せる(過去閲覧に追従しない) */
export default function AdventureProtagonistDock({
  onClose,
  portraitUrl,
  partnerUrl,
  partnerClothing,
  framesAvailable,
  onOpenPortrait,
  onOpenPartner,
}: AdventureProtagonistDockProps) {
  const { t } = useTranslation();
  const { activeRun } = useAdventure();
  if (!activeRun) return null;
  const sim = activeRun.preset === "romance" ? (activeRun.sim ?? null) : null;

  return (
    <aside
      className="adventure-protagonist-dock"
      aria-label={t("adventure.protagonist")}
    >
      <div className="adventure-protagonist-dock__head">
        <strong>{sim?.player_name || t("adventure.protagonist")}</strong>
        <button
          type="button"
          className="adventure-protagonist-dock__close"
          aria-label={t("adventure.protagonistHide")}
          title={t("adventure.protagonistHide")}
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      {portraitUrl && (
        <button
          type="button"
          className="adventure-protagonist-dock__figure"
          disabled={!framesAvailable}
          title={t("adventure.viewFullScreen")}
          onClick={onOpenPortrait}
        >
          <img src={portraitUrl} alt={t("adventure.portraitAlt")} />
        </button>
      )}
      <dl className="adventure-protagonist-dock__facts">
        <div>
          <dt>{t("adventure.protagonistAppearance")}</dt>
          <dd>
            {activeRun.visual_state?.appearance ||
              t("adventure.protagonistUnknown")}
          </dd>
        </div>
        <div>
          <dt>{t("adventure.protagonistClothing")}</dt>
          <dd>
            {activeRun.visual_state?.clothing ||
              t("adventure.protagonistUnknown")}
          </dd>
        </div>
      </dl>
      {sim && (
        <div className="adventure-protagonist-dock__partner">
          <div className="adventure-protagonist-dock__subhead">
            <span>{t("adventure.partnerSection")}</span>
            <strong>{sim.partner_name}</strong>
          </div>
          {partnerUrl && (
            <button
              type="button"
              className="adventure-protagonist-dock__figure"
              disabled={!framesAvailable}
              title={t("adventure.viewFullScreen")}
              onClick={onOpenPartner}
            >
              <img
                src={partnerUrl}
                alt={t("adventure.romance.partnerPortraitAlt")}
              />
            </button>
          )}
          <dl className="adventure-protagonist-dock__facts">
            <div>
              <dt>{t("adventure.protagonistAppearance")}</dt>
              <dd>
                {sim.partner_appearance || t("adventure.protagonistUnknown")}
              </dd>
            </div>
            <div>
              <dt>{t("adventure.protagonistClothing")}</dt>
              <dd>{partnerClothing || t("adventure.protagonistUnknown")}</dd>
            </div>
          </dl>
        </div>
      )}
    </aside>
  );
}
