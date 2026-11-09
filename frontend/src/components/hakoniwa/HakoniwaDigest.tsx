import { useTranslation } from "react-i18next";
import type {
  HakoniwaDigestArc,
  HakoniwaDigestChange,
  HakoniwaDigestHint,
  HakoniwaDissonanceStage,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import {
  adaptationStageKey,
  arcTitle,
  moodLevel,
  worldStageKey,
} from "./hakoniwaLabels";

const GENERIC_HINTS = ["furniture", "talk", "transform"] as const;

interface HakoniwaDigestProps {
  /** overlay: 再生後に部屋へ重ねるカード / panel: 年代記の先頭 */
  variant: "overlay" | "panel";
}

/**
 * 1日のまとめ(山場・大きく動いたこと・適応の進展・続いている物語・世界の違和感・明日の予感)。
 * 文は種類と数値から組み立てる。
 */
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
  const adaptations = digest.adaptations ?? [];
  const worldAdaptations = digest.world_adaptations ?? [];
  const arcs = digest.arcs ?? [];
  const dissonance = digest.dissonance ?? null;
  const stageName = (stage: HakoniwaDissonanceStage) =>
    t(`hakoniwa.story.dissonanceStage.${stage}`);

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
      case "acknowledged":
        return t("hakoniwa.digest.hintAcknowledged");
      case "dissonance_near":
        return t("hakoniwa.digest.hintDissonanceNear", {
          stage: stageName(hint.stage),
          remaining: hint.remaining,
        });
      case "arc_near_climax":
        return t("hakoniwa.digest.hintArcNearClimax", {
          title: arcTitle(t, hint.kind, hint.ids, nameOf),
        });
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

  const arcStatus = (arc: HakoniwaDigestArc): string => {
    if (arc.status === "started") return t("hakoniwa.digest.arcStarted");
    if (arc.status === "climax") return t("hakoniwa.digest.arcClimax");
    if (arc.status === "faded") return t("hakoniwa.digest.arcFaded");
    if (arc.status === "resolved") return t("hakoniwa.digest.arcResolved");
    const remaining = Math.max(arc.beats - arc.progress, 0);
    return remaining <= 1
      ? t("hakoniwa.digest.arcNearClimax")
      : t("hakoniwa.digest.arcRemaining", { remaining });
  };

  const dissonanceTail = () => {
    if (!dissonance) return "";
    if (dissonance.acknowledged) {
      return ` ${t("hakoniwa.digest.dissonanceAcknowledged")}`;
    }
    if (dissonance.next_stage && dissonance.remaining !== null) {
      return ` ${t("hakoniwa.digest.dissonanceNext", {
        stage: stageName(dissonance.next_stage),
        remaining: dissonance.remaining,
      })}`;
    }
    return "";
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
      {(adaptations.length > 0 || worldAdaptations.length > 0) && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.adaptations")}
          </span>
          <ul>
            {adaptations.map((item) => (
              <li key={`self:${item.id}`}>
                {t("hakoniwa.digest.adaptationSelf", {
                  name: nameOf(item.id),
                  subject: t(`hakoniwa.story.subject.${item.kind}`),
                  stage: t(
                    `hakoniwa.story.adaptationStage.${adaptationStageKey(item.stage)}`,
                  ),
                })}
              </li>
            ))}
            {worldAdaptations.map((item) => (
              <li key={`world:${item.ids.join(",")}`}>
                {t("hakoniwa.digest.adaptationWorld", {
                  names: joinNames(item.ids),
                  subject: t(`hakoniwa.story.subject.${item.kind}`),
                  stage: t(
                    `hakoniwa.story.worldStage.${worldStageKey(item.stage)}`,
                  ),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
      {arcs.length > 0 && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.arcs")}
          </span>
          <ul>
            {arcs.map((arc) => (
              <li key={arc.id}>
                {t("hakoniwa.digest.arcLine", {
                  title: arcTitle(t, arc.kind, arc.ids, nameOf),
                  status: arcStatus(arc),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
      {dissonance && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.dissonance")}
          </span>
          <p>
            {t("hakoniwa.digest.dissonanceChange", {
              fromStage: stageName(dissonance.from_stage),
              from: dissonance.from,
              toStage: stageName(dissonance.to_stage),
              to: dissonance.to,
            })}
            {dissonanceTail()}
          </p>
        </div>
      )}
      {digest.intervention && (
        <div className="hakoniwa-digest__section">
          <span className="hakoniwa-digest__label">
            {t("hakoniwa.digest.intervention")}
          </span>
          <p>{t(`hakoniwa.intervention.result.${digest.intervention}`)}</p>
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
