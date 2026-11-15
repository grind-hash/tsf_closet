import type {
  HakoniwaPlayerPresence,
  HakoniwaWorldSummary,
} from "../../apis/hakoniwa";

/** 世界の一覧の絞り込み。住民とあなた(すべて / 顔なじみ / 見えない存在)と住民の名前 */
export interface HakoniwaWorldFilter {
  presence: "all" | HakoniwaPlayerPresence;
  /** この名前の住民がいる世界だけ。null はすべて */
  resident: string | null;
}

export const ALL_WORLDS: HakoniwaWorldFilter = {
  presence: "all",
  resident: null,
};

export function worldPresence(
  world: HakoniwaWorldSummary,
): HakoniwaPlayerPresence {
  return world.player_presence ?? "known";
}

/** 住民全員の名前(古い応答では顔を出す先頭の数人だけになる) */
export function worldResidentNames(world: HakoniwaWorldSummary): string[] {
  return world.resident_names ?? world.residents.map((item) => item.name);
}

function matchesPresence(
  world: HakoniwaWorldSummary,
  presence: HakoniwaWorldFilter["presence"],
) {
  return presence === "all" || worldPresence(world) === presence;
}

function matchesResident(world: HakoniwaWorldSummary, resident: string | null) {
  return resident === null || worldResidentNames(world).includes(resident);
}

export function filterWorlds(
  worlds: HakoniwaWorldSummary[],
  filter: HakoniwaWorldFilter,
): HakoniwaWorldSummary[] {
  return worlds.filter(
    (world) =>
      matchesPresence(world, filter.presence) &&
      matchesResident(world, filter.resident),
  );
}

export interface HakoniwaWorldFacetCounts {
  presence: Record<HakoniwaWorldFilter["presence"], number>;
  /** 住民の名前と、その住民がいる世界の数(多い順、同数は名前順) */
  residents: { name: string; count: number }[];
}

/**
 * 絞り込みのチップに添える件数。片方の絞り込みの件数は、もう片方の絞り込みを効かせた
 * うえで数える(押すと 0 件になるチップを作らない)。
 */
export function worldFacetCounts(
  worlds: HakoniwaWorldSummary[],
  filter: HakoniwaWorldFilter,
): HakoniwaWorldFacetCounts {
  const byResident = worlds.filter((world) =>
    matchesResident(world, filter.resident),
  );
  const presence = { all: byResident.length, known: 0, hidden: 0 };
  for (const world of byResident) presence[worldPresence(world)] += 1;

  const counts = new Map<string, number>();
  for (const world of worlds) {
    if (!matchesPresence(world, filter.presence)) continue;
    for (const name of new Set(worldResidentNames(world))) {
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  const residents = [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "ja"));
  return { presence, residents };
}
