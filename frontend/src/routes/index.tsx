/**
 * React Router v7 ルート定義
 * 007-chat-interactive-ux
 *
 * 注: 現在はmain.tsxでBrowserRouterを使用し、App.tsx内でuseLocationに基づいて
 * 画面を切り替えているため、このルーター定義は参照用です。
 * 将来的にRouterProviderに移行する際に使用します。
 */

import AchievementsScreen from "../components/achievements/AchievementsScreen";
import EndingsScreen from "../components/endings/EndingsScreen";
import GalleryScreen from "../components/gallery/GalleryScreen";
import SettingsScreen from "../components/settings/SettingsScreen";

/**
 * ルート定義
 *
 * /                     → ルート（/play/newにリダイレクト）
 * /play/:sessionId      → ゲーム画面（セッションID指定）
 * /play/new             → 新規ゲーム開始（キャラクター選択）
 * /gallery              → ギャラリー画面
 * /achievements         → 実績画面
 * /settings             → 設定画面
 * /prompt-expander      → Prompt Expander（セッション一覧）
 * /prompt-expander/:sessionId → Prompt Expander（セッション詳細）
 *
 * 注: /gameはバックエンドAPIで使用されているため、フロントエンドは/playを使用
 */

// ルートパス定数
export const ROUTES = {
  HOME: "/",
  GAME: "/play",
  GAME_SESSION: "/play/:sessionId",
  GAME_NEW: "/play/new",
  GALLERY: "/gallery",
  GALLERY_SESSION: "/gallery/:sessionId",
  ENDINGS: "/endings",
  ACHIEVEMENTS: "/achievements",
  SETTINGS: "/settings",
  ADVENTURE: "/adventure",
  ADVENTURE_RUN: "/adventure/:runId",
  // /adventure 配下に置かないこと。App.tsx が startsWith("/adventure") で
  // AdventureScreen へ流し、パス2階層目を runId として解釈するため衝突する
  BGM_TEST: "/bgm-test",
  PROMPT_EXPANDER: "/prompt-expander",
  PROMPT_EXPANDER_SESSION: "/prompt-expander/:sessionId",
} as const;

// セッションID付きのゲームURLを生成するヘルパー
export const getGameSessionPath = (sessionId: string): string =>
  `/play/${sessionId}`;

// 画面コンポーネントのエクスポート（App.tsxで使用）
export { AchievementsScreen, EndingsScreen, GalleryScreen, SettingsScreen };

export type RouteKey = keyof typeof ROUTES;
