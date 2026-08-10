import { expect, test } from "@playwright/test";

// 64x64: near-white background (252,251,250) with a solid 20x20 red square in the middle.
const WHITE_BG_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAmUlEQVR4nO3ZsQ3CQBQE0bkR7ZBRAYW7Amd0gx3Qgy84jczL92ulDf84jy9lEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEveYP7E/35ezr8929wUkTuIkTuIkTuIkTuIkTuIkTuIkTuIkTuIkTuLG/1O/mMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMS5usCsH/HgCWNvKE7YAAAAAElFTkSuQmCC";

const IMAGE = "/probe-portrait.png";

const RUN = {
  id: "run-1",
  source_session_id: "session-1",
  source_history_id: null,
  scenario_template_id: null,
  preset: "infiltration",
  title: "潜入ミッション",
  objective: "差出人を特定する",
  setting: "仮面舞踏会",
  constraints: [],
  status: "active",
  turn_count: 0,
  max_turns: 8,
  remaining_turns: 8,
  ending_title: null,
  ending_summary: null,
  clues: [],
  milestones: [],
  completed_milestones: [],
  opening_narrative: "舞踏会の入口に立っている。",
  choices: [{ id: "a", label: "受付を観察する" }],
  current_image_url: IMAGE,
  current_image_prompt: null,
  use_precise_reference: false,
  enable_composite_scene: false,
  opening_image_url: IMAGE,
  background_image_url: IMAGE,
  portrait_image_url: IMAGE,
  opening_portrait_url: IMAGE,
  visual_state: null,
  turns: [],
  created_at: "2026-08-01T00:00:00",
  updated_at: "2026-08-01T00:00:00",
};

test("stage portrait is replaced by a transparent version", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalAdventureEnabled: true }),
    );
  });
  await page.route("**/api/probe-portrait.png", async (route) => {
    await route.fulfill({
      body: Buffer.from(WHITE_BG_PNG_BASE64, "base64"),
      contentType: "image/png",
    });
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({ json: RUN });
  });

  await page.goto("/adventure/run-1");
  const portrait = page.locator(".adventure-stage__portrait");
  await expect(portrait).toBeVisible();
  await expect
    .poll(async () => (await portrait.getAttribute("src")) ?? "", {
      timeout: 15000,
    })
    .toMatch(/^blob:/);

  const src = (await portrait.getAttribute("src")) as string;
  const stats = await page.evaluate(async (url: string) => {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("failed to load processed image"));
      el.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas 2d context unavailable");
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let transparent = 0;
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] < 8) transparent++;
    }
    return {
      width: canvas.width,
      height: canvas.height,
      corner: [data[0], data[1], data[2], data[3]],
      ratio: transparent / (canvas.width * canvas.height),
      centerAlpha:
        data[((canvas.height / 2) * canvas.width + canvas.width / 2) * 4 + 3],
    };
  }, src);

  // Background is cleared while the subject stays fully opaque.
  expect(stats.ratio).toBeGreaterThan(0.5);
  expect(stats.centerAlpha).toBe(255);
});
