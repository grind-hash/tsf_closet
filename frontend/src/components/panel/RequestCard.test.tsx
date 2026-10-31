import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import i18n from "../../i18n";
import type { SessionRequestView } from "../../types";
import RequestCard from "./RequestCard";

const mocks = vi.hoisted(() => ({
  generateRequest: vi.fn(),
  state: {
    sessionId: "s1",
    isTransforming: false,
    request: null as SessionRequestView | null,
    requestGenerating: false,
    requestError: null as string | null,
  },
}));

vi.mock("../../contexts/GameContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../contexts/GameContext")>()),
  useGame: () => ({
    state: mocks.state,
    generateRequest: mocks.generateRequest,
  }),
}));

const REQUEST: SessionRequestView = {
  wish: "舞踏会のお姫様になってみたい",
  status: "active",
  satisfaction: 60,
  threshold: 80,
  fit: "good",
  hint: "色合いが少し気になっているようです",
  preferences: [
    { id: "p1", hint: "色合い", text: null, met: false },
    { id: "p2", hint: "丈", text: "膝より長い丈", met: true },
  ],
  evaluated_turns: 1,
  can_regenerate: false,
};

describe("RequestCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ja");
    mocks.generateRequest.mockReset();
    mocks.state.request = null;
    mocks.state.requestGenerating = false;
    mocks.state.requestError = null;
  });

  afterEach(() => cleanup());

  it("依頼の無いセッションでは何も描かない", () => {
    const { container } = render(<RequestCard />);
    expect(container.innerHTML).toBe("");
  });

  it("生成中はスピナー付きの進捗として表示する", () => {
    mocks.state.requestGenerating = true;
    render(<RequestCard />);
    expect(screen.getByRole("status").textContent).toContain(
      "依頼を考えています",
    );
  });

  it("願い・満足度・未開示の好みの分類・ヒントを出す", () => {
    mocks.state.request = REQUEST;
    render(<RequestCard />);
    expect(screen.getByText(REQUEST.wish)).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe(
      "60",
    );
    // 伏せた好みは分類だけ、開示済みは本文を出す
    expect(screen.getByText("？？？（色合い）")).toBeTruthy();
    expect(screen.getByText("膝より長い丈")).toBeTruthy();
    expect(screen.getByText(/色合いが少し気になっている/)).toBeTruthy();
    // 最初の着せ替えの後は作り直せない
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("最初の着せ替え前は作り直し、失敗時はもう一度作れる", () => {
    mocks.state.request = {
      ...REQUEST,
      evaluated_turns: 0,
      can_regenerate: true,
    };
    const { rerender } = render(<RequestCard />);
    fireEvent.click(screen.getByRole("button", { name: "別の依頼にする" }));
    expect(mocks.generateRequest).toHaveBeenCalledWith("s1");

    mocks.state.request = null;
    mocks.state.requestError = "依頼を作れませんでした";
    rerender(<RequestCard />);
    fireEvent.click(screen.getByRole("button", { name: "もう一度依頼を作る" }));
    expect(mocks.generateRequest).toHaveBeenCalledTimes(2);
  });
});
