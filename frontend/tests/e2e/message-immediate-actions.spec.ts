import { expect, test } from "@playwright/test";
import {
  latestDeleteButton,
  sendGameplayMessage,
  startFirstCharacterGame,
} from "./helpers/gameplay";
import {
  expectLatestMessageActionsReady,
  expectNoReloadWorkaround,
  waitForGameplayStreamToFinish,
} from "./helpers/streamAssertions";

test.describe("Immediate message actions", () => {
  // NovelAI API response can be slow; double the per-test timeout
  test.slow();

  test("completed message becomes manageable without reload", async ({
    page,
  }) => {
    await startFirstCharacterGame(page);
    await sendGameplayMessage(page, "赤いワンピースに着替える", "dress_up");

    await waitForGameplayStreamToFinish(page);
    await expectLatestMessageActionsReady(page);
    await expectNoReloadWorkaround(page);
  });

  test("delete button stays disabled while streaming", async ({ page }) => {
    await startFirstCharacterGame(page);
    await sendGameplayMessage(page, "青い制服に着替える", "dress_up");

    await expect(latestDeleteButton(page)).toBeDisabled();
  });
});
