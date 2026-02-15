import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
});
