import { useTranslation } from "react-i18next";
import type {
  HakoniwaDigestChange,
  HakoniwaDigestHint,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { moodLevel } from "./hakoniwaLabels";

const GENERIC_HINTS = ["furniture", "talk", "transform"] as const;

interface HakoniwaDigestProps {
  /** overlay: 再生後に部屋へ重ねるカード / panel: 年代記の先頭 */
  variant: "overlay" | "panel";
}

/** 1日のまとめ(山場・大きく動いたこと・明日の予感)。文は種類と数値から組み立てる */
export default function HakoniwaDigest({ variant }: HakoniwaDigestProps) {
  const { t } = useTranslation();
  const { world, hideDigest, openAdv } = useHakoniwa();
  const digest = world?.last_digest;
  if (!world || !digest) return null;

  const names = new Map(world.residents.map((item) => [item.id, item.name]));
  const nameOf = (id: string) => names.get(id) ?? "?";
  const joinNames = (ids: string[]) =>
    ids.map(nameOf).join(t("hakoniwa.digest.and"));
  const highlight = digest.highlight;
  const highlightExists =
    highlight !== null &&
    world.events.some((event) => event.id === highlight.event_id);

  const changeText = (change: HakoniwaDigestChange): string => {
    if (change.type === "affinity") {
      return t("hakoniwa.digest.affinityChange", {
        names: joinNames(change.ids),
        delta: change.delta > 0 ? `+${change.delta}` : String(change.delta),
        value: change.value,
      });
    }
    return t(
      change.delta > 0 ? "hakoniwa.digest.moodUp" : "hakoniwa.digest.moodDown",
      {
        name: nameOf(change.id),
        label: t(`hakoniwa.residents.moodLabels.${moodLevel(change.mood)}`),
      },
    );
  };

  const hintText = (hint: HakoniwaDigestHint): string => {
    switch (hint.type) {
      case "swap":
        return t("hakoniwa.digest.hintSwap", {
          a: nameOf(hint.ids[0] ?? ""),
          b: nameOf(hint.ids[1] ?? ""),
        });
      case "near_close":
        return t("hakoniwa.digest.hintNearClose", {
          a: nameOf(hint.ids[0] ?? ""),
          b: nameOf(hint.ids[1] ?? ""),
          value: hint.value,
          remaining: hint.remaining,
        });
      case "no_rules":
        return t("hakoniwa.digest.hintNoRules");
      case "more_rules":
        return t("hakoniwa.digest.hintMoreRules", {
          remaining: hint.remaining,
        });
      default:
        return t(
          `hakoniwa.digest.hintGeneric.${GENERIC_HINTS[hint.index % GENERIC_HINTS.length] ?? "talk"}`,
        );
    }
  };

  const highlightReason = () => {
    if (!highlight) return "";
    if (highlight.reason === "transform") {
      return t("hakoniwa.digest.reasonTransform", {
        name: nameOf(highlight.participants[0] ?? ""),
      });
    }
    return t(`hakoniwa.digest.reason.${highlight.reason}`);
  };

  return (
    <section
      className={`hakoniwa-digest hakoniwa-digest--${variant}`}
      aria-label={t("hakoniwa.digest.title", { day: digest.day })}
    >
      <div className="hakoniwa-digest__head">
        <strong>{t("hakoniwa.digest.title", { day: digest.day })}</strong>
        {variant === "overlay" && (
          <button
            type="button"
            className="hakoniwa-icon-button"
            aria-label={t("hakoniwa.digest.close")}
            title={t("hakoniwa.digest.close")}
            onClick={hideDigest}
          >
            ×
          </button>
        )}
      </div>
      {highlight && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.highlight")}
          </span>
          <p>
            <strong>{highlight.title}</strong> — {highlightReason()}
          </p>
          {highlightExists && (
            <button
              type="button"
              className="hakoniwa-button hakoniwa-button--ghost"
              onClick={() => openAdv(highlight.event_id)}
            >
              ▶ {t("hakoniwa.chronicle.openAdv")}
            </button>
          )}
        </div>
      )}
      {digest.changes.length > 0 && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.changes")}
          </span>
          <ul>
            {digest.changes.map((change) => (
              <li
                key={`${change.type}:${"id" in change ? change.id : change.ids.join(",")}`}
              >
                {changeText(change)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="hakoniwa-digest__section">
        <span className="hakoniwa-digest__label">
          {t("hakoniwa.digest.tomorrow")}
        </span>
        <p>{hintText(digest.hint)}</p>
      </div>
    </section>
  );
}
