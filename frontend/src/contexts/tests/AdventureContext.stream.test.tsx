import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdventureProvider, useAdventure } from "../AdventureContext";

type StreamEvent = { type: string; data: Record<string, unknown> };

const streamControl = vi.hoisted(() => ({
  onEvent: null as ((event: StreamEvent) => void) | null,
  finish: null as (() => void) | null,
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
  fetchAdventureRun: vi.fn(async () => ({
    id: "run-1",
    turns: [],
    choices: [],
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
    phase,
    phaseStep,
    streamingNarrative,
  } = useAdventure();
  return (
    <>
      <div data-testid="run">{activeRun?.id ?? "none"}</div>
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
});
