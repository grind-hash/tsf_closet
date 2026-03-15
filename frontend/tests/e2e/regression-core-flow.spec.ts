import { test, expect } from "@playwright/test";
import {
  gotoPlay,
  sendGameplayMessage,
  startFirstCharacterGame,
} from "./helpers/gameplay";
import { waitForGameplayStreamToFinish } from "./helpers/streamAssertions";

test.describe("Regression core flow", () => {
  test("desktop: play, conversation, resume, gallery routes stay usable", async ({
    page,
  }) => {
    await startFirstCharacterGame(page);

    const instructionType = page.locator(".chat-input__type-select");
    await expect(instructionType).toBeVisible();
    await expect(
      instructionType.locator('option[value="dress_up"]'),
    ).toHaveCount(1);
    await expect(
      instructionType.locator('option[value="reality_alter"]'),
    ).toHaveCount(1);
    await expect(
      instructionType.locator('option[value="conversation"]'),
    ).toHaveCount(1);
    await expect(instructionType.locator('option[value="action"]')).toHaveCount(
      1,
    );

    await sendGameplayMessage(
      page,
      "こんにちは。今の状況を教えて",
      "conversation",
    );
    await expect(page.locator(".chat-message--user").last()).toContainText(
      "こんにちは。今の状況を教えて",
    );
    await expect(page.locator(".chat-message--system").last()).not.toHaveText(
      "",
      {
        timeout: 30_000,
      },
    );

    await page.reload();
    await expect(page.locator(".game-play-screen")).toBeVisible();
    await expect(page.locator(".chat-input__textarea")).toBeVisible();

    await page.goto("/gallery");
    await expect(page.locator(".gallery-screen")).toBeVisible();
    const resumeButton = page
      .locator(".gallery-screen__session-resume")
      .first();
    if (await resumeButton.isVisible().catch(() => false)) {
      await resumeButton.click();
      await expect(page.locator(".game-play-screen")).toBeVisible();
    }
  });

  test("desktop: dress up stream completes and remains operable", async ({
    page,
  }) => {
    await startFirstCharacterGame(page);
    await sendGameplayMessage(page, "赤いワンピースに着替える", "dress_up");

    await waitForGameplayStreamToFinish(page);
    await expect(page.locator(".chat-input__textarea")).toBeEnabled();
    await expect(page.locator(".game-play-screen__messages")).toBeVisible();
  });
});

test.describe("Regression core flow mobile", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("mobile: play screen keeps primary controls reachable", async ({
    page,
  }) => {
    await gotoPlay(page);

    if (
      await page
        .locator(".welcome-screen")
        .isVisible()
        .catch(() => false)
    ) {
      await expect(page.locator(".welcome-screen__start-btn")).toBeVisible();
    } else {
      await expect(page.locator(".game-play-screen")).toBeVisible();
      await expect(page.locator(".chat-input__textarea")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "パネルを開く" }),
      ).toBeVisible();
    }
  });
});
