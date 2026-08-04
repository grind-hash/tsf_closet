import { useTranslation } from "react-i18next";
import type { BloomerCatalog, BloomerRun } from "../../apis/bloomer";
import { useBloomer } from "../../contexts/BloomerContext";
import "./BloomerScreen.css";

interface Props {
  run: BloomerRun;
  catalog: BloomerCatalog | null;
  onClose: () => void;
}

export default function MilestoneModal({ run, catalog, onClose }: Props) {
  const { t } = useTranslation();
  const { doMilestone, actionLoading } = useBloomer();

  const milestone = catalog?.milestones[String(run.day)];
  if (!milestone) {
    onClose();
    return null;
  }

  const handleChoice = async (key: string) => {
    await doMilestone(key);
    onClose();
  };

  return (
    <div className="bloomer-modal__overlay" role="dialog" aria-modal="true">
      <div className="bloomer-modal">
        <h3 className="bloomer-modal__title">
          {t(`bloomer.milestones.${milestone.id}.title`, {
            defaultValue: t("bloomer.milestones.defaultTitle"),
          })}
        </h3>
        <p className="bloomer-modal__subtitle">
          {t("bloomer.milestones.chooseOne")}
        </p>
        <div className="bloomer-modal__choices">
          {Object.entries(milestone.choices).map(([key, choice]) => (
            <button
              key={key}
              type="button"
              className="bloomer-modal__choice-btn"
              onClick={() => handleChoice(key)}
              disabled={actionLoading}
            >
              <span className="bloomer-modal__choice-label">
                {t(`bloomer.milestones.${milestone.id}.choices.${key}`, {
                  defaultValue: key,
                })}
              </span>
              <span className="bloomer-modal__choice-hint">
                {choice.trust > 0 &&
                  `+${choice.trust} ${t("bloomer.room.trust")} `}
                {choice.trust < 0 &&
                  `${choice.trust} ${t("bloomer.room.trust")} `}
                {choice.mood > 0 && `+${choice.mood} ${t("bloomer.room.mood")}`}
                {choice.mood < 0 && `${choice.mood} ${t("bloomer.room.mood")}`}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
