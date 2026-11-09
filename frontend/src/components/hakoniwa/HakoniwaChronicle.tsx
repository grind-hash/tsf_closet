import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useHakoniwa } from "../../contexts/HakoniwaContext";

/** 年代記: 出来事を新しい順に並べる。お気に入りと、部屋での再生ができる */
export default function HakoniwaChronicle() {
  const { t } = useTranslation();
  const { world, setFavorite, replayEvent, playbackQueue } = useHakoniwa();
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const filterId = useId();

  const names = useMemo(
    () =>
      Object.fromEntries(
        (world?.residents ?? []).map((resident) => [
          resident.id,
          resident.name,
        ]),
      ),
    [world?.residents],
  );
  const events = useMemo(() => {
    const list = [...(world?.events ?? [])].reverse();
    return favoritesOnly ? list.filter((event) => event.favorite) : list;
  }, [favoritesOnly, world?.events]);

  if (!world) return null;
  const nameOf = (id: string) => names[id] ?? "?";

  return (
    <div className="hakoniwa-chronicle">
      <label className="hakoniwa-toggle" htmlFor={filterId}>
        <span>{t("hakoniwa.chronicle.favoritesOnly")}</span>
        <input
          id={filterId}
          type="checkbox"
          className="hakoniwa-toggle__input"
          checked={favoritesOnly}
          onChange={(event) => setFavoritesOnly(event.target.checked)}
        />
        <span className="hakoniwa-toggle__switch" aria-hidden />
      </label>
      {events.length === 0 ? (
        <p className="hakoniwa-note">{t("hakoniwa.chronicle.empty")}</p>
      ) : (
        <ol className="hakoniwa-chronicle__list">
          {events.map((event) => (
            <li key={event.id} className="hakoniwa-event">
              <div className="hakoniwa-event__head">
                <span className="hakoniwa-event__day">
                  {t("hakoniwa.chronicle.day", { day: event.day })}
                </span>
                <strong className="hakoniwa-event__title">{event.title}</strong>
                {event.kind === "transform" && (
                  <span className="hakoniwa-badge hakoniwa-badge--accent">
                    {t("hakoniwa.chronicle.transformMark")}
                  </span>
                )}
                {event.source === "template" && (
                  <span className="hakoniwa-badge">
                    {t("hakoniwa.chronicle.sourceTemplate")}
                  </span>
                )}
                <button
                  type="button"
                  className={`hakoniwa-event__star${event.favorite ? " is-on" : ""}`}
                  aria-pressed={event.favorite}
                  aria-label={
                    event.favorite
                      ? t("hakoniwa.chronicle.unfavorite")
                      : t("hakoniwa.chronicle.favorite")
                  }
                  title={
                    event.favorite
                      ? t("hakoniwa.chronicle.unfavorite")
                      : t("hakoniwa.chronicle.favorite")
                  }
                  onClick={() => void setFavorite(event.id, !event.favorite)}
                >
                  {event.favorite ? "★" : "☆"}
                </button>
              </div>
              <p className="hakoniwa-event__participants">
                {t("hakoniwa.chronicle.participants", {
                  names: event.participants.map(nameOf).join("・"),
                })}
              </p>
              <p className="hakoniwa-event__narration">{event.narration}</p>
              {event.lines.length > 0 && (
                <ul className="hakoniwa-event__lines">
                  {event.lines.map((line, index) => (
                    <li
                      // biome-ignore lint/suspicious/noArrayIndexKey: 台詞は並び順そのものが識別子
                      key={index}
                    >
                      <span className="hakoniwa-event__speaker">
                        {nameOf(line.speaker)}
                      </span>
                      <span>
                        {t("hakoniwa.chronicle.line", { text: line.text })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost hakoniwa-event__replay"
                onClick={() => replayEvent(event)}
                disabled={playbackQueue.length > 0}
              >
                ▶ {t("hakoniwa.chronicle.replay")}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
