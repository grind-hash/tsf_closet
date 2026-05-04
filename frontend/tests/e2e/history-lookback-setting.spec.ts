/**
 * spec 004 (T027, US4): 履歴遡及件数（history_lookback_count）設定 UI E2E
 *
 * 要件:
 *   - 設定画面で履歴遡及件数を 10 → 15 へ変更
 *   - 設定保存後、PUT /api/settings に history_lookback_count: 15 が送信される
 *   - 範囲外（4 / 21）入力は UI で 5 / 20 に丸められる
 *
 * 注: 本テストは live スタック（フロント:3000 / バック:8000）が必要。
 */

import { test, expect } from "@playwright/test";

const APP_URL = "http://localhost:3000";

test.describe("history lookback count setting", () => {
  test("update lookback count from 10 to 15", async ({ page }) => {
    const updateRequests: Array<{ url: string; body: unknown }> = [];

    page.on("request", (request) => {
      if (
        request.method() === "PUT" &&
        request.url().includes("/api/settings") &&
        !request.url().includes("/api/settings/user") &&
        !request.url().includes("/api/settings/self-profile")
      ) {
        try {
          updateRequests.push({
            url: request.url(),
            body: JSON.parse(request.postData() ?? "{}"),
          });
        } catch {
          /* ignore */
        }
      }
    });

    await page.goto(APP_URL);

    await page
      .getByRole("link", { name: /設定|Settings/i })
      .first()
      .click();

    const lookbackInput = page.getByLabel(/履歴遡及件数|History Lookback/i);
    await expect(lookbackInput).toBeVisible();

    await lookbackInput.fill("15");
    await lookbackInput.blur();

    await expect
      .poll(() =>
        updateRequests.some(
          (req) =>
            (req.body as { history_lookback_count?: number })
              ?.history_lookback_count === 15,
        ),
      )
      .toBe(true);
  });

  test("clamp out-of-range input", async ({ page }) => {
    await page.goto(APP_URL);
    await page
      .getByRole("link", { name: /設定|Settings/i })
      .first()
      .click();

    const lookbackInput = page.getByLabel(/履歴遡及件数|History Lookback/i);

    await lookbackInput.fill("21");
    await lookbackInput.blur();
    await expect(lookbackInput).toHaveValue("20");

    await lookbackInput.fill("4");
    await lookbackInput.blur();
    await expect(lookbackInput).toHaveValue("5");
  });
});
