import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaRandomResident } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

const RANDOM_COUNT_MAX = 7;
const RANDOM_COUNT_DEFAULT = 3;

interface HakoniwaRandomRosterProps {
  residents: HakoniwaRandomResident[];
  onChange: (residents: HakoniwaRandomResident[]) => void;
  /** 重ねない名前(選んだプリセット・キャラクターの名前) */
  excludeNames: string[];
  /** おまかせの住民に使える人数(住民の上限から、ほかの住民を引いた数) */
  available: number;
}

/**
 * 作成画面の「おまかせの住民」。人数を選んで組み、1人ずつ入れ替えたり外したりできる。
 * 組んだ住民は、世界を作るときにほかの住民と一緒に送る。
 */
export default function HakoniwaRandomRoster({
  residents,
  onChange,
  excludeNames,
  available,
}: HakoniwaRandomRosterProps) {
  const { t } = useTranslation();
  const { busy, randomResidents } = useHakoniwa();
  const countId = useId();
  const [count, setCount] = useState(RANDOM_COUNT_DEFAULT);
  const [replacing, setReplacing] = useState<number | null>(null);
  const maxCount = Math.min(RANDOM_COUNT_MAX, Math.max(available, 0));
  const chosenCount = Math.min(count, maxCount);
  const rolling = busy === "random" && replacing === null;
  const countOptions = Array.from(
    { length: Math.max(maxCount, 1) },
    (_, position) => position + 1,
  );

  const roll = async () => {
    if (chosenCount < 1) return;
    const result = await randomResidents(chosenCount, excludeNames);
    if (result) onChange(result);
  };

  const replace = async (index: number) => {
    setReplacing(index);
    const others = residents
      .filter((_, position) => position !== index)
      .map((item) => item.name);
    const result = await randomResidents(1, [...excludeNames, ...others]);
    setReplacing(null);
    const next = result?.[0];
    if (!next) return;
    onChange(
      residents.map((item, position) => (position === index ? next : item)),
    );
  };

  const remove = (index: number) =>
    onChange(residents.filter((_, position) => position !== index));

  return (
    <div className="hakoniwa-random">
      <div className="hakoniwa-random__controls">
        <label className="hakoniwa-random__count" htmlFor={countId}>
          <span>{t("hakoniwa.random.countLabel")}</span>
          <select
            id={countId}
            value={chosenCount}
            disabled={busy !== null || maxCount < 1}
            onChange={(event) => setCount(Number(event.target.value))}
          >
            {countOptions.map((value) => (
              <option key={value} value={value}>
                {t("hakoniwa.random.countOption", { count: value })}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="hakoniwa-button"
          disabled={busy !== null || maxCount < 1}
          onClick={() => void roll()}
        >
          {rolling ? (
            <>
              <span className="hakoniwa-spinner" aria-hidden />
              {t("hakoniwa.random.rolling")}
            </>
          ) : residents.length > 0 ? (
            t("hakoniwa.random.reroll")
          ) : (
            t("hakoniwa.random.roll")
          )}
        </button>
      </div>
      {maxCount < 1 && (
        <p className="hakoniwa-note">{t("hakoniwa.random.full")}</p>
      )}
      {residents.length > 0 && (
        <ul className="hakoniwa-random__list">
          {residents.map((resident, index) => (
            // 名前は組んだ住民の中で重ならない
            <li key={resident.name} className="hakoniwa-random__item">
              <div className="hakoniwa-random__head">
                <strong>{resident.name}</strong>
                <span className="hakoniwa-roster__meta">
                  {t(`hakoniwa.gender.${resident.gender}`)}・{resident.age}・
                  {resident.job}
                </span>
              </div>
              <p>{resident.personality}</p>
              <p className="hakoniwa-note">{resident.appearance_text}</p>
              <div className="hakoniwa-random__actions">
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  disabled={busy !== null}
                  onClick={() => void replace(index)}
                >
                  {replacing === index ? (
                    <>
                      <span className="hakoniwa-spinner" aria-hidden />
                      {t("hakoniwa.random.replacing")}
                    </>
                  ) : (
                    t("hakoniwa.random.replace")
                  )}
                </button>
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  disabled={busy !== null}
                  onClick={() => remove(index)}
                >
                  {t("hakoniwa.random.remove")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="hakoniwa-note">{t("hakoniwa.random.note")}</p>
    </div>
  );
}
