import type { HakoniwaEvent, HakoniwaResident } from "../../apis/hakoniwa";

/** 指示した出来事に本人と一緒に出られる住民の上限(バックエンドと同じ) */
export const EVENT_PARTNERS_MAX = 2;
/** 出来事の指示文の上限(バックエンドと同じ) */
export const EVENT_TEXT_MAX = 500;

/**
 * 続きを指示できる出来事か。今日の出来事で、参加者がまだ住んでいるもの
 * (前の日の出来事は、住民の姿や居場所が変わっているため続けられない)
 */
export function canContinueEvent(
  event: Pick<HakoniwaEvent, "day" | "participants">,
  day: number,
  residents: HakoniwaResident[],
): boolean {
  return (
    event.day === day &&
    event.participants.some((id) => residents.some((item) => item.id === id))
  );
}

/** 本人と同じ部屋にいるほかの住民 */
export function roomMates(
  residents: HakoniwaResident[],
  target: HakoniwaResident,
): HakoniwaResident[] {
  return residents.filter(
    (item) =>
      item.id !== target.id && item.current_area === target.current_area,
  );
}

/** 選んだ住民の id を、いる住民・本人以外・上限までに絞って住民にする(選んだ順) */
export function chosenPartners(
  residents: HakoniwaResident[],
  targetId: string,
  ids: string[],
): HakoniwaResident[] {
  const picked: HakoniwaResident[] = [];
  for (const id of ids) {
    if (id === targetId || picked.some((item) => item.id === id)) continue;
    const resident = residents.find((item) => item.id === id);
    if (resident) picked.push(resident);
    if (picked.length >= EVENT_PARTNERS_MAX) break;
  }
  return picked;
}

/** チップを押したときの選択。選び済みなら外し、上限に達していれば変えない */
export function togglePartner(ids: string[], id: string): string[] {
  if (ids.includes(id)) return ids.filter((item) => item !== id);
  if (ids.length >= EVENT_PARTNERS_MAX) return ids;
  return [...ids, id];
}

/** いま見えている体がどちらも男性の組(TS で女性の体になった住民は含まない) */
export function maleBodyPairs(
  cast: HakoniwaResident[],
): [HakoniwaResident, HakoniwaResident][] {
  const males = cast.filter((item) => item.body_gender === "male");
  return males.flatMap((a, index) =>
    males
      .slice(index + 1)
      .map((b): [HakoniwaResident, HakoniwaResident] => [a, b]),
  );
}
