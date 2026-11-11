import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type HakoniwaEventScope,
  type HakoniwaResident,
  hakoniwaMediaUrl,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import {
  chosenPartners,
  EVENT_PARTNERS_MAX,
  EVENT_TEXT_MAX,
  maleBodyPairs,
  roomMates,
  togglePartner,
} from "./eventCast";
import HakoniwaPortrait from "./HakoniwaPortrait";

const SCOPES: HakoniwaEventScope[] = ["solo", "selected", "room"];
const SCOPE_LABEL_KEYS = {
  solo: "hakoniwa.panel.scopeSolo",
  selected: "hakoniwa.panel.scopeSelected",
  room: "hakoniwa.panel.scopeRoom",
} as const;

interface HakoniwaEventComposerProps {
  resident: HakoniwaResident;
}

/** 住民パネルの「出来事」: 指示と巻き込み方を選び、いまの姿のまま場面を1つ起こす */
export default function HakoniwaEventComposer({
  resident,
}: HakoniwaEventComposerProps) {
  const { t } = useTranslation();
  const { world, busy, playbackQueue, directEvent } = useHakoniwa();
  const inputId = useId();
  const scopeLabelId = useId();
  const partnersLabelId = useId();
  const locationId = useId();
  // 住民を切り替えても書きかけの指示と選んだ相手を残す
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [partnerIds, setPartnerIds] = useState<Record<string, string[]>>({});
  const [scope, setScope] = useState<HakoniwaEventScope>("solo");
  // 出来事の場所(null はおまかせ: 内容に合う場所を生成が選ぶ)
  const [location, setLocation] = useState<string | null>(null);

  if (!world) return null;
  const draft = drafts[resident.id] ?? "";
  const partners = chosenPartners(
    world.residents,
    resident.id,
    partnerIds[resident.id] ?? [],
  );
  const mates = roomMates(world.residents, resident);
  const candidates = world.residents.filter((item) => item.id !== resident.id);
  const cast =
    scope === "selected"
      ? [resident, ...partners]
      : scope === "room"
        ? [resident, ...mates]
        : [resident];
  const malePairs = maleBodyPairs(cast);
  const locked = busy !== null || playbackQueue.length > 0;
  const castReady =
    (scope !== "selected" || partners.length > 0) &&
    (scope !== "room" || mates.length > 0);
  const join = (items: string[]) => items.join(t("hakoniwa.panel.listJoin"));
  const pairsText = join(
    malePairs.map(
      ([a, b]) => `${a.name}${t("hakoniwa.panel.pairJoin")}${b.name}`,
    ),
  );

  const handlePartner = (id: string) => {
    setPartnerIds((current) => ({
      ...current,
      [resident.id]: togglePartner(
        partners.map((item) => item.id),
        id,
      ),
    }));
  };

  const handleRun = () => {
    const instruction = draft.trim();
    if (!instruction || !castReady) return;
    void directEvent(resident.id, {
      instruction,
      scope,
      partnerIds: partners.map((item) => item.id),
      location,
    });
  };

  return (
    <>
      <label htmlFor={inputId}>
        <strong>{t("hakoniwa.panel.eventHeading")}</strong>
      </label>
      <textarea
        id={inputId}
        rows={3}
        maxLength={EVENT_TEXT_MAX}
        value={draft}
        placeholder={t("hakoniwa.panel.eventPlaceholder")}
        onChange={(event) =>
          setDrafts((current) => ({
            ...current,
            [resident.id]: event.target.value,
          }))
        }
      />
      <span id={scopeLabelId} className="hakoniwa-resident__subheading">
        {t("hakoniwa.panel.eventScopeLabel")}
      </span>
      <div
        className="hakoniwa-segments hakoniwa-directive__scope"
        role="group"
        aria-labelledby={scopeLabelId}
      >
        {SCOPES.map((option) => (
          <button
            key={option}
            type="button"
            className={scope === option ? "is-active" : undefined}
            aria-pressed={scope === option}
            onClick={() => setScope(option)}
          >
            {t(SCOPE_LABEL_KEYS[option])}
          </button>
        ))}
      </div>
      {scope === "selected" && (
        <>
          <span id={partnersLabelId} className="hakoniwa-resident__subheading">
            {t("hakoniwa.panel.partnersLabel", { max: EVENT_PARTNERS_MAX })}
          </span>
          <div
            className="hakoniwa-directive__chips"
            role="group"
            aria-labelledby={partnersLabelId}
          >
            {candidates.map((item) => {
              const chosen = partners.some((partner) => partner.id === item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`hakoniwa-areas__chip${chosen ? " is-active" : ""}`}
                  aria-pressed={chosen}
                  disabled={!chosen && partners.length >= EVENT_PARTNERS_MAX}
                  onClick={() => handlePartner(item.id)}
                >
                  <HakoniwaPortrait
                    src={hakoniwaMediaUrl(item.display_avatar_url)}
                    alt=""
                    className="hakoniwa-directive__face"
                  />
                  {item.name}
                </button>
              );
            })}
          </div>
          <p className="hakoniwa-note">
            {partners.length > 0
              ? t("hakoniwa.panel.partnersNote", { name: resident.name })
              : t("hakoniwa.panel.partnersEmpty")}
          </p>
        </>
      )}
      {scope === "room" && (
        <p className="hakoniwa-note">
          {mates.length === 0
            ? t("hakoniwa.panel.roomEmpty")
            : t(
                mates.length > EVENT_PARTNERS_MAX
                  ? "hakoniwa.panel.roomRandom"
                  : "hakoniwa.panel.roomMembers",
                {
                  names: join(mates.map((item) => item.name)),
                  max: EVENT_PARTNERS_MAX,
                },
              )}
        </p>
      )}
      {/* 場所は12か所あり、チップで並べるとパネルを押し下げるため、1行のプルダウンにする */}
      <div className="hakoniwa-directive__place">
        <label htmlFor={locationId} className="hakoniwa-resident__subheading">
          {t("hakoniwa.panel.locationLabel")}
        </label>
        <select
          id={locationId}
          value={location ?? ""}
          onChange={(event) => setLocation(event.target.value || null)}
        >
          <option value="">{t("hakoniwa.panel.locationAuto")}</option>
          {world.locations.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      {malePairs.length > 0 && (
        <p className="hakoniwa-note">
          {t("hakoniwa.panel.maleBodyNote", { pairs: pairsText })}
        </p>
      )}
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--primary"
        onClick={handleRun}
        disabled={!draft.trim() || !castReady || locked}
      >
        {busy === "event" ? (
          <>
            <span className="hakoniwa-spinner" aria-hidden />
            {t("hakoniwa.panel.runningEvent")}
          </>
        ) : (
          t("hakoniwa.panel.runEvent")
        )}
      </button>
      <p className="hakoniwa-note">{t("hakoniwa.panel.eventNote")}</p>
    </>
  );
}
