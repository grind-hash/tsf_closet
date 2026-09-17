import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CharacterChatPlayProposal } from "../../apis/characterChat";
import "../../i18n";
import CharacterChatPlayProposalCard from "./CharacterChatPlayProposalCard";

const mocks = vi.hoisted(() => ({
  startProposedPlay: vi.fn(),
  sending: false,
  selfProfile: null as { display_name: string } | null,
}));

vi.mock("../../contexts/CharacterChatContext", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../contexts/CharacterChatContext")
  >()),
  useCharacterChat: () => ({
    startProposedPlay: mocks.startProposedPlay,
    sending: mocks.sending,
  }),
}));

vi.mock("../../contexts/SettingsContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../contexts/SettingsContext")>()),
  useSettings: () => ({ selfProfile: mocks.selfProfile }),
}));

const PROPOSAL: CharacterChatPlayProposal = {
  kind: "play",
  title: "放課後の着せ替え",
  reason: "最近は制服が多いので、秋物で趣向を変えてみます。",
  character: { source: "template", id: "sakura", name: "サクラ" },
  self_mode: false,
  first_instruction: {
    instruction_type: "dress_up",
    text: "秋物のカーディガンとロングスカートに着替える",
  },
};

const START = "このキャラクターでプレイを始める";

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname}</p>;
}

function renderCard(proposal: CharacterChatPlayProposal = PROPOSAL) {
  return render(
    <MemoryRouter initialEntries={["/talk/t1"]}>
      <Routes>
        <Route
          path="/talk/:threadId"
          element={<CharacterChatPlayProposalCard proposal={proposal} />}
        />
        <Route path="/play/:sessionId" element={<p>play screen</p>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

function startButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: START }) as HTMLButtonElement;
}

beforeEach(() => {
  mocks.startProposedPlay.mockReset();
  mocks.sending = false;
  mocks.selfProfile = null;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CharacterChatPlayProposalCard", () => {
  it("shows every field of the proposal in full", () => {
    renderCard();
    expect(screen.getByText("おすすめのプレイ")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "放課後の着せ替え" }),
    ).toBeTruthy();
    expect(screen.getByText(PROPOSAL.reason)).toBeTruthy();
    expect(screen.getByText("サクラ")).toBeTruthy();
    expect(screen.queryByText("自分自身モード")).toBeNull();
    // 指示タイプはプレイ画面の選択肢と同じ表示名
    expect(screen.getByText("着せ替え")).toBeTruthy();
    expect(
      screen.getByText("秋物のカーディガンとロングスカートに着替える"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "開始すると最初の指示が入力欄に入ります。確認してから送信してください。",
      ),
    ).toBeTruthy();
    expect(startButton().disabled).toBe(false);
  });

  it("starts the proposed play, shows progress, then opens the play screen", async () => {
    let resolveStart: (sessionId: string) => void = () => {};
    mocks.startProposedPlay.mockReturnValue(
      new Promise<string>((resolve) => {
        resolveStart = resolve;
      }),
    );
    renderCard();
    fireEvent.click(startButton());

    const progress = await screen.findByRole("status");
    expect(progress.textContent).toBe("プレイを準備しています...");
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(mocks.startProposedPlay).toHaveBeenCalledTimes(1);
    expect(mocks.startProposedPlay).toHaveBeenCalledWith(PROPOSAL);

    await act(async () => {
      resolveStart("s-123");
    });
    expect(await screen.findByText("play screen")).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/play/s-123");
  });

  it("cannot start while a reply is still being processed", () => {
    mocks.sending = true;
    renderCard();
    expect(startButton().disabled).toBe(true);
    fireEvent.click(startButton());
    expect(mocks.startProposedPlay).not.toHaveBeenCalled();
  });

  it("cannot start a self-mode play without a self profile", () => {
    renderCard({ ...PROPOSAL, self_mode: true });
    expect(screen.getByText("自分自身モード")).toBeTruthy();
    expect(screen.getByText(/自分自身モードのキャラ設定が未登録/)).toBeTruthy();
    expect(startButton().disabled).toBe(true);
    fireEvent.click(startButton());
    expect(mocks.startProposedPlay).not.toHaveBeenCalled();
  });

  it("allows a self-mode play once the self profile exists", () => {
    mocks.selfProfile = { display_name: "ハル" };
    renderCard({ ...PROPOSAL, self_mode: true });
    expect(screen.getByText("自分自身モード")).toBeTruthy();
    expect(screen.queryByText(/自分自身モードのキャラ設定が未登録/)).toBeNull();
    expect(startButton().disabled).toBe(false);
  });

  it("shows an alert and stays on the chat when the start fails", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    mocks.startProposedPlay.mockRejectedValue(new Error("HTTP 400"));
    renderCard();
    fireEvent.click(startButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("プレイを開始できませんでした。");
    expect(screen.getByTestId("location").textContent).toBe("/talk/t1");
    expect(startButton().disabled).toBe(false);
  });
});
