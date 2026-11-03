import { describe, expect, it } from "vitest";
import type { SalonRun, SalonVisit, SalonWeek } from "../apis/salon";
import type { HistoryItem, SessionRequestView } from "../types";
import {
  buildOpeningCutscene,
  buildWeekCutscene,
  formatSignedNumber,
  formatSignedYen,
  formatYen,
  initialSalonAct,
  isAdultSalonTurn,
  isExperienceTurn,
  lastStyledHistory,
  salonCashSeries,
  salonCashTicks,
  salonPreferenceChips,
  salonReviews,
  salonSatisfactionDelta,
  settleExperience,
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
    extra_cost: 0,
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
    season_length: "standard",
    season_weeks: 12,
    season: 1,
    season_start_week: 1,
    season_start_cash: 2_000_000,
    seasons: [],
    sensitive: false,
    extra_turn_price: 50_000,
    extra_turns_max: 1,
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

function request(overrides: Partial<SessionRequestView>): SessionRequestView {
  return {
    wish: "ふんわりした姿に",
    status: "active",
    satisfaction: 0,
    threshold: 70,
    fit: null,
    hint: "",
    preferences: [
      { id: "p1", hint: "色合い", text: null, met: false },
      { id: "p2", hint: "丈", text: "膝より長い丈", met: true },
      { id: "p3", hint: "", text: null, met: false },
    ],
    evaluated_turns: 0,
    turn_limit: 3,
    turns_used: 0,
    turns_remaining: 3,
    question_limit: 2,
    questions: [],
    questions_remaining: 2,
    listening_bonus: 0,
    can_regenerate: true,
    ...overrides,
  };
}

describe("salon request chart", () => {
  it("カルテは分類と叶えた印を並べ、施術後だけ注目の印を付ける", () => {
    const before = salonPreferenceChips(
      request({
        focus_preference_id: "p1",
        questions: [
          {
            question: "色は？",
            answer: "淡い色",
            reflected: false,
            target_id: "p1",
          },
        ],
      }),
      { showFocus: true },
    );
    expect(before.map((chip) => chip.category)).toEqual(["色合い", "丈", "？"]);
    expect(before.map((chip) => chip.asked)).toEqual([true, false, false]);
    // まだ施術していないので、ヒントが指す好みは無い
    expect(before.some((chip) => chip.focus)).toBe(false);

    const styled = request({ evaluated_turns: 1, focus_preference_id: "p1" });
    expect(
      salonPreferenceChips(styled, { showFocus: true }).map(
        (chip) => chip.focus,
      ),
    ).toEqual([true, false, false]);
    // 追加施術の手番ではヒントを見せない
    expect(
      salonPreferenceChips(styled, { showFocus: false }).some(
        (chip) => chip.focus,
      ),
    ).toBe(false);
    expect(salonPreferenceChips(null, { showFocus: true })).toEqual([]);
  });

  it("満足度の増減は2手目の施術から出す", () => {
    expect(salonSatisfactionDelta(null)).toBeNull();
    expect(
      salonSatisfactionDelta(
        request({
          evaluated_turns: 1,
          satisfaction: 40,
          previous_satisfaction: null,
        }),
      ),
    ).toBeNull();
    expect(
      salonSatisfactionDelta(
        request({
          evaluated_turns: 2,
          satisfaction: 52,
          previous_satisfaction: 60,
        }),
      ),
    ).toBe(-8);
    expect(
      salonSatisfactionDelta(
        request({
          evaluated_turns: 3,
          satisfaction: 72,
          previous_satisfaction: 60,
        }),
      ),
    ).toBe(12);
  });
});

describe("isAdultSalonTurn", () => {
  const sensitive = { sensitive: true } as unknown as SessionRequestView;
  const allAges = { sensitive: false } as unknown as SessionRequestView;

  it("draws adult only for an explicit request while NSFW mode is on", () => {
    expect(isAdultSalonTurn(sensitive, true)).toBe(true);
    expect(isAdultSalonTurn(sensitive, false)).toBe(false);
    expect(isAdultSalonTurn(allAges, true)).toBe(false);
    expect(isAdultSalonTurn(null, true)).toBe(false);
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

  it("settles from the refetched history when it has arrived", () => {
    const history = [
      item("start"),
      item("styled", "dress_up"),
      { ...item("experience", "action"), feelingText: "saved" },
    ];
    expect(
      settleExperience({
        history,
        baseLength: 2,
        baseImage: "/img/styled.png",
        currentImage: "/img/experience.png",
        feelingText: "streamed",
      }),
    ).toEqual({
      status: "done",
      image: "/img/experience.png",
      feeling: "saved",
    });
  });

  // 実際の不具合: 履歴の取り直しより先に手番の終了が届き、生成済みなのに失敗と出ていた
  it("settles from the received image before the history is refetched", () => {
    const history = [item("start"), item("styled", "dress_up")];
    expect(
      settleExperience({
        history,
        baseLength: 2,
        baseImage: "/img/styled.png",
        currentImage: "/history/images/experience",
        feelingText: "streamed",
      }),
    ).toEqual({
      status: "done",
      image: "/history/images/experience",
      feeling: "streamed",
    });
  });

  it("fails when no image arrived", () => {
    const history = [item("start"), item("styled", "dress_up")];
    expect(
      settleExperience({
        history,
        baseLength: 2,
        baseImage: "/img/styled.png",
        currentImage: "/img/styled.png",
        feelingText: "",
      }).status,
    ).toBe("failed");
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

describe("buildWeekCutscene", () => {
  function week(overrides: Partial<SalonWeek>): SalonWeek {
    return {
      week: 1,
      revenue: 0,
      extra_cost: 0,
      salary: 100_000,
      fixed_cost: 300_000,
      served: 0,
      declined: 0,
      cash_end: 1_800_000,
      reputation_end: 20,
      ...overrides,
    };
  }

  it("第1週は開業資金と、今週の接客の分を戻した評判から始める", () => {
    const before = run({
      week: 1,
      cash: 2_075_000,
      reputation: 25,
      visits: [
        visit({
          id: "a",
          status: "done",
          payment: 75_000,
          reputation_delta: 8,
        }),
        visit({ id: "b", slot: 1, status: "declined", reputation_delta: -3 }),
      ],
    });
    const closedWeek = week({
      revenue: 75_000,
      served: 1,
      declined: 1,
      cash_end: 1_875_000,
      reputation_end: 25,
    });
    const scene = buildWeekCutscene(before, {
      run: run({
        week: 2,
        cash: 1_875_000,
        reputation: 25,
        weeks: [closedWeek],
        visits: [
          ...before.visits,
          visit({ id: "c", week: 2, status: "booked" }),
          visit({
            id: "d",
            week: 2,
            slot: 1,
            status: "booked",
            returning_look: true,
            customer: { source: "template", id: "char2", name: "ミナ" },
          }),
        ],
      }),
      achievements: [],
    });
    expect(scene).toMatchObject({
      week: closedWeek,
      cashStart: 2_000_000,
      cashDelta: -125_000,
      reputationStart: 20,
      nextWeek: 2,
      bookings: 2,
      regulars: ["ミナ"],
      result: null,
    });
  });

  it("2週目以降は前週末の現金と評判から始める", () => {
    const weeks = [
      week({ week: 1, cash_end: 1_800_000, reputation_end: 30 }),
      week({ week: 2, cash_end: 1_700_000, reputation_end: 27 }),
    ];
    const scene = buildWeekCutscene(run({ week: 2, reputation: 30 }), {
      run: run({ week: 3, weeks }),
      achievements: [],
    });
    expect(scene?.cashStart).toBe(1_800_000);
    expect(scene?.cashDelta).toBe(-100_000);
    expect(scene?.reputationStart).toBe(30);
  });

  it.each([
    "success",
    "partial",
    "bankrupt",
  ] as const)("決算(%s)では翌週を出さず、結果と実績を渡す", (outcome) => {
    const achievement = {
      achievement_id: "salon_first_season",
      name: "はじめての決算",
      description: "",
      icon: "🪞",
      category: "salon",
    };
    const scene = buildWeekCutscene(run({ week: 12 }), {
      run: run({
        week: 12,
        status: outcome === "bankrupt" ? "bankrupt" : "completed",
        weeks: [week({ week: 12 })],
        visits: [visit({ week: 12, status: "done" })],
        result: { outcome, cash: 0, profit: 0 },
      }),
      achievements: [achievement],
    });
    expect(scene?.nextWeek).toBeNull();
    expect(scene?.bookings).toBe(0);
    expect(scene?.result?.outcome).toBe(outcome);
    expect(scene?.achievements).toEqual([achievement]);
  });

  it("期中の倒産も決算として扱う", () => {
    const scene = buildWeekCutscene(run({ week: 4 }), {
      run: run({
        week: 4,
        status: "bankrupt",
        weeks: [week({ week: 4, cash_end: -50_000 })],
        result: { outcome: "bankrupt", cash: -50_000 },
      }),
      achievements: [],
    });
    expect(scene?.nextWeek).toBeNull();
    expect(scene?.result?.outcome).toBe("bankrupt");
  });

  it("帳簿が無ければ null", () => {
    expect(
      buildWeekCutscene(run({}), { run: run({ weeks: [] }), achievements: [] }),
    ).toBeNull();
  });
});

describe("buildOpeningCutscene", () => {
  it("開業資金・毎週の収支・評判と、開業した週の予約数を渡す", () => {
    const scene = buildOpeningCutscene(
      run({
        name: "Le Rêve Secret",
        week: 1,
        initial_cash: 1_500_000,
        cash: 1_500_000,
        reputation: 20,
        visits: [
          visit({ id: "a", status: "booked" }),
          visit({ id: "b", slot: 1, status: "declined" }),
          visit({ id: "c", week: 2, status: "booked" }),
        ],
      }),
    );
    expect(scene).toEqual({
      kind: "opening",
      name: "Le Rêve Secret",
      week: 1,
      totalWeeks: 12,
      initialCash: 1_500_000,
      reputation: 20,
      weeklySalary: 100_000,
      weeklyFixedCost: 300_000,
      bookings: 1,
    });
  });
});
