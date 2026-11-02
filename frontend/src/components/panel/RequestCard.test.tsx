import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import i18n from "../../i18n";
import type { SessionRequestView } from "../../types";
import RequestCard from "./RequestCard";

const mocks = vi.hoisted(() => ({
  generateRequest: vi.fn(),
  askRequestQuestion: vi.fn(),
  state: {
    sessionId: "s1",
    isTransforming: false,
    request: null as SessionRequestView | null,
    requestGenerating: false,
    requestError: null as string | null,
    requestTurnLimit: null as number | null,
  },
}));

vi.mock("../../contexts/GameContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../contexts/GameContext")>()),
  useGame: () => ({
    state: mocks.state,
    generateRequest: mocks.generateRequest,
    askRequestQuestion: mocks.askRequestQuestion,
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
  turn_limit: 3,
  turns_used: 1,
  turns_remaining: 2,
  question_limit: 2,
  questions: [
    {
      question: "好きな色は？",
      answer: "春の花みたいな色かな",
      reflected: true,
    },
  ],
  questions_remaining: 1,
  listening_bonus: 10,
  can_regenerate: false,
};

describe("RequestCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ja");
    mocks.generateRequest.mockReset();
    mocks.askRequestQuestion.mockReset();
    mocks.state.request = null;
    mocks.state.requestTurnLimit = null;
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
    // 施術の残り手数とカウンセリングのやり取り
    expect(screen.getByText("2 / 3 手")).toBeTruthy();
    expect(screen.getByText("春の花みたいな色かな")).toBeTruthy();
    // ヒアリングを汲んだ加点と、汲んだ答えの印
    expect(screen.getByText(/ヒアリングの反映 \+10/)).toBeTruthy();
    expect(screen.getByText("反映")).toBeTruthy();
    expect(screen.getByText("あと 1 回質問できます")).toBeTruthy();
    // 最初の着せ替えの後は作り直せない
    expect(screen.queryByRole("button", { name: "別の依頼にする" })).toBeNull();
  });

  it("質問を送ると入力欄を空にし、使い切ったら質問欄を閉じる", async () => {
    mocks.state.request = REQUEST;
    mocks.askRequestQuestion.mockResolvedValue(undefined);
    const { rerender } = render(<RequestCard />);
    const input = screen.getByRole("textbox", { name: /依頼主に質問する/ });
    fireEvent.change(input, { target: { value: "丈はどのくらい？" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "質問する" }));
    });
    expect(mocks.askRequestQuestion).toHaveBeenCalledWith("丈はどのくらい？");
    expect((input as HTMLInputElement).value).toBe("");

    mocks.state.request = { ...REQUEST, questions_remaining: 0 };
    rerender(<RequestCard />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("質問は使い切りました")).toBeTruthy();
  });

  it("手数が上限なしなら使った手数を出す", () => {
    mocks.state.request = {
      ...REQUEST,
      turn_limit: null,
      turns_remaining: null,
      turns_used: 4,
    };
    render(<RequestCard />);
    expect(screen.getByText("上限なし（4 手使用）")).toBeTruthy();
  });

  it("最初の着せ替え前は作り直し、失敗時はもう一度作れる", () => {
    mocks.state.request = {
      ...REQUEST,
      evaluated_turns: 0,
      can_regenerate: true,
    };
    const { rerender } = render(<RequestCard />);
    fireEvent.click(screen.getByRole("button", { name: "別の依頼にする" }));
    // 作り直しても手数と質問の回数は引き継ぐ
    expect(mocks.generateRequest).toHaveBeenCalledWith("s1", {
      turnLimit: 3,
      questionLimit: 2,
    });

    mocks.state.request = null;
    mocks.state.requestError = "依頼を作れませんでした";
    mocks.state.requestTurnLimit = 5;
    rerender(<RequestCard />);
    fireEvent.click(screen.getByRole("button", { name: "もう一度依頼を作る" }));
    // 依頼が無ければ開始画面で選んだ手数で作り直す
    expect(mocks.generateRequest).toHaveBeenLastCalledWith("s1", {
      turnLimit: 5,
    });
  });
});
