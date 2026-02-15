import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";
import "./i18n";

// Context Providers
import { SettingsProvider } from "./contexts/SettingsContext";
import { NotificationProvider } from "./contexts/NotificationContext";
import { GameProvider } from "./contexts/GameContext";
import { ChatProvider } from "./contexts/ChatContext";

/**
 * アプリケーションのエントリポイント
 *
 * Context階層:
 * 1. BrowserRouter - ルーティング
 * 2. SettingsProvider - アプリ設定（最外層、他Contextで参照可能）
 * 3. NotificationProvider - 通知システム
 * 4. GameProvider - ゲーム状態
 * 5. ChatProvider - チャット状態（GameProviderに依存）
 *
 * 注: RouterProviderを使用する代わりに、BrowserRouterでラップした上で
 * App.tsx内でuseLocationを使用してルートに応じたコンポーネントを切り替えます。
 * これにより既存のAppコンポーネントとの互換性を保ちます。
 */
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SettingsProvider>
        <NotificationProvider>
          <GameProvider>
            <ChatProvider>
              <App />
            </ChatProvider>
          </GameProvider>
        </NotificationProvider>
      </SettingsProvider>
    </BrowserRouter>
  </StrictMode>,
);
