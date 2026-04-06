/**
 * React Router v7 ルート定義
 * 007-chat-interactive-ux
 *
 * 注: 現在はmain.tsxでBrowserRouterを使用し、App.tsx内でuseLocationに基づいて
 * 画面を切り替えているため、このルーター定義は参照用です。
 * 将来的にRouterProviderに移行する際に使用します。
 */

/* eslint-disable react-refresh/only-export-components */

import GalleryScreen from "../components/gallery/GalleryScreen";
import AchievementsScreen from "../components/achievements/AchievementsScreen";
import EndingsScreen from "../components/endings/EndingsScreen";
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
} as const;

// セッションID付きのゲームURLを生成するヘルパー
export const getGameSessionPath = (sessionId: string): string =>
  `/play/${sessionId}`;

// 画面コンポーネントのエクスポート（App.tsxで使用）
export { GalleryScreen, EndingsScreen, AchievementsScreen, SettingsScreen };

export type RouteKey = keyof typeof ROUTES;
