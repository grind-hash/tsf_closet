import { act, cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { SalonVisit } from "../../apis/salon";
import i18n from "../../i18n";
import { formatYen } from "../../utils/salonView";
import SalonReceipt from "./SalonReceipt";

function visit(overrides: Partial<SalonVisit> = {}): SalonVisit {
  return {
    id: "v",
    week: 1,
    slot: 0,
    customer: { source: "template", id: "char1", name: "サクラ" },
    session_id: null,
    status: "done",
    satisfaction: 85,
    fulfilled: true,
    payment: 75_000,
    reputation_delta: 5,
    review: "",
    visit_number: 1,
    previous_review: null,
    kept_look: true,
    returning_look: false,
    experience_bonus: 0,
    extra_cost: 0,
    ...overrides,
  };
}

function renderReceipt(target: SalonVisit, celebrate: boolean) {
  return render(
    <SalonReceipt
      visit={target}
      language="ja"
      celebrate={celebrate}
      cashTarget={createRef<HTMLElement>()}
    />,
  );
}

function mockReducedMotion(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

beforeAll(async () => {
  await i18n.changeLanguage("ja");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("SalonReceipt", () => {
  it("済んだ来店を開き直したときは、数え上げずに最終値を見せる", () => {
    renderReceipt(visit(), false);
    expect(screen.getByText("85%")).toBeTruthy();
    expect(screen.getByText(formatYen(75_000, "ja"))).toBeTruthy();
    expect(document.querySelector(".is-celebrating")).toBeNull();
    expect(document.querySelector(".salon-receipt__seal")?.textContent).toBe(
      "成就",
    );
  });

  it("会計した直後は、満足度とお支払いを 0 から数え上げる", () => {
    vi.useFakeTimers({
      toFake: [
        "setTimeout",
        "clearTimeout",
        "requestAnimationFrame",
        "cancelAnimationFrame",
        "performance",
      ],
    });
    renderReceipt(visit(), true);
    expect(screen.getByText("0%")).toBeTruthy();
    expect(screen.getByText(formatYen(0, "ja"))).toBeTruthy();
    expect(document.querySelector(".is-celebrating")).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("85%")).toBeTruthy();
    expect(screen.getByText(formatYen(75_000, "ja"))).toBeTruthy();
  });

  it("動きを減らす設定のときは、会計した直後でも最終値を見せる", () => {
    mockReducedMotion(true);
    renderReceipt(visit(), true);
    expect(screen.getByText("85%")).toBeTruthy();
    expect(screen.getByText(formatYen(75_000, "ja"))).toBeTruthy();
    expect(document.querySelector(".salon-payment-chip")).toBeNull();
  });

  it("チップと指名料があれば、お支払いの内訳に行を足す", () => {
    renderReceipt(
      visit({ payment: 125_000, tip: 30_000, regular_fee: 20_000 }),
      false,
    );
    expect(screen.getByText("評判のチップ")).toBeTruthy();
    expect(screen.getByText("常連の指名料")).toBeTruthy();
    expect(screen.getByText(formatYen(125_000, "ja"))).toBeTruthy();
    expect(screen.queryByText("満点の仕上がり")).toBeNull();
  });

  it("満点の仕上がりは施術料を内訳に出し、上乗せが無い来店には内訳を出さない", () => {
    renderReceipt(
      visit({ satisfaction: 100, payment: 110_000, tip: 10_000 }),
      false,
    );
    expect(screen.getByText("満点の仕上がり")).toBeTruthy();
    expect(screen.getByText(formatYen(100_000, "ja"))).toBeTruthy();
    cleanup();
    renderReceipt(visit(), false);
    expect(screen.queryByText("評判のチップ")).toBeNull();
    expect(screen.queryByText("常連の指名料")).toBeNull();
  });

  it("願いに届かなかったときは封蝋を押さない", () => {
    renderReceipt(
      visit({ fulfilled: false, satisfaction: 40, kept_look: false }),
      false,
    );
    expect(document.querySelector(".salon-receipt__seal")).toBeNull();
    expect(screen.getByText("願いにはあと一歩でした")).toBeTruthy();
  });
});
