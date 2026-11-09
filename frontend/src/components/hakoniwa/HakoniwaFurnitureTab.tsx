import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

const NONE = "";

/** 家具タブ: 場所ごとのスロットに家具を置く・片付ける。家具は1点物で、別の場所に置くと移る */
export default function HakoniwaFurnitureTab() {
  const { t } = useTranslation();
  const { world, busy, placeFurniture, viewAreaId, setViewAreaId } =
    useHakoniwa();
  const baseId = useId();
  if (!world) return null;

  const locations = new Map<string, { areaName: string; slot: number }>();
  for (const area of world.areas) {
    area.slots.forEach((slot, index) => {
      if (slot.furniture_id) {
        locations.set(slot.furniture_id, {
          areaName: area.name,
          slot: index + 1,
        });
      }
    });
  }

  return (
    <div className="hakoniwa-furniture">
      <p className="hakoniwa-note">{t("hakoniwa.furniture.note")}</p>
      {world.areas.map((area) => (
        <section
          key={area.id}
          className={`hakoniwa-furniture__area${area.id === viewAreaId ? " is-viewing" : ""}`}
        >
          <div className="hakoniwa-furniture__head">
            <strong>{area.name}</strong>
            {area.id !== viewAreaId && (
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={() => setViewAreaId(area.id)}
              >
                {t("hakoniwa.furniture.view")}
              </button>
            )}
          </div>
          {area.slots.map((slot, index) => {
            const selectId = `${baseId}-${area.id}-${index}`;
            return (
              // ラベルで選択欄を包むと、選択肢の文までラベルの名前に混ざるため分けて置く
              <div key={selectId} className="hakoniwa-field">
                <label htmlFor={selectId}>
                  {t("hakoniwa.furniture.slot", { number: index + 1 })}
                </label>
                <select
                  id={selectId}
                  value={slot.furniture_id ?? NONE}
                  disabled={busy !== null}
                  onChange={(event) =>
                    void placeFurniture(
                      area.id,
                      index,
                      event.target.value === NONE ? null : event.target.value,
                    )
                  }
                >
                  <option value={NONE}>{t("hakoniwa.furniture.empty")}</option>
                  {world.furniture_catalog.map((item) => {
                    const place = locations.get(item.id);
                    const elsewhere =
                      place && item.id !== slot.furniture_id
                        ? t("hakoniwa.furniture.placedAt", place)
                        : "";
                    return (
                      <option key={item.id} value={item.id}>
                        {item.name}
                        {elsewhere}
                      </option>
                    );
                  })}
                </select>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
