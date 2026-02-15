/**
 * API Base URL utility
 *
 * すべてのAPI呼び出しはこのベースURLを使用します。
 * バックエンドAPIは /api プレフィックスでマウントされています。
 */

// 環境変数が設定されている場合はそれを使用、なければ /api をデフォルト
export const API_BASE = import.meta.env.VITE_API_URL || "/api";
