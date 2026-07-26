/**
 * T040: Responsive layout regression tests
 * Verifies that desktop (1280x800), tablet (900x800), and mobile (375x667) layouts
 * render correctly without visual regressions.
 *
 * NOTE: This test uses visual snapshot comparisons.
 * Run `npx playwright test --update-snapshots` to generate baseline images.
 */
import { expect, test } from "@playwright/test";

const viewports = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 900, height: 800 },
  { name: "mobile", width: 375, height: 667 },
] as const;

test.describe("Responsive layout regression", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("novelai_api_key_consent", "true");
    });
  });

  for (const viewport of viewports) {
    test(`play screen renders correctly at ${viewport.name} (${viewport.width}x${viewport.height})`, async ({
      page,
    }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });

      await page.goto("/play");

      // Wait for the main screen to be visible
      await expect(page.locator(".game-play-screen")).toBeVisible();

      // Wait for any loading states to complete
      await page.waitForTimeout(500);

      // Take a screenshot for visual comparison (mask dynamic content)
      await expect(page).toHaveScreenshot(`play-screen-${viewport.name}.png`, {
        fullPage: false,
        maxDiffPixelRatio: 0.05,
        mask: [
          page.locator(".game-play-screen__messages"),
          page.locator(".chat-message-list"),
          page.locator(".game-play-screen__character-image"),
        ],
      });
    });
  }

  test("tablet layout shows character panel with adequate height", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Check that left panel exists and has reasonable height (40vh = ~320px at 800px viewport)
    const leftPanel = page.locator(".game-play-screen__left-panel");
    await expect(leftPanel).toBeVisible();

    const boundingBox = await leftPanel.boundingBox();
    expect(boundingBox).not.toBeNull();
    if (boundingBox) {
      // At 800px viewport, 40vh = 320px. Allow some margin.
      expect(boundingBox.height).toBeGreaterThanOrEqual(200);
      expect(boundingBox.height).toBeLessThanOrEqual(400);
    }
  });

  test("mobile layout shows column direction content", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Verify content is in column layout
    const content = page.locator(".game-play-screen__content");
    await expect(content).toBeVisible();

    // Check CSS flex-direction is column
    const flexDirection = await content.evaluate((el) => {
      return window.getComputedStyle(el).flexDirection;
    });
    expect(flexDirection).toBe("column");
  });

  test("desktop layout shows row direction content", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Verify content is in row layout
    const content = page.locator(".game-play-screen__content");
    await expect(content).toBeVisible();

    const flexDirection = await content.evaluate((el) => {
      return window.getComputedStyle(el).flexDirection;
    });
    expect(flexDirection).toBe("row");
  });

  test("character image uses object-fit contain", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Check the character image has object-fit: contain
    const characterImage = page.locator(".character-state-panel__image");
    // Skip if no image is loaded
    const count = await characterImage.count();
    if (count > 0) {
      const objectFit = await characterImage.first().evaluate((el) => {
        return window.getComputedStyle(el).objectFit;
      });
      expect(objectFit).toBe("contain");
    }
  });

  test("chat input is accessible at tablet viewport", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Verify chat input is visible and usable
    const chatInput = page.locator("textarea, input[type='text']").first();
    await expect(chatInput).toBeVisible();

    // Verify it's in the viewport (not clipped)
    const boundingBox = await chatInput.boundingBox();
    expect(boundingBox).not.toBeNull();
    if (boundingBox) {
      expect(boundingBox.y + boundingBox.height).toBeLessThanOrEqual(800);
    }
  });
});
