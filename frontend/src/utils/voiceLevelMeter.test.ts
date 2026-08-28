import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createSilentVoiceLevelMeter,
  createVoiceLevelMeter,
  normalizeVoiceLevel,
  rmsFromTimeDomain,
  smoothLevel,
} from "./voiceLevelMeter";

describe("voiceLevelMeter pure helpers", () => {
  it("computes RMS of time-domain samples", () => {
    expect(rmsFromTimeDomain(new Float32Array(0))).toBe(0);
    expect(rmsFromTimeDomain(new Float32Array(256))).toBe(0);
    const square = new Float32Array(256);
    for (let i = 0; i < square.length; i++) square[i] = i % 2 === 0 ? 1 : -1;
    expect(rmsFromTimeDomain(square)).toBeCloseTo(1, 9);
    const half = new Float32Array(64).fill(0.5);
    expect(rmsFromTimeDomain(half)).toBeCloseTo(0.5, 9);
  });

  it("normalizes by playback volume and clamps to 0..1", () => {
    expect(normalizeVoiceLevel(0, 1)).toBe(0);
    expect(normalizeVoiceLevel(0.01, 1)).toBe(0);
    expect(normalizeVoiceLevel(1, 1)).toBe(1);
    expect(normalizeVoiceLevel(0.1, 0.5)).toBeGreaterThan(
      normalizeVoiceLevel(0.1, 1),
    );
    // 0.02 のしきい値を引いて 0.25 で割る
    expect(normalizeVoiceLevel(0.145, 1)).toBeCloseTo(0.5, 9);
    // 音量 0 でも 0 除算にならない
    expect(Number.isFinite(normalizeVoiceLevel(0.1, 0))).toBe(true);
    expect(normalizeVoiceLevel(0.1, 0)).toBeLessThanOrEqual(1);
    expect(normalizeVoiceLevel(Number.NaN, 1)).toBe(0);
  });

  it("rises faster than it falls", () => {
    const rise = smoothLevel(0, 1, 0.05) - 0;
    const fall = 1 - smoothLevel(1, 0, 0.05);
    expect(rise).toBeGreaterThan(fall);
    expect(rise).toBeGreaterThan(0);
    expect(rise).toBeLessThan(1);
    expect(smoothLevel(0.3, 0.3, 0.05)).toBeCloseTo(0.3, 9);
    // 経過時間 0 では変化しない
    expect(smoothLevel(0, 1, 0)).toBe(0);
    // 十分に長い時間では目標へ収束する
    expect(smoothLevel(0, 1, 10)).toBeCloseTo(1, 6);
  });
});

describe("createVoiceLevelMeter without Web Audio", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns a silent meter in node", () => {
    const meter = createVoiceLevelMeter();
    const audio = {} as HTMLAudioElement;
    expect(() => meter.attach(audio)).not.toThrow();
    expect(meter.getLevel()).toBe(0);
    expect(() => meter.dispose()).not.toThrow();
    expect(meter.getLevel()).toBe(0);
  });

  it("returns a silent meter when window has no AudioContext", () => {
    vi.stubGlobal("window", {});
    const meter = createVoiceLevelMeter();
    const audio = {} as HTMLAudioElement;
    expect(() => meter.attach(audio)).not.toThrow();
    expect(meter.getLevel()).toBe(0);
    expect(() => meter.dispose()).not.toThrow();
  });

  it("exposes an explicit silent meter", () => {
    const meter = createSilentVoiceLevelMeter();
    meter.attach({} as HTMLAudioElement);
    expect(meter.getLevel()).toBe(0);
    meter.dispose();
  });
});

type Listener = () => void;

function makeFakeAudioEnvironment(initialState: "running" | "suspended") {
  const listeners = new Map<string, Listener[]>();
  const analyserFill = { value: 0 };
  const instances: FakeAudioContext[] = [];
  class FakeAnalyser {
    fftSize = 2048;
    smoothingTimeConstant = 0.8;
    connect = vi.fn();
    disconnect = vi.fn();
    getFloatTimeDomainData(buf: Float32Array) {
      buf.fill(analyserFill.value);
    }
  }
  class FakeAudioContext {
    state: "running" | "suspended" | "closed" = initialState;
    destination = {};
    constructor() {
      instances.push(this);
    }
    createMediaElementSource = vi.fn(() => ({
      connect: vi.fn(),
      disconnect: vi.fn(),
    }));
    createAnalyser = vi.fn(() => new FakeAnalyser());
    resume = vi.fn(async () => {
      this.state = "running";
    });
    close = vi.fn(async () => {
      this.state = "closed";
    });
  }
  const fakeWindow = {
    AudioContext: FakeAudioContext,
    addEventListener: vi.fn((type: string, handler: Listener) => {
      listeners.set(type, [...(listeners.get(type) ?? []), handler]);
    }),
    removeEventListener: vi.fn((type: string, handler: Listener) => {
      listeners.set(
        type,
        (listeners.get(type) ?? []).filter((h) => h !== handler),
      );
    }),
  };
  vi.stubGlobal("window", fakeWindow);
  return { fakeWindow, listeners, analyserFill, instances };
}

async function loadMeterModule() {
  vi.resetModules();
  return import("./voiceLevelMeter");
}

describe("createVoiceLevelMeter with a fake AudioContext", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("connects immediately when the context is running", async () => {
    const env = makeFakeAudioEnvironment("running");
    const { createVoiceLevelMeter: create } = await loadMeterModule();
    const meter = create();
    const audio = {
      paused: false,
      ended: false,
      volume: 1,
    } as HTMLAudioElement;
    meter.attach(audio);
    env.analyserFill.value = 0.5;
    expect(meter.getLevel()).toBe(1);
    env.analyserFill.value = 0;
    expect(meter.getLevel()).toBe(0);
    expect(env.fakeWindow.addEventListener).not.toHaveBeenCalled();
    meter.dispose();
    expect(meter.getLevel()).toBe(0);
  });

  it("reports 0 while the element is paused or ended", async () => {
    const env = makeFakeAudioEnvironment("running");
    const { createVoiceLevelMeter: create } = await loadMeterModule();
    const meter = create();
    const audio = { paused: true, ended: false, volume: 1 } as HTMLAudioElement;
    meter.attach(audio);
    env.analyserFill.value = 0.5;
    expect(meter.getLevel()).toBe(0);
    (audio as { paused: boolean }).paused = false;
    expect(meter.getLevel()).toBe(1);
    (audio as { ended: boolean }).ended = true;
    expect(meter.getLevel()).toBe(0);
    meter.dispose();
  });

  it("defers connection until a user gesture when suspended", async () => {
    const env = makeFakeAudioEnvironment("suspended");
    const { createVoiceLevelMeter: create } = await loadMeterModule();
    const meter = create();
    const audio = {
      paused: false,
      ended: false,
      volume: 1,
    } as HTMLAudioElement;
    meter.attach(audio);
    expect(env.instances).toHaveLength(1);
    const ctx = env.instances[0];
    // 停止中のコンテキストには接続しない(接続すると要素が無音化する)
    expect(ctx.createMediaElementSource).not.toHaveBeenCalled();
    expect(env.fakeWindow.addEventListener).toHaveBeenCalledWith(
      "pointerdown",
      expect.any(Function),
      { once: true },
    );
    expect(env.fakeWindow.addEventListener).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
      { once: true },
    );
    // まだ接続されていないのでレベルは 0
    env.analyserFill.value = 0.5;
    expect(meter.getLevel()).toBe(0);

    const handlers = env.listeners.get("pointerdown") ?? [];
    expect(handlers).toHaveLength(1);
    handlers[0]();
    await vi.waitFor(() => {
      expect(meter.getLevel()).toBe(1);
    });
    expect(ctx.resume).toHaveBeenCalledTimes(1);
    expect(ctx.createMediaElementSource).toHaveBeenCalledTimes(1);
    expect(ctx.createMediaElementSource).toHaveBeenCalledWith(audio);
    // 一方のリスナーが発火したらもう一方も外れる
    expect(env.fakeWindow.removeEventListener).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
    );
    meter.dispose();
  });

  it("does not reconnect the same element across meters", async () => {
    const env = makeFakeAudioEnvironment("running");
    const { createVoiceLevelMeter: create } = await loadMeterModule();
    const audio = {
      paused: false,
      ended: false,
      volume: 1,
    } as HTMLAudioElement;
    const first = create();
    first.attach(audio);
    first.dispose();
    const second = create();
    expect(() => second.attach(audio)).not.toThrow();
    expect(() => second.attach(audio)).not.toThrow();
    expect(env.instances).toHaveLength(1);
    expect(env.instances[0].createMediaElementSource).toHaveBeenCalledTimes(1);
    expect(env.instances[0].close).not.toHaveBeenCalled();
    second.dispose();
  });

  it("removes unlock listeners on dispose", async () => {
    const env = makeFakeAudioEnvironment("suspended");
    const { createVoiceLevelMeter: create } = await loadMeterModule();
    const meter = create();
    meter.attach({
      paused: false,
      ended: false,
      volume: 1,
    } as HTMLAudioElement);
    meter.dispose();
    expect(env.listeners.get("pointerdown") ?? []).toHaveLength(0);
    expect(env.listeners.get("keydown") ?? []).toHaveLength(0);
  });
});
