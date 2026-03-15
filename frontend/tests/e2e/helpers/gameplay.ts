import { expect, type Locator, type Page } from "@playwright/test";

export async function gotoPlay(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
  });
  await page.goto("/play");
  await expect(
    page.locator(".game-play-screen, .welcome-screen").first(),
  ).toBeVisible();
}

async function acceptApiConsentIfPresent(page: Page) {
  const consentButton = page.getByRole("button", { name: "同意して続行" });
  if (await consentButton.isVisible().catch(() => false)) {
    await consentButton.click();
  }
}

export async function startFirstCharacterGame(page: Page) {
  await gotoPlay(page);
  await acceptApiConsentIfPresent(page);

  const gamePlayScreen = page.locator(".game-play-screen");
  if (await gamePlayScreen.isVisible().catch(() => false)) {
    await expect(gamePlayScreen).toBeVisible();
    return;
  }

  const welcomeScreen = page.locator(".welcome-screen");
  if (!(await welcomeScreen.isVisible().catch(() => false))) {
    await expect(gamePlayScreen).toBeVisible();
    return;
  }

  const firstCharacterCard = page
    .locator(".welcome-screen__character-card")
    .first();
  await expect(firstCharacterCard).toBeVisible();
  await firstCharacterCard.click();

  const startButton = page.locator(".welcome-screen__start-btn");
  await expect(startButton).toBeEnabled();
  await startButton.click();
  await expect(gamePlayScreen).toBeVisible();
}

export async function sendGameplayMessage(
  page: Page,
  message: string,
  instructionType:
    | "dress_up"
    | "reality_alter"
    | "conversation"
    | "action" = "dress_up",
) {
  await page.locator(".chat-input__type-select").selectOption(instructionType);
  await page.locator(".chat-input__textarea").fill(message);
  await page.locator(".chat-input__send-btn").click();
}

export function latestUserMessage(page: Page): Locator {
  return page.locator(".chat-message--user").last();
}

export function latestDeleteButton(page: Page): Locator {
  return latestUserMessage(page).locator(".chat-message__action-btn--delete");
}

export function latestEditButton(page: Page): Locator {
  return latestUserMessage(page).locator(".chat-message__action-btn--edit");
}
