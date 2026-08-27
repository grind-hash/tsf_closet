import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdventureProvider, useAdventure } from "../AdventureContext";

type StreamEvent = { type: string; data: Record<string, unknown> };

const streamControl = vi.hoisted(() => ({
  onEvent: null as ((event: StreamEvent) => void) | null,
  finish: null as (() => void) | null,
}));

const talkControl = vi.hoisted(() => ({
  onEvent: null as ((event: StreamEvent) => void) | null,
  finish: null as (() => void) | null,
  bodies: [] as unknown[],
}));

// AdventureProvider は API 料金の累計加算と Anlas 確認判定のために
// SettingsContext を参照する。Provider 全体を立てずに最小のモックで賄う
vi.mock("../SettingsContext", () => ({
  useSettings: () => ({
    state: { imageProvider: "novelai", showCost: false, totalCost: 0 },
    addTotalCost: vi.fn(),
  }),
}));

vi.mock("../../apis/adventure", () => ({
  streamAdventureTurn: vi.fn(
    (
      _runId: string,
      _request: unknown,
      onEvent: (event: StreamEvent) => void,
    ) =>
      new Promise<void>((resolve) => {
        streamControl.onEvent = onEvent;
        streamControl.finish = resolve;
      }),
  ),
  streamAdventureTalk: vi.fn(
    (_runId: string, body: unknown, onEvent: (event: StreamEvent) => void) =>
      new Promise<void>((resolve) => {
        talkControl.bodies.push(body);
        talkControl.onEvent = onEvent;
        talkControl.finish = resolve;
      }),
  ),
  canActOnRun: (run: { status?: string; epilogue?: boolean } | null) =>
    run?.status === "active" || Boolean(run?.epilogue),
  fetchAdventureRun: vi.fn(async () => ({
    id: "run-1",
    preset: "romance",
    status: "active",
    turn_count: 2,
    turns: [],
    choices: [],
    talk_log: [],
  })),
  fetchAdventureRuns: vi.fn(async () => []),
  fetchAdventureTemplates: vi.fn(async () => []),
  createAdventureRun: vi.fn(),
  deleteAdventureRun: vi.fn(),
  generateAdventureSetup: vi.fn(),
  normalizeAdventureImageUrl: (url: unknown) =>
    typeof url === "string" ? url : null,
  regenerateAdventureChoices: vi.fn(),
  streamAdventureImage: vi.fn(),
  updateAdventureRunSettings: vi.fn(),
}));

function StreamProbe() {
  const {
    activeRun,
    loadRun,
    submitTurn,
    submitTalk,
    talking,
    talkDraft,
    phase,
    phaseStep,
    streamingNarrative,
  } = useAdventure();
  return (
    <>
      <div data-testid="run">{activeRun?.id ?? "none"}</div>
      <div data-testid="turn-count">{activeRun?.turn_count ?? "none"}</div>
      <div data-testid="talking">{talking ? "yes" : "no"}</div>
      <div data-testid="talk-draft">{talkDraft}</div>
      <div data-testid="talk-log">
        {(activeRun?.talk_log ?? [])
          .map((entry) => `${entry.role}:${entry.text}`)
          .join("|")}
      </div>
      <button type="button" onClick={() => void submitTalk("  やあ  ")}>
        talk
      </button>
      <div data-testid="phase">{phase ?? "none"}</div>
      <div data-testid="phase-step">
        {phaseStep
          ? `${phaseStep.step}:${phaseStep.index}/${phaseStep.count}`
          : "none"}
      </div>
      <div data-testid="narrative">{streamingNarrative}</div>
      <button type="button" onClick={() => void loadRun("run-1")}>
        load
      </button>
      <button
        type="button"
        onClick={() => void submitTurn("観察する", "free_text")}
      >
        submit
      </button>
    </>
  );
}

async function startTurnStream() {
  render(
    <AdventureProvider>
      <StreamProbe />
    </AdventureProvider>,
  );
  act(() => {
    screen.getByRole("button", { name: "load" }).click();
  });
  await waitFor(() =>
    expect(screen.getByTestId("run").textContent).toBe("run-1"),
  );
  act(() => {
    screen.getByRole("button", { name: "submit" }).click();
  });
  await waitFor(() => expect(streamControl.onEvent).not.toBeNull());
}

async function finishTurnStream() {
  act(() => {
    streamControl.finish?.();
  });
  await waitFor(() =>
    expect(screen.getByTestId("phase").textContent).toBe("none"),
  );
}

describe("AdventureContext turn stream", () => {
  beforeEach(() => {
    streamControl.onEvent = null;
    streamControl.finish = null;
    talkControl.onEvent = null;
    talkControl.finish = null;
    talkControl.bodies = [];
  });

  afterEach(() => {
    cleanup();
  });

  it("trims leading whitespace only while the narrative is empty", async () => {
    await startTurnStream();

    act(() => {
      streamControl.onEvent?.({
        type: "narrative_chunk",
        data: { chunk: "\n\n扉が開いた。" },
      });
    });
    expect(screen.getByTestId("narrative").textContent).toBe("扉が開いた。");

    // 蓄積後のチャンクは意図的な改行を含めてそのまま連結する
    act(() => {
      streamControl.onEvent?.({
        type: "narrative_chunk",
        data: { chunk: "\n\n続きの文。" },
      });
    });
    expect(screen.getByTestId("narrative").textContent).toBe(
      "扉が開いた。\n\n続きの文。",
    );

    await finishTurnStream();
  });

  it("tracks image generation sub-steps from status events", async () => {
    await startTurnStream();

    act(() => {
      streamControl.onEvent?.({
        type: "status",
        data: { phase: "clue_check" },
      });
    });
    expect(screen.getByTestId("phase").textContent).toBe("clue_check");
    expect(screen.getByTestId("phase-step").textContent).toBe("none");

    act(() => {
      streamControl.onEvent?.({
        type: "status",
        data: {
          phase: "image_generation",
          step: "portrait",
          step_index: 1,
          step_count: 2,
        },
      });
    });
    expect(screen.getByTestId("phase-step").textContent).toBe("portrait:1/2");

    act(() => {
      streamControl.onEvent?.({
        type: "status",
        data: {
          phase: "image_generation",
          step: "composite",
          step_index: 2,
          step_count: 2,
        },
      });
    });
    expect(screen.getByTestId("phase-step").textContent).toBe("composite:2/2");

    await finishTurnStream();
  });

  it("keeps the partner sub-step (1on1 mode has no portrait step)", async () => {
    await startTurnStream();

    act(() => {
      streamControl.onEvent?.({
        type: "status",
        data: {
          phase: "image_generation",
          step: "partner",
          step_index: 1,
          step_count: 1,
        },
      });
    });
    expect(screen.getByTestId("phase-step").textContent).toBe("partner:1/1");

    await finishTurnStream();
  });
});

describe("AdventureContext talk stream", () => {
  beforeEach(() => {
    streamControl.onEvent = null;
    streamControl.finish = null;
    talkControl.onEvent = null;
    talkControl.finish = null;
    talkControl.bodies = [];
  });

  afterEach(() => {
    cleanup();
  });

  it("appends talk entries without touching the turn count", async () => {
    render(
      <AdventureProvider>
        <StreamProbe />
      </AdventureProvider>,
    );
    act(() => {
      screen.getByRole("button", { name: "load" }).click();
    });
    await waitFor(() =>
      expect(screen.getByTestId("run").textContent).toBe("run-1"),
    );
    act(() => {
      screen.getByRole("button", { name: "talk" }).click();
    });
    await waitFor(() => expect(talkControl.onEvent).not.toBeNull());
    expect(talkControl.bodies).toEqual([{ user_input: "やあ" }]);
    expect(screen.getByTestId("talking").textContent).toBe("yes");

    act(() => {
      talkControl.onEvent?.({ type: "talk_chunk", data: { chunk: "\nやっ" } });
      talkControl.onEvent?.({ type: "talk_chunk", data: { chunk: "ほー" } });
    });
    expect(screen.getByTestId("talk-draft").textContent).toBe("やっほー");

    act(() => {
      talkControl.onEvent?.({
        type: "talk_done",
        data: {
          user_entry: { id: "u1", role: "user", text: "やあ", after_turn: 2 },
          partner_entry: {
            id: "p1",
            role: "partner",
            text: "やっほー",
            after_turn: 2,
          },
          turn_count: 2,
        },
      });
      talkControl.finish?.();
    });
    await waitFor(() =>
      expect(screen.getByTestId("talking").textContent).toBe("no"),
    );
    expect(screen.getByTestId("talk-log").textContent).toBe(
      "user:やあ|partner:やっほー",
    );
    expect(screen.getByTestId("turn-count").textContent).toBe("2");
    expect(screen.getByTestId("talk-draft").textContent).toBe("");
  });
});
