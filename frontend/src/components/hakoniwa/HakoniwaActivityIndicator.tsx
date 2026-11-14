import { useTranslation } from "react-i18next";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { currentActivity } from "./hakoniwaActivity";

const ACTIVITY_LABEL_KEYS = {
  day: "hakoniwa.activity.day",
  eventWriting: "hakoniwa.activity.eventWriting",
  eventPlanning: "hakoniwa.activity.eventPlanning",
  eventPortraits: "hakoniwa.activity.eventPortraits",
  eventScene: "hakoniwa.activity.eventScene",
  transform: "hakoniwa.activity.transform",
  reality: "hakoniwa.activity.reality",
  avatar: "hakoniwa.activity.avatar",
  avatarBatch: "hakoniwa.activity.avatarBatch",
  look: "hakoniwa.activity.look",
  memoPlanning: "hakoniwa.activity.memoPlanning",
  scene: "hakoniwa.activity.scene",
} as const;

/**
 * 上端のバーに出す、いま進めている処理(出来事・変身・姿・場面の絵など)。
 * 処理は始めたタブの中のボタンにしか出ないので、別のタブへ移っても分かるように、
 * どのタブからも見える場所に出す。バーの下端には動く線を重ねる(レイアウトは動かさない)。
 */
export default function HakoniwaActivityIndicator() {
  const { t } = useTranslation();
  const { world, busy, lookTarget, lookProgress, avatarBatch, eventProgress } =
    useHakoniwa();
  const activity = currentActivity({
    busy,
    lookTarget,
    lookProgress,
    avatarBatch,
    eventProgress,
  });
  if (!activity) return null;

  const lookLabel = () => {
    if (activity.lookTarget === "combo")
      return t("hakoniwa.activity.lookCombo");
    if (activity.lookTarget === "memo") return t("hakoniwa.activity.lookMemo");
    const rule = world?.rule_cards.find(
      (card) => card.id === activity.lookTarget,
    );
    return rule
      ? t("hakoniwa.activity.lookRule", { name: rule.name })
      : t("hakoniwa.activity.lookOther");
  };

  return (
    <div
      className="hakoniwa-activity"
      role="status"
      data-testid="hakoniwa-activity"
    >
      <span className="hakoniwa-spinner" aria-hidden />
      <span className="hakoniwa-activity__text">
        {t(ACTIVITY_LABEL_KEYS[activity.kind], {
          done: activity.done ?? 0,
          total: activity.total ?? 0,
          label: activity.kind === "look" ? lookLabel() : "",
        })}
      </span>
      <span className="hakoniwa-activity__bar" aria-hidden />
    </div>
  );
}
