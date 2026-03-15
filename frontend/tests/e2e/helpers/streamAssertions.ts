import { expect, type Page } from "@playwright/test";
import { latestDeleteButton } from "./gameplay";

export async function waitForGameplayStreamToFinish(page: Page) {
  await expect(page.locator(".chat-input__textarea")).toBeEnabled({
    timeout: 90_000,
  });
}

export async function expectLatestMessageActionsReady(page: Page) {
  await expect(latestDeleteButton(page)).toBeEnabled();
}

export async function expectNoReloadWorkaround(page: Page) {
  await expect(
    page.getByText("このメッセージを操作するにはページをリロードしてください"),
  ).toHaveCount(0);
  await expect(
    page.getByText("Please reload the page to manage this message"),
  ).toHaveCount(0);
}
