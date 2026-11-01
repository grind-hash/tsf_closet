import { describe, expect, it } from "vitest";
import type { SalonRun, SalonVisit } from "../apis/salon";
import type { HistoryItem, SessionRequestView } from "../types";
import {
  formatSignedNumber,
  formatSignedYen,
  formatYen,
  initialSalonAct,
  isExperienceTurn,
  lastStyledHistory,
  salonCashSeries,
  salonCashTicks,
  salonReviews,
  thisWeekVisits,
} from "./salonView";

function visit(overrides: Partial<SalonVisit>): SalonVisit {
  return {
    id: "v",
    week: 1,
    slot: 0,
    customer: { source: "template", id: "char1", name: "サクラ" },
    session_id: null,
    status: "booked",
    satisfaction: null,
    fulfilled: false,
    payment: 0,
    reputation_delta: 0,
    review: null,
    visit_number: 1,
    previous_review: null,
    kept_look: false,
    returning_look: false,
    experience_bonus: 0,
    ...overrides,
  };
}

function run(overrides: Partial<SalonRun>): SalonRun {
  return {
    id: "run",
    name: "店",
    status: "active",
    week: 2,
    total_weeks: 12,
    cash: 2_000_000,
    reputation: 20,
    difficulty: "normal",
    initial_cash: 2_000_000,
    sensitive: false,
    weekly_fixed_cost: 300_000,
    weekly_salary: 100_000,
    base_price: 50_000,
    turn_limit: 3,
    question_limit: 2,
    visits: [],
    weeks: [],
    result: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

describe("formatYen", () => {
  it("uses 万円 in Japanese and full yen in English", () => {
    expect(formatYen(3_000_000, "ja")).toBe("300万円");
    expect(formatYen(75_000, "ja")).toBe("7.5万円");
    expect(formatYen(3_000_000, "en")).toBe("¥3,000,000");
  });

  it("signs changes", () => {
    expect(formatSignedYen(75_000, "ja")).toBe("+7.5万円");
    expect(formatSignedYen(-100_000, "ja")).toBe("−10万円");
    expect(formatSignedYen(0, "en")).toBe("±¥0");
    expect(formatSignedNumber(8)).toBe("+8");
    expect(formatSignedNumber(-3)).toBe("−3");
    expect(formatSignedNumber(0)).toBe("±0");
  });
});

describe("visits and reviews", () => {
  const visits = [
    visit({ id: "old", week: 1, status: "done", review: "前の週" }),
    visit({ id: "b", week: 2, slot: 1 }),
    visit({ id: "a", week: 2, slot: 0, status: "done", review: "今週" }),
    visit({ id: "declined", week: 2, slot: 2, status: "declined" }),
  ];

  it("lists this week's bookings in slot order", () => {
    expect(thisWeekVisits(run({ visits })).map((item) => item.id)).toEqual([
      "a",
      "b",
      "declined",
    ]);
  });

  it("lists reviews newest first", () => {
    expect(salonReviews(run({ visits })).map((item) => item.id)).toEqual([
      "a",
      "old",
    ]);
  });
});

describe("initialSalonAct", () => {
  it("resumes styling once a turn has been used", () => {
    expect(initialSalonAct(null)).toBe("counsel");
    expect(
      initialSalonAct({ turns_used: 0 } as unknown as SessionRequestView),
    ).toBe("counsel");
    expect(
      initialSalonAct({ turns_used: 1 } as unknown as SessionRequestView),
    ).toBe("styling");
  });
});

describe("experience turn", () => {
  const item = (id: string, instructionType?: string): HistoryItem => ({
    id,
    instruction: "",
    imageUrl: `/img/${id}.png`,
    feelingText: "",
    beforeDescription: "",
    afterDescription: "",
    timestamp: "",
    instructionType,
  });

  it("finds the last styled look before the experience scene", () => {
    const history = [
      item("start"),
      item("styled", "dress_up"),
      item("experience", "action"),
    ];
    expect(isExperienceTurn(history.at(-1))).toBe(true);
    expect(lastStyledHistory(history)?.id).toBe("styled");
    expect(lastStyledHistory(history.slice(0, 2))?.id).toBe("styled");
    expect(lastStyledHistory([])).toBeUndefined();
  });
});

describe("cash chart", () => {
  it("starts from the opening funds", () => {
    const series = salonCashSeries(
      run({
        weeks: [
          {
            week: 1,
            revenue: 0,
            salary: 100_000,
            fixed_cost: 300_000,
            served: 0,
            declined: 1,
            cash_end: 1_800_000,
            reputation_end: 17,
          },
        ],
      }),
    );
    expect(series).toEqual([
      { week: 0, cash: 2_000_000 },
      { week: 1, cash: 1_800_000 },
    ]);
  });

  it("ticks cover zero and negative cash on clean steps", () => {
    const ticks = salonCashTicks([
      { week: 0, cash: 1_500_000 },
      { week: 8, cash: -100_000 },
    ]);
    expect(ticks[0]).toBeLessThanOrEqual(-100_000);
    expect(ticks).toContain(0);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(1_500_000);
    const steps = new Set(ticks.slice(1).map((tick, i) => tick - ticks[i]));
    expect(steps.size).toBe(1);
  });
});
