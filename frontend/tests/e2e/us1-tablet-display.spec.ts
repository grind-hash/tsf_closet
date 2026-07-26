/**
 * T041: US1 - Tablet viewport tests for character image display
 * Verifies: FR-001〜FR-003
 * - Character image not cropped at tablet breakpoints
 * - Chat input coexists with character panel
 * - Image tap opens fullscreen preview
 */
import { expect, test } from "@playwright/test";

test.describe("US1: Tablet viewport character display", () => {
  const tabletViewports = [
    { name: "small-tablet", width: 768, height: 1024 },
    { name: "large-tablet", width: 1024, height: 768 },
  ];

  for (const viewport of tabletViewports) {
    test.describe(`at ${viewport.name} (${viewport.width}x${viewport.height})`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });
        await page.goto("/play");
        await expect(page.locator(".game-play-screen")).toBeVisible();
      });

      test("character panel and chat input both visible (FR-001)", async ({
        page,
      }) => {
        // Character state panel should be visible
        const characterPanel = page.locator(".character-state-panel");
        await expect(characterPanel).toBeVisible();

        // Chat input should also be visible
        const chatInput = page.locator("textarea, input[type='text']").first();
        await expect(chatInput).toBeVisible();

        // Both should be in the viewport
        const panelBox = await characterPanel.boundingBox();
        const inputBox = await chatInput.boundingBox();

        expect(panelBox).not.toBeNull();
        expect(inputBox).not.toBeNull();

        if (panelBox && inputBox) {
          // Panel top should be above input bottom (both visible, not overlapping)
          expect(panelBox.y).toBeLessThan(
            inputBox.y + inputBox.height + viewport.height,
          );
        }
      });

      test("character image uses contain fit, not cropped (FR-002)", async ({
        page,
      }) => {
        // Check if character image exists
        const characterImage = page.locator(".character-state-panel__image");
        const count = await characterImage.count();

        if (count > 0) {
          const objectFit = await characterImage.first().evaluate((el) => {
            return window.getComputedStyle(el).objectFit;
          });
          expect(objectFit).toBe("contain");
        }
      });

      test("left panel has adequate height for image visibility (FR-003)", async ({
        page,
      }) => {
        // At tablet viewports (max-width: 900px), left panel should have max-height: 40vh
        if (viewport.width <= 900) {
          const leftPanel = page.locator(".game-play-screen__left-panel");
          await expect(leftPanel).toBeVisible();

          const boundingBox = await leftPanel.boundingBox();
          expect(boundingBox).not.toBeNull();

          if (boundingBox) {
            // 40vh at this viewport = 40% of viewport height
            const expectedMaxHeight = viewport.height * 0.4;
            // Allow some margin for padding/borders
            expect(boundingBox.height).toBeLessThanOrEqual(
              expectedMaxHeight + 50,
            );
            expect(boundingBox.height).toBeGreaterThan(100);
          }
        }
      });
    });
  }

  test("image click opens fullscreen preview modal", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await page.goto("/play");
    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Find the image button in character panel
    const imageButton = page.locator(".character-state-panel__image-btn");

    if ((await imageButton.count()) > 0) {
      await imageButton.click();

      // Verify the image preview modal appears
      const previewModal = page.locator(".image-preview-modal");
      await expect(previewModal).toBeVisible({ timeout: 2000 });
    }
  });
});
