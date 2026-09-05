import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // すべてのAPIは /api/ プレフィックスでバックエンドにプロキシ
      // フロントエンドルート (/gallery, /achievements, /settings) との競合を回避
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // 履歴画像配信 (静的ファイル)
      "/history": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // ヘルスチェック
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // NovelAI関連
      "/novelai": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    // Context のテストは @testing-library/react で DOM を使うため jsdom を既定にする
    environment: "jsdom",
    // Playwright の tests/e2e/*.spec.ts を vitest が拾わないよう src 配下に限定する
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
