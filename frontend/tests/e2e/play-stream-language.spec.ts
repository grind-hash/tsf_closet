import { test, expect } from "@playwright/test";

test("play stream request includes selected language", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });

  let capturedLanguage: string | undefined;

  await page.route("**/api/game/play/stream", async (route) => {
    const payload = route.request().postDataJSON() as
      | { language?: string }
      | undefined;
    capturedLanguage = payload?.language;

    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: text",
        'data: {"chunk":"Hello"}',
        "",
        "event: complete",
        'data: {"session_id":"test-session","transformation_count":1}',
        "",
      ].join("\n"),
    });
  });

  await page.goto("http://localhost:3000/settings");
  await page.getByRole("radio", { name: "English" }).check();

  await page.goto("http://localhost:3000/play");
  await page.locator(".backdrop").first().waitFor({ state: "hidden" });

  const startButton = page.locator(".welcome-screen__start-btn");
  if (await startButton.isVisible().catch(() => false)) {
    await page.locator(".welcome-screen__character-card").first().click();
    await startButton.click();
    await page.waitForTimeout(1000);
  }

  const input = page.locator("textarea").first();
  await input.fill("Please change into a cute pink maid outfit");
  await page.getByRole("button", { name: /Send|送信/ }).click();

  await expect.poll(() => capturedLanguage).toBe("en");
});
