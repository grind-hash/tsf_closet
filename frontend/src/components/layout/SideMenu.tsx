/**
 * SideMenu - 左サイドメニュー
 * 007-chat-interactive-ux
 *
 * メニュー項目:
 * - 新規プレイ
 * - ギャラリー
 * - TSFシナリオ / BGMテスト（実験設定で有効化）
 * - Prompt Expander（実験設定で有効化）
 * - 実績
 * - 設定
 */

import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import { getGameSessionPath, ROUTES } from "../../routes";
import {
  readLastAdventureRunId,
  subscribeLastAdventureRunId,
} from "../../utils/adventureLastRun";
import "./SideMenu.css";

const getServerLastAdventureRunId = (): string | null => null;

interface MenuItem {
  id: string;
  label: string;
  icon: string;
  path: string;
  description?: string;
}

const getMenuItems = (
  t: (key: string) => string,
  showEndingMenu: boolean,
  showAdventureMenu: boolean,
  showPromptExpanderMenu: boolean,
): MenuItem[] => {
  return [
    {
      id: "new-game",
      label: t("menu.newGame"),
      icon: "🎮",
      path: ROUTES.GAME_NEW,
      description: t("menu.newGameDesc"),
    },
    {
      id: "gallery",
      label: t("menu.gallery"),
      icon: "🖼️",
      path: ROUTES.GALLERY,
      description: t("menu.galleryDesc"),
    },
    ...(showAdventureMenu
      ? [
          {
            id: "adventure",
            label: t("menu.adventure"),
            icon: "A",
            path: ROUTES.ADVENTURE,
            description: t("menu.adventureDesc"),
          },
          {
            id: "bgm-test",
            label: t("menu.bgmTest"),
            icon: "♪",
            path: ROUTES.BGM_TEST,
            description: t("menu.bgmTestDesc"),
          },
        ]
      : []),
    ...(showPromptExpanderMenu
      ? [
          {
            id: "prompt-expander",
            label: t("menu.promptExpander"),
            icon: "✨",
            path: ROUTES.PROMPT_EXPANDER,
            description: t("menu.promptExpanderDesc"),
          },
        ]
      : []),
    ...(showEndingMenu
      ? [
          {
            id: "endings",
            label: t("menu.endings"),
            icon: "🎬",
            path: ROUTES.ENDINGS,
            description: t("menu.endingsDesc"),
          },
        ]
      : []),
    {
      id: "achievements",
      label: t("menu.achievements"),
      icon: "🏆",
      path: ROUTES.ACHIEVEMENTS,
      description: t("menu.achievementsDesc"),
    },
    {
      id: "settings",
      label: t("menu.settings"),
      icon: "⚙️",
      path: ROUTES.SETTINGS,
      description: t("menu.settingsDesc"),
    },
  ];
};

export default function SideMenu() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { state: gameState, clearSession } = useGame();
  const { clearMessages } = useChat();
  const { state: settingsState } = useSettings();

  // メニュー項目を取得
  const menuItems = getMenuItems(
    t,
    settingsState.experimentalEndingEnabled,
    settingsState.experimentalAdventureEnabled,
    settingsState.experimentalPromptExpanderEnabled,
  );

  // プレイ中のゲームがあるかどうか
  const hasActiveGame = gameState.isActive && gameState.sessionId;

  // 直前に開いた TSFシナリオ(Adventure run)。AdventureProvider は /adventure 配下に
  // しか無いため Context ではなく localStorage の購読で取得する
  const lastAdventureRunId = useSyncExternalStore(
    subscribeLastAdventureRunId,
    readLastAdventureRunId,
    getServerLastAdventureRunId,
  );

  const handleMenuClick = (path: string, menuId: string) => {
    // 新規プレイの場合はセッションとチャット履歴をクリアしてからナビゲート
    if (menuId === "new-game") {
      clearSession();
      clearMessages();
    }
    navigate(path);
  };

  // プレイ中のゲームに移動
  const handleGoToActiveGame = () => {
    if (gameState.sessionId) {
      navigate(getGameSessionPath(gameState.sessionId));
    }
  };

  // タイトルクリック時の処理
  const handleTitleClick = () => {
    if (hasActiveGame && gameState.sessionId) {
      navigate(getGameSessionPath(gameState.sessionId));
    }
  };

  const isActive = (path: string): boolean => {
    // /play と /play/new の両方を "game" として扱う
    if (path === ROUTES.GAME_NEW) {
      return (
        location.pathname === ROUTES.GAME_NEW ||
        location.pathname === ROUTES.GAME
      );
    }
    // 詳細ページ（/prompt-expander/:id、/adventure/:runId、/gallery/:sessionId）でも
    // 親の項目を選択中として扱う。セッションを開いたまま項目が非活性になると、
    // その項目から一覧へ戻れることに気付けない
    return (
      location.pathname === path || location.pathname.startsWith(`${path}/`)
    );
  };

  return (
    <nav className="side-menu" aria-label={t("menu.main")}>
      <div className="side-menu__header">
        <button
          type="button"
          className={`side-menu__title ${hasActiveGame ? "is-clickable" : ""}`}
          onClick={handleTitleClick}
          disabled={!hasActiveGame}
          title={hasActiveGame ? t("menu.goActiveGame") : undefined}
        >
          TSF Closet
        </button>
      </div>

      <ul className="side-menu__list">
        {menuItems.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={`side-menu__item ${isActive(item.path) ? "is-active" : ""}`}
              onClick={() => handleMenuClick(item.path, item.id)}
              title={item.description}
              aria-current={isActive(item.path) ? "page" : undefined}
            >
              <span className="side-menu__icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="side-menu__label">{item.label}</span>
            </button>
            {/* 新規プレイの下にプレイ中のゲームに移動を表示 */}
            {item.id === "new-game" && hasActiveGame && (
              <button
                type="button"
                className="side-menu__item side-menu__item--sub"
                onClick={handleGoToActiveGame}
                title={t("menu.backToActiveGame")}
              >
                <span className="side-menu__icon" aria-hidden="true">
                  ▶️
                </span>
                <span className="side-menu__label">
                  {t("menu.goActiveGame")}
                </span>
              </button>
            )}
            {/* TSFシナリオの下に直前に開いたシナリオへの導線を表示 */}
            {item.id === "adventure" && lastAdventureRunId && (
              <button
                type="button"
                className="side-menu__item side-menu__item--sub"
                onClick={() =>
                  navigate(`${ROUTES.ADVENTURE}/${lastAdventureRunId}`)
                }
                title={t("menu.goLastAdventure")}
              >
                <span className="side-menu__icon" aria-hidden="true">
                  ▶️
                </span>
                <span className="side-menu__label">
                  {t("menu.goLastAdventure")}
                </span>
              </button>
            )}
          </li>
        ))}
      </ul>

      <div className="side-menu__footer">
        <span className="side-menu__version"></span>
      </div>
    </nav>
  );
}
