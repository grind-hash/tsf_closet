import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import type { AdventureRun, AdventureTurn } from "../apis/adventure";
import type { AdventureStageFrame } from "./adventureFrames";
import { buildAdventureSceneView } from "./adventureSceneView";

// i18n はキーをそのまま返す（文言の検証は対象外）
const t = ((key: string) => key) as unknown as TFunction;

function makeTurn(overrides: Partial<AdventureTurn>): AdventureTurn {
  return {
    id: "turn-1",
    turn_number: 1,
    user_input: "進む",
    input_kind: "free_text",
    narrative: "手番1の本文",
    location: "駅前",
    ...overrides,
  } as unknown as AdventureTurn;
}

function makeRun(overrides: Partial<AdventureRun>): AdventureRun {
  return {
    id: "run-1",
    preset: "mission",
    turn_count: 1,
    turns: [makeTurn({})],
    opening_narrative: "開幕の本文",
    choices: [
      { id: "c1", label: "進む" },
      { id: "c2", label: "   " },
    ],
    completed_milestones: ["m1"],
    reality_rules: undefined,
    inventory_enabled: false,
    visual_state: {
      location: "現在地",
      appearance: "",
      clothing: "",
      surroundings: "",
      main_characters: [],
    },
    talk_log: [],
    ...overrides,
  } as unknown as AdventureRun;
}

function makeFrame(
  overrides: Partial<AdventureStageFrame>,
): AdventureStageFrame {
  return {
    key: "frame-1",
    turnNumber: 1,
    imageUrl: "/img/1.png",
    kind: "portrait",
    backgroundUrl: null,
    portraitUrl: null,
    portraitStatus: null,
    sceneUrl: null,
    userInput: "過去の行動",
    inputKind: "free_text",
    narrative: "過去の本文",
    location: "過去の場所",
    sim: null,
    partnerNote: null,
    partnerUrl: null,
    partnerStatus: null,
    partnerInherited: false,
    bgm: "daily",
    bgmReason: null,
    ...overrides,
  };
}

function build(
  run: AdventureRun,
  extra: Partial<Parameters<typeof buildAdventureSceneView>[0]> = {},
) {
  return buildAdventureSceneView({
    activeRun: run,
    selectedFrame: undefined,
    latestFrame: undefined,
    isViewingPast: false,
    streamingNarrative: "",
    pendingUserInput: null,
    actionMode: "act",
    t,
    ...extra,
  });
}

describe("buildAdventureSceneView", () => {
  it("最新表示では最後の手番の本文・行動・現在地を出す", () => {
    const view = build(makeRun({}));
    expect(view.activeNarrative).toBe("手番1の本文");
    expect(view.activeAction).toBe("進む");
    expect(view.activeLocation).toBe("駅前");
    expect(view.isStreamingNarrative).toBe(false);
  });

  it("手番が無ければ開幕の本文と visual_state の現在地に倒す", () => {
    const view = build(makeRun({ turns: [], turn_count: 0 }));
    expect(view.activeNarrative).toBe("開幕の本文");
    expect(view.activeAction).toBeUndefined();
    expect(view.activeLocation).toBe("現在地");
  });

  it("ストリーム中は途中経過の本文と送信中の行動を優先する", () => {
    const view = build(makeRun({}), {
      streamingNarrative: "途中の本文",
      pendingUserInput: "話しかける",
    });
    expect(view.isStreamingNarrative).toBe(true);
    expect(view.activeNarrative).toBe("途中の本文");
    expect(view.activeAction).toBe("話しかける");
  });

  it("過去フレーム閲覧中はそのフレームの本文・行動・現在地に追従する", () => {
    const frame = makeFrame({});
    const view = build(makeRun({}), {
      selectedFrame: frame,
      isViewingPast: true,
    });
    expect(view.activeNarrative).toBe("過去の本文");
    expect(view.activeAction).toBe("過去の行動");
    expect(view.activeLocation).toBe("過去の場所");
  });

  it("空ラベルの選択肢を除き、達成済み進行目標を Set にする", () => {
    const view = build(makeRun({}));
    expect(view.availableChoices.map((choice) => choice.id)).toEqual(["c1"]);
    expect(view.completedMilestones.has("m1")).toBe(true);
    expect(view.realityRules).toEqual([]);
  });

  it("持ち物 OFF の run では inventory を null にし、ON なら所持数を合計する", () => {
    expect(build(makeRun({})).inventory).toBeNull();
    const view = build(
      makeRun({
        inventory_enabled: true,
        inventory: {
          items: [
            { id: "i1", name: "本", quantity: 2 },
            { id: "i2", name: "花", quantity: 1 },
          ],
          log: [],
        },
      } as unknown as Partial<AdventureRun>),
    );
    expect(view.inventoryCount).toBe(3);
  });

  it("romance では sim と攻略対象の名前・服装(登場人物から部分一致)を引く", () => {
    const run = makeRun({
      preset: "romance",
      sim: {
        partner_name: "サクラ",
        player_name: "ユウ",
      } as unknown as AdventureRun["sim"],
      visual_state: {
        location: "教室",
        appearance: "",
        clothing: "",
        surroundings: "",
        main_characters: [
          { name: "", clothing: "無名", action: "" },
          { name: "サクラ先輩", clothing: "制服", action: "" },
        ],
      } as unknown as AdventureRun["visual_state"],
    });
    const view = build(run);
    expect(view.sim?.partner_name).toBe("サクラ");
    expect(view.partnerName).toBe("サクラ");
    expect(view.partnerClothing).toBe("制服");
    expect(view.playerDisplayName).toBe("ユウ");
  });

  it("romance 以外では sim を無視し、主人公名は i18n の既定に倒す", () => {
    const view = build(
      makeRun({
        sim: { partner_name: "サクラ" } as unknown as AdventureRun["sim"],
      }),
    );
    expect(view.sim).toBeNull();
    expect(view.partnerName).toBe("");
    expect(view.playerDisplayName).toBe("adventure.talk.you");
  });

  it("トークモードは romance の talk のときだけ有効で、今の手番の会話だけを拾う", () => {
    const run = makeRun({
      preset: "romance",
      turn_count: 2,
      sim: { partner_name: "サクラ" } as unknown as AdventureRun["sim"],
      talk_log: [
        { id: "t1", role: "user", text: "旧", after_turn: 1 },
        { id: "t2", role: "partner", text: "旧返答", after_turn: 1 },
        { id: "t3", role: "user", text: "今", after_turn: 2 },
        { id: "t4", role: "partner", text: "今の返答", after_turn: 2 },
      ],
    });
    const view = build(run, { actionMode: "talk" });
    expect(view.talkMode).toBe(true);
    expect(view.currentTalkEntries.map((entry) => entry.id)).toEqual([
      "t3",
      "t4",
    ]);
    expect(view.lastPartnerTalk?.id).toBe("t4");
    expect(build(makeRun({}), { actionMode: "talk" }).talkMode).toBe(false);
  });

  it("表示中フレームの持ち物の変化を 1 行の案内にする", () => {
    const run = makeRun({
      inventory_enabled: true,
      inventory: { items: [], log: [] },
    } as unknown as Partial<AdventureRun>);
    const frame = makeFrame({
      worldEvents: [
        {
          kind: "acquire",
          item_id: "i1",
          item_name: "本",
          quantity: 1,
          turn_number: 1,
        },
      ] as unknown as AdventureStageFrame["worldEvents"],
    });
    const view = build(run, { latestFrame: frame });
    expect(view.inventoryNote).not.toBeNull();
    expect(build(run, { latestFrame: makeFrame({}) }).inventoryNote).toBeNull();
  });
});
