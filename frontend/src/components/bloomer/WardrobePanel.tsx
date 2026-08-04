import { useTranslation } from "react-i18next";
import type { BloomerCatalog, BloomerRun } from "../../apis/bloomer";
import "./BloomerScreen.css";

interface Props {
  run: BloomerRun;
  catalog: BloomerCatalog | null;
  onEquip: (key: string) => void;
  onClose: () => void;
}

export default function WardrobePanel({
  run,
  catalog,
  onEquip,
  onClose,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="bloomer-modal__overlay" role="dialog" aria-modal="true">
      <div className="bloomer-modal bloomer-modal--wardrobe">
        <div className="bloomer-modal__header">
          <h3 className="bloomer-modal__title">
            {t("bloomer.wardrobe.title")}
          </h3>
          <button
            type="button"
            className="bloomer-modal__close"
            onClick={onClose}
            aria-label={t("bloomer.wardrobe.close")}
          >
            ×
          </button>
        </div>
        <ul className="bloomer-wardrobe__list">
          {run.wardrobe.map((key) => {
            const def = catalog?.outfits[key];
            const isEquipped = run.equipped_outfit === key;
            return (
              <li
                key={key}
                className={`bloomer-wardrobe__item${isEquipped ? " bloomer-wardrobe__item--equipped" : ""}`}
              >
                <span className="bloomer-wardrobe__name">
                  {t(`bloomer.outfits.${key}`, { defaultValue: key })}
                  {isEquipped && (
                    <span className="bloomer-wardrobe__equipped-badge">
                      {" "}
                      {t("bloomer.wardrobe.equipped")}
                    </span>
                  )}
                </span>
                {def && (
                  <span className="bloomer-wardrobe__tags">{def.tags}</span>
                )}
                {!isEquipped && (
                  <button
                    type="button"
                    className="bloomer-wardrobe__equip-btn"
                    onClick={() => onEquip(key)}
                  >
                    {t("bloomer.wardrobe.equip")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
