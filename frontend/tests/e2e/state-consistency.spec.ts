import { expect, test } from "@playwright/test";
import {
  latestDeleteButton,
  latestUserMessage,
  sendGameplayMessage,
  startFirstCharacterGame,
} from "./helpers/gameplay";
import {
  expectLatestMessageActionsReady,
  expectNoReloadWorkaround,
  waitForGameplayStreamToFinish,
} from "./helpers/streamAssertions";

test.describe("State consistency", () => {
  test.describe.configure({ timeout: 120_000 });

  test("consecutive gameplay sends remain actionable after each completion", async ({
    page,
  }) => {
    await startFirstCharacterGame(page);
    const initialUserMessageCount = await page
      .locator(".chat-message--user")
      .count();

    await sendGameplayMessage(page, "赤いワンピースに着替える", "dress_up");
    await waitForGameplayStreamToFinish(page);
    await expectLatestMessageActionsReady(page);
    await expect(latestUserMessage(page)).toContainText(
      "赤いワンピースに着替える",
    );

    await sendGameplayMessage(page, "青い制服に着替える", "dress_up");
    await waitForGameplayStreamToFinish(page);
    await expectLatestMessageActionsReady(page);
    await expect(latestUserMessage(page)).toContainText("青い制服に着替える");
    const currentUserMessageCount = await page
      .locator(".chat-message--user")
      .count();
    expect(currentUserMessageCount).toBeGreaterThanOrEqual(
      initialUserMessageCount + 2,
    );
    await expectNoReloadWorkaround(page);
  });

  test("reload restore keeps latest message manageable", async ({ page }) => {
    await startFirstCharacterGame(page);

    await sendGameplayMessage(page, "白いブラウスに着替える", "dress_up");
    await waitForGameplayStreamToFinish(page);
    await expectLatestMessageActionsReady(page);

    await page.reload();
    await expect(page.locator(".game-play-screen")).toBeVisible();
    await expect(latestUserMessage(page)).toContainText(
      "白いブラウスに着替える",
    );
    await expect(latestDeleteButton(page)).toBeEnabled();
    await expectNoReloadWorkaround(page);
  });
});
