/**
 * MainLayout - 3カラムレイアウト
 * 007-chat-interactive-ux
 *
 * レイアウト構成:
 * ┌─────────────────────────────────────────────────────────────┐
 * │ ┌────────┐ ┌─────────────────────────────┐ ┌─────────────┐ │
 * │ │        │ │                             │ │             │ │
 * │ │ メニュー │ │       メインコンテンツ        │ │  右パネル   │ │
 * │ │        │ │                             │ │  (開閉式)   │ │
 * │ └────────┘ └─────────────────────────────┘ └─────────────┘ │
 * └─────────────────────────────────────────────────────────────┘
 */

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import SideMenu from "./SideMenu";
import "./MainLayout.css";

interface MainLayoutProps {
  children: ReactNode;
  rightPanel?: ReactNode;
  showRightPanel?: boolean;
  onToggleRightPanel?: () => void;
}

export default function MainLayout({
  children,
  rightPanel,
  showRightPanel = false,
  onToggleRightPanel,
}: MainLayoutProps) {
  const { t } = useTranslation();

  // 右パネルが表示されている場合、グリッドを3カラムに変更
  const layoutClassName = `main-layout${showRightPanel && rightPanel ? " has-right-panel" : ""}`;

  return (
    <div className={layoutClassName}>
      {/* 左サイドメニュー */}
      <aside className="main-layout__side-menu">
        <SideMenu />
      </aside>

      {/* メインコンテンツエリア */}
      <main className="main-layout__content">{children}</main>

      {/* 右パネル（オプション、開閉式） */}
      {rightPanel && (
        <>
          <button
            type="button"
            className={`main-layout__toggle-right ${showRightPanel ? "is-open" : ""}`}
            onClick={onToggleRightPanel}
            aria-label={
              showRightPanel ? t("layout.closePanel") : t("layout.openPanel")
            }
            aria-expanded={showRightPanel}
          >
            {showRightPanel ? "›" : "‹"}
          </button>
          <aside
            className={`main-layout__right-panel ${showRightPanel ? "is-open" : ""}`}
          >
            {rightPanel}
          </aside>
        </>
      )}
    </div>
  );
}
