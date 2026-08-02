import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App.tsx";
import "./i18n";

// Self-hosted fonts (bundled via @fontsource, no external requests)
import "@fontsource/biz-udgothic/400.css";
import "@fontsource/biz-udgothic/700.css";
import "@fontsource/noto-sans-jp/400.css";
import "@fontsource/noto-sans-jp/500.css";
import "@fontsource/noto-sans-jp/700.css";
import "@fontsource/biz-udmincho/400.css";
import "@fontsource/biz-udmincho/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/roboto-mono/400.css";
import "@fontsource/roboto-mono/500.css";
import "@fontsource/roboto-mono/700.css";

import { ChatProvider } from "./contexts/ChatContext";
import { GameProvider } from "./contexts/GameContext";
import { NotificationProvider } from "./contexts/NotificationContext";
// Context Providers
import { SettingsProvider } from "./contexts/SettingsContext";

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
