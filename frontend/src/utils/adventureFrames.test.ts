import { describe, expect, it } from "vitest";
import type { AdventureRun, AdventureTurn } from "../apis/adventure";
import {
  buildStageFrames,
  partnerPortraitInherited,
  partnerPortraitReasonKey,
} from "./adventureFrames";

function makeTurn(overrides: Partial<AdventureTurn>): AdventureTurn {
  return {
    id: "turn-1",
    turn_number: 1,
    user_input: "進む",
    input_kind: "free",
    narrative: "本文",
    location: null,
    image_url: null,
    portrait_image_url: null,
    portrait_status: null,
    background_image_url: null,
    partner_portrait_url: null,
    partner_portrait_status: null,
    partner_note: null,
    sim: null,
    bgm: null,
    bgm_reason: null,
    ...overrides,
  } as unknown as AdventureTurn;
}

function makeRun(overrides: Partial<AdventureRun>): AdventureRun {
  return {
    preset: "mission",
    companion_mode: false,
    enable_composite_scene: false,
    current_image_url: "/img/current.png",
    background_image_url: null,
    opening_image_url: "/img/opening.png",
    opening_portrait_url: null,
    opening_partner_portrait_url: null,
    opening_narrative: "開幕",
    opening_sim: null,
    opening_bgm: "daily",
    opening_bgm_reason: null,
    turns: [],
    ...overrides,
  } as unknown as AdventureRun;
}

describe("buildStageFrames", () => {
  it("run が無ければ空", () => {
    expect(buildStageFrames(null)).toEqual([]);
  });

  it("立ち絵モードは立ち絵のある手番だけをフレームにし、BGM は据え置き手番も引き継ぐ", () => {
    const run = makeRun({
      opening_portrait_url: "/img/p0.png",
      background_image_url: "/img/bg.png",
      turns: [
        makeTurn({
          id: "t1",
          turn_number: 1,
          bgm: "tense",
          bgm_reason: "追跡",
        }),
        makeTurn({
          id: "t2",
          turn_number: 2,
          portrait_image_url: "/img/p2.png",
          partner_portrait_status: "not_requested",
        }),
      ],
    });
    const frames = buildStageFrames(run);
    expect(frames.map((f) => f.key)).toEqual(["opening", "t2"]);
    expect(frames[0]).toMatchObject({
      kind: "portrait",
      imageUrl: "/img/p0.png",
      backgroundUrl: "/img/bg.png",
      bgm: "daily",
      partnerInherited: false,
    });
    expect(frames[1]).toMatchObject({
      kind: "portrait",
      imageUrl: "/img/p2.png",
      bgm: "tense",
      bgmReason: "追跡",
      partnerStatus: "not_requested",
      partnerInherited: true,
    });
  });

  it("合成モードは画像のある手番だけを使い、立ち絵の引き継ぎ案内は出さない", () => {
    const run = makeRun({
      enable_composite_scene: true,
      opening_partner_portrait_url: "/img/partner0.png",
      turns: [
        makeTurn({ id: "t1", turn_number: 1 }),
        makeTurn({
          id: "t2",
          turn_number: 2,
          image_url: "/img/scene2.png",
          portrait_image_url: "/img/p2.png",
          partner_portrait_status: "not_requested",
        }),
      ],
    });
    const frames = buildStageFrames(run);
    expect(frames.map((f) => f.key)).toEqual(["opening", "t2"]);
    expect(frames[1]).toMatchObject({
      kind: "composite",
      imageUrl: "/img/scene2.png",
      sceneUrl: "/img/scene2.png",
      portraitUrl: "/img/p2.png",
      partnerUrl: "/img/partner0.png",
      partnerInherited: false,
    });
  });

  it("対面会話モードは全手番をフレームにし、立ち絵と背景は直前の1枚を引き継ぐ", () => {
    const run = makeRun({
      preset: "romance",
      companion_mode: true,
      opening_partner_portrait_url: "/img/partner0.png",
      turns: [
        makeTurn({
          id: "t1",
          turn_number: 1,
          partner_portrait_url: "/img/partner1.png",
          partner_portrait_status: "generated",
          background_image_url: "/img/bg1.png",
        }),
        makeTurn({
          id: "t2",
          turn_number: 2,
          partner_portrait_status: "scene_unchanged",
          partner_expression: "not-a-real-expression",
        } as Partial<AdventureTurn>),
      ],
    });
    const frames = buildStageFrames(run);
    expect(frames.map((f) => f.key)).toEqual(["opening", "t1", "t2"]);
    expect(frames[0]).toMatchObject({
      kind: "partner",
      imageUrl: "/img/partner0.png",
      backgroundUrl: null,
    });
    expect(frames[1]).toMatchObject({
      imageUrl: "/img/partner1.png",
      backgroundUrl: "/img/bg1.png",
      partnerInherited: false,
    });
    expect(frames[2]).toMatchObject({
      imageUrl: "/img/partner1.png",
      backgroundUrl: "/img/bg1.png",
      partnerUrl: "/img/partner1.png",
      partnerInherited: true,
      partnerExpression: null,
    });
  });
});

describe("partnerPortraitInherited", () => {
  it("status が記録された手番はそれに従う", () => {
    expect(
      partnerPortraitInherited(
        makeTurn({ partner_portrait_status: "generated" }),
        "/img/prev.png",
      ),
    ).toBe(false);
    expect(
      partnerPortraitInherited(
        makeTurn({ partner_portrait_status: "failed" }),
        null,
      ),
    ).toBe(true);
  });

  it("status の無い旧ターンは URL の一致で判定する", () => {
    expect(partnerPortraitInherited(makeTurn({}), "/img/prev.png")).toBe(true);
    expect(
      partnerPortraitInherited(
        makeTurn({ partner_portrait_url: "/img/prev.png" }),
        "/img/prev.png",
      ),
    ).toBe(true);
    expect(
      partnerPortraitInherited(
        makeTurn({ partner_portrait_url: "/img/new.png" }),
        "/img/prev.png",
      ),
    ).toBe(false);
  });
});

describe("partnerPortraitReasonKey", () => {
  it("未記録と generated は unknown、それ以外は status をそのまま返す", () => {
    expect(partnerPortraitReasonKey(null)).toBe("unknown");
    expect(partnerPortraitReasonKey("generated")).toBe("unknown");
    expect(partnerPortraitReasonKey("partner_absent")).toBe("partner_absent");
  });
});
