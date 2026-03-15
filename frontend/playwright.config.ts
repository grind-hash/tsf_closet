import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  timeout: 30_000,
  // NovelAI API rate limit (429) にならないよう、テストを直列実行する（NovelAIに負荷をかけない）
  workers: 1,
  fullyParallel: false,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
});
