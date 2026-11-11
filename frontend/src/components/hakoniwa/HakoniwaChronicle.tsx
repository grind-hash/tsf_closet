import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaEvent } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import HakoniwaDigest from "./HakoniwaDigest";
import { arcTitle } from "./hakoniwaLabels";

/** 年代記: 出来事を新しい順に並べる。お気に入りと、部屋での再生ができる */
export default function HakoniwaChronicle() {
  const { t } = useTranslation();
  const { world, setFavorite, replayEvent, playbackQueue, openAdv } =
    useHakoniwa();
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
  // エリアの外で起きた出来事は、その場所(浴室・商店街など)を出す
  const placeName = (event: HakoniwaEvent) =>
    (event.location &&
      world.locations.find((item) => item.id === event.location)?.name) ||
    (world.areas.find((area) => area.id === event.area)?.name ?? "");
  const arcName = (id: string) => {
    const arc = world.story_arcs.find((item) => item.id === id);
    return arc ? arcTitle(t, arc.kind, arc.resident_ids, nameOf) : "";
  };

  return (
    <div className="hakoniwa-chronicle">
      {world.last_digest && (
        <details className="hakoniwa-chronicle__digest">
          <summary>
            {t("hakoniwa.digest.latest", { day: world.last_digest.day })}
          </summary>
          <HakoniwaDigest variant="panel" />
        </details>
      )}
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
                {event.kind === "directed" && (
                  <span className="hakoniwa-badge hakoniwa-badge--accent">
                    {t("hakoniwa.chronicle.directedMark")}
                  </span>
                )}
                {event.kind === "confrontation" && (
                  <span className="hakoniwa-badge hakoniwa-badge--accent">
                    {t("hakoniwa.chronicle.confrontationMark")}
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
                <span className="hakoniwa-event__place">
                  {placeName(event)}
                </span>
              </p>
              {event.arc_id && (
                <p
                  className={`hakoniwa-event__arc${event.arc_climax ? " is-climax" : ""}`}
                >
                  {t(
                    event.arc_climax
                      ? "hakoniwa.chronicle.arcClimax"
                      : "hakoniwa.chronicle.arcContinue",
                    {
                      title:
                        arcName(event.arc_id) ||
                        t("hakoniwa.chronicle.arcUnknown"),
                    },
                  )}
                </p>
              )}
              {event.kind === "directed" && event.instruction && (
                <p className="hakoniwa-event__instruction">
                  {t("hakoniwa.chronicle.instruction", {
                    text: event.instruction,
                  })}
                </p>
              )}
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
              <div className="hakoniwa-event__actions">
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost hakoniwa-event__replay"
                  onClick={() => openAdv(event.id)}
                >
                  ▶ {t("hakoniwa.chronicle.openAdv")}
                </button>
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost hakoniwa-event__replay"
                  onClick={() => replayEvent(event)}
                  disabled={playbackQueue.length > 0}
                >
                  {t("hakoniwa.chronicle.replay")}
                </button>
                {event.scene_image_url ? (
                  <span className="hakoniwa-badge hakoniwa-badge--accent">
                    {t("hakoniwa.chronicle.hasScene")}
                  </span>
                ) : (
                  event.scene_suggestion && (
                    <span
                      className="hakoniwa-badge"
                      title={event.scene_suggestion.reason}
                    >
                      {t("hakoniwa.chronicle.sceneSuggested")}
                    </span>
                  )
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
