import { expect, test } from "@playwright/test";
import {
  sendGameplayMessage,
  startFirstCharacterGame,
} from "./helpers/gameplay";
import {
  expectLatestMessageActionsReady,
  waitForGameplayStreamToFinish,
} from "./helpers/streamAssertions";

/**
 * spec 004 T013 / quickstart.md シナリオ A:
 * 連続 3 アクション → 中央 history を削除 → bloom / shame / adaptation が
 * 「2 件分の累積」と一致 (= 中央アクションの delta 分が逆適用) することを画面表示で検証する。
 *
 * 実数値は LLM 出力に依存するため exact-match 比較は行わず、
 * 「3 回後の値」と「中央削除後の値」が異なる (revert が発生した) ことと、
 * 中央のユーザメッセージが削除されていることを assert する。
 */
test.describe("Stats revert on history delete", () => {
  test.describe.configure({ timeout: 240_000 });

  async function readStat(
    page: import("@playwright/test").Page,
    nth: number,
  ): Promise<number> {
    const value = await page
      .locator(".character-state-panel__stat-value")
      .nth(nth)
      .innerText();
    return Number.parseInt(value.trim(), 10);
  }

  test("intermediate history delete reverts stats by middle action delta", async ({
    page,
  }) => {
    await startFirstCharacterGame(page);

    // 3 連続アクションを送信
    const instructions = [
      "白いブラウスに着替える",
      "赤いスカートに着替える",
      "黒いハイヒールに履き替える",
    ];
    for (const text of instructions) {
      await sendGameplayMessage(page, text, "dress_up");
      await waitForGameplayStreamToFinish(page);
      await expectLatestMessageActionsReady(page);
    }

    // 3 アクション後の累積 stats を取得
    const bloomAfter3 = await readStat(page, 0);
    const shameAfter3 = await readStat(page, 1);
    const adaptAfter3 = await readStat(page, 2);

    // 中央 (2 番目) の user メッセージの delete ボタンをクリック
    const userMessages = page.locator(".chat-message--user");
    await expect(userMessages).toHaveCount(3);
    const middleDelete = userMessages
      .nth(1)
      .locator(".chat-message__action-btn--delete");
    await expect(middleDelete).toBeEnabled();

    // confirm dialog 対応
    page.once("dialog", (dialog) => dialog.accept());
    await middleDelete.click();

    // 中央メッセージが消える
    await expect(userMessages).toHaveCount(2, { timeout: 30_000 });
    await expect(userMessages.nth(0)).toContainText(instructions[0]);
    await expect(userMessages.nth(1)).toContainText(instructions[2]);

    // stats が更新される (revert により値が変化、または等しい場合でも値表示が NaN/エラーでない)
    const bloomAfterDelete = await readStat(page, 0);
    const shameAfterDelete = await readStat(page, 1);
    const adaptAfterDelete = await readStat(page, 2);

    expect(Number.isNaN(bloomAfterDelete)).toBe(false);
    expect(Number.isNaN(shameAfterDelete)).toBe(false);
    expect(Number.isNaN(adaptAfterDelete)).toBe(false);

    // 中央アクションの delta が完全に 0 ではない限り少なくとも 1 stat は変化する想定。
    // LLM 応答が確率的なので、3 stats いずれかが変化していることのみ確認。
    const changed =
      bloomAfterDelete !== bloomAfter3 ||
      shameAfterDelete !== shameAfter3 ||
      adaptAfterDelete !== adaptAfter3;
    expect(changed).toBe(true);
  });
});
