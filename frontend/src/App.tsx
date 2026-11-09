import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { shouldShowCost } from "./apis/system";
import AchievementsScreen from "./components/achievements/AchievementsScreen";
import AdventureScreen from "./components/adventure/AdventureScreen";
import BgmTestScreen from "./components/bgm/BgmTestScreen";
import CharacterChatScreen from "./components/characterChat/CharacterChatScreen";
import CharactersScreen from "./components/characters/CharactersScreen";
import EndingModal from "./components/EndingModal";
import EndingsScreen from "./components/endings/EndingsScreen";
import FavoritePromptHost from "./components/favoritePrompts/FavoritePromptHost";
import GamePlayScreen from "./components/GamePlayScreen";
// 007-chat-interactive-ux: ルートベースの画面コンポーネント
import GalleryScreen from "./components/gallery/GalleryScreen";
import GuideScreen from "./components/guide/GuideScreen";
import HakoniwaScreen from "./components/hakoniwa/HakoniwaScreen";
import NovelaiAccountModals, {
  NovelaiAccountCheckOnOpen,
} from "./components/NovelaiAccountModals";
import NotificationContainer from "./components/notifications/NotificationContainer";
import PromptExpanderScreen from "./components/promptExpander/PromptExpanderScreen";
import SessionListModal from "./components/SessionListModal";
import SalonScreen from "./components/salon/SalonScreen";
import SettingsScreen from "./components/settings/SettingsScreen";
import { AdventureProvider } from "./contexts/AdventureContext";
import { CharacterChatProvider } from "./contexts/CharacterChatContext";
import { HakoniwaProvider } from "./contexts/HakoniwaContext";
import { PromptExpanderProvider } from "./contexts/PromptExpanderContext";
import { SalonProvider } from "./contexts/SalonContext";
import { useSettings } from "./contexts/SettingsContext";
import { useNovelaiAccountCheck } from "./hooks/useNovelaiAccountCheck";
import { usePlayTurn } from "./hooks/usePlayTurn";
import { getGameSessionPath } from "./routes";
// MainLayout は各画面コンポーネント内で使用
import { API_BASE } from "./utils/api";
import { readStorage, writeStorage } from "./utils/storage";
import "./App.css";

// 007-chat-interactive-ux: Context hooks
import { SESSION_STORAGE_KEY, useGame } from "./contexts/GameContext";

// /health の結果は同一タブ内で再取得しない（sessionStorage キャッシュ）
const IMAGE_PROVIDER_CACHE_KEY = "image_provider";
const SHOW_COST_CACHE_KEY = "show_cost";

function App() {
  return (
    <>
      {/* 通知トーストコンテナ。ギャラリー・設定・TSFシナリオ・Prompt Expander でも
          通知が出るよう、ルート分岐より外側に置く（AppMain の中に置くと通常プレイ
          画面へ移動するまでキューに溜まったままになる） */}
      <NotificationContainer />
      {/* お気に入りプロンプトのダイアログ。どの画面のボタンからも開けるようルート外に 1 つ置く */}
      <FavoritePromptHost />
      <AppRoutes />
    </>
  );
}

function AppRoutes() {
  // 007-chat-interactive-ux: React Router location
  const location = useLocation();
  const { state: settingsState } = useSettings();

  // ルートに基づいて専用画面を表示（各画面は内部でMainLayoutを持つ）。
  // NovelAI で生成する画面には NovelaiAccountCheckOnOpen を添え、直接開いたときも
  // 通常プレイと同じく同意とプランを確かめる(Prompt Expander は自前の同意ダイアログの後に画面内で行う)
  if (
    location.pathname === "/gallery" ||
    location.pathname.startsWith("/gallery/")
  ) {
    return <GalleryScreen />;
  }
  if (location.pathname === "/endings") {
    return <EndingsScreen />;
  }
  if (location.pathname === "/achievements") {
    return <AchievementsScreen />;
  }
  // 遊び方ガイド。既定OFFの機能を紹介してその場でONにできる(ゲートなし)
  if (location.pathname === "/guide") {
    return <GuideScreen />;
  }
  if (location.pathname === "/settings") {
    return <SettingsScreen />;
  }
  // TSFシナリオのBGMカタログを試聴する画面。ゲートはTSFシナリオと同一にする
  if (location.pathname === "/bgm-test") {
    if (!settingsState.adventureEnabled) {
      return <Navigate to="/play/new" replace />;
    }
    return <BgmTestScreen />;
  }
  if (location.pathname.startsWith("/adventure")) {
    if (!settingsState.adventureEnabled) {
      return <Navigate to="/play/new" replace />;
    }
    return (
      <AdventureProvider>
        <AdventureScreen />
        <NovelaiAccountCheckOnOpen />
      </AdventureProvider>
    );
  }
  // キャラチャット（既定 ON）。/talk と /talk/:threadId。ゲートは設定画面のトグル
  if (location.pathname === "/talk" || location.pathname.startsWith("/talk/")) {
    // TSFシナリオの「トーク」から遷移するため、Adventure が有効なら通す
    if (
      !settingsState.characterChatEnabled &&
      !settingsState.adventureEnabled
    ) {
      return <Navigate to="/play/new" replace />;
    }
    return (
      <CharacterChatProvider>
        <CharacterChatScreen />
        <NovelaiAccountCheckOnOpen />
      </CharacterChatProvider>
    );
  }
  // キャラクター（キャラクターの作成・管理と、そのキャラでのプレイ開始）。常に開ける
  if (
    location.pathname === "/characters" ||
    location.pathname.startsWith("/characters/")
  ) {
    return (
      <>
        <CharactersScreen />
        <NovelaiAccountCheckOnOpen />
      </>
    );
  }
  // サロン経営（実験機能）。/salon・/salon/:runId・/salon/:runId/visits/:visitId
  if (
    location.pathname === "/salon" ||
    location.pathname.startsWith("/salon/")
  ) {
    if (!settingsState.experimentalSalonEnabled) {
      return <Navigate to="/play/new" replace />;
    }
    return (
      <SalonProvider>
        <SalonScreen />
        <NovelaiAccountCheckOnOpen />
      </SalonProvider>
    );
  }
  // AI箱庭（実験機能）。/hakoniwa・/hakoniwa/:worldId
  if (
    location.pathname === "/hakoniwa" ||
    location.pathname.startsWith("/hakoniwa/")
  ) {
    if (!settingsState.experimentalHakoniwaEnabled) {
      return <Navigate to="/play/new" replace />;
    }
    return (
      <HakoniwaProvider>
        <HakoniwaScreen />
        <NovelaiAccountCheckOnOpen />
      </HakoniwaProvider>
    );
  }
  // Prompt Expander（実験機能）。ゲートは設定画面のトグルで切り替える
  if (location.pathname.startsWith("/prompt-expander")) {
    if (!settingsState.experimentalPromptExpanderEnabled) {
      return <Navigate to="/play/new" replace />;
    }
    return (
      <PromptExpanderProvider>
        <PromptExpanderScreen />
      </PromptExpanderProvider>
    );
  }

  // デフォルト: 新UIゲーム画面（/、/play、/play/new）
  return <AppMain />;
}

function AppMain() {
  // 旧UIで使用していた変数（新UIへの移行後、削除予定）
  const location = useLocation();
  const { state: settingsState, resetTotalCost } = useSettings();
  const {
    state: gameState,
    loadCharacters,
    restoreActiveSession,
    restoreSessionById,
    resetSession,
    setEnding,
    setError,
    ensureProtagonistCharacter,
  } = useGame();
  const { t } = useTranslation();
  // 旧UI用: 新UIではWelcomeScreenが担当 (型定義用にscreen変数を使用)
  const [, setScreen] = useState<"character-select" | "game">(
    "character-select",
  );
  const [showSessionList, setShowSessionList] = useState(false);
  const [providerLoading, setProviderLoading] = useState(true);

  // NovelAI の同意・Anlas 残高・プランの確認（サロン経営の画面と共有）
  const novelaiAccount = useNovelaiAccountCheck();

  const replacePathWithSessionId = useCallback((sessionId: string | null) => {
    if (!sessionId) {
      return;
    }
    window.history.replaceState(null, "", getGameSessionPath(sessionId));
  }, []);

  // FR-010: 複数人モード ON 時、セッションが確立されていれば
  // 主人公の session_character レコードを冪等に確保する。
  // セッション開始/再開直後やトグル OFF→ON 遷移時に発火し、
  // プレイ前から CharacterPanel に主人公枠を表示する。
  useEffect(() => {
    if (
      !gameState.sessionId ||
      !settingsState.enableMultiplePeople ||
      !settingsState.multiCharacterPanelEnabled
    ) {
      return;
    }
    void ensureProtagonistCharacter();
  }, [
    gameState.sessionId,
    settingsState.enableMultiplePeople,
    settingsState.multiCharacterPanelEnabled,
    ensureProtagonistCharacter,
  ]);

  // 初期化: セッション復元を試みる（/play/new の場合は復元しない）
  // マウント時のみ実行する意図的な空依存配列
  // biome-ignore lint/correctness/useExhaustiveDependencies: 初期化はマウント時のみ
  useEffect(() => {
    const init = async () => {
      await loadCharacters();

      // URLからセッションIDを抽出（/play/:sessionId 形式）
      const playMatch = location.pathname.match(/^\/play\/([a-f0-9-]+)$/i);
      const urlSessionId = playMatch ? playMatch[1] : null;

      // /play/new の場合は新規ゲーム開始なのでセッション復元をスキップ
      if (location.pathname === "/play/new") {
        // 新規ゲームなので何もしない
      } else if (urlSessionId) {
        // ギャラリー等から遷移済みで、GameContextに同じセッションが既にある場合はスキップ
        if (gameState.sessionId === urlSessionId) {
          setScreen("game");
        } else {
          // URLにセッションIDが含まれている場合、そのセッションを復元
          try {
            await restoreSessionById(urlSessionId);
            setScreen("game");
            // URLは既にセッションID付きなので更新不要
          } catch (err) {
            console.error("Error restoring session from URL:", err);
            // 復元失敗時はlocalStorageのセッションを復元
            const restored = await restoreActiveSession();
            if (restored) {
              setScreen("game");
              replacePathWithSessionId(
                readStorage("local", SESSION_STORAGE_KEY),
              );
            }
          }
        }
      } else {
        // 通常のセッション復元（/play や / にアクセス時）
        const restored = await restoreActiveSession();
        if (restored) {
          setScreen("game");
          replacePathWithSessionId(readStorage("local", SESSION_STORAGE_KEY));
        }
      }
      // 画像プロバイダー取得（NovelAI専用UI制御）
      // sessionStorageにキャッシュして同一タブ内での再取得を回避
      let detectedProvider: "selfhost" | "openrouter" | "novelai" = "selfhost";
      const cachedProvider = readStorage("session", IMAGE_PROVIDER_CACHE_KEY);
      const cachedShowCost = readStorage("session", SHOW_COST_CACHE_KEY);
      if (
        cachedProvider &&
        cachedShowCost !== null &&
        ["selfhost", "openrouter", "novelai"].includes(cachedProvider)
      ) {
        detectedProvider = cachedProvider as
          | "selfhost"
          | "openrouter"
          | "novelai";
        setProviderLoading(false);
      } else {
        try {
          const res = await fetch("/health");
          if (res.ok) {
            const data = await res.json();
            if (
              data.image_provider === "openrouter" ||
              data.image_provider === "novelai"
            ) {
              detectedProvider = data.image_provider;
            }
            const hasCostProvider = shouldShowCost(data);
            // キャッシュに保存
            writeStorage("session", IMAGE_PROVIDER_CACHE_KEY, detectedProvider);
            writeStorage(
              "session",
              SHOW_COST_CACHE_KEY,
              String(hasCostProvider),
            );
          }
          setProviderLoading(false);
        } catch (e) {
          console.warn("Failed to fetch /health", e);
          setProviderLoading(false);
        }
      }

      // NovelAIプロバイダーの場合、同意を確かめてから Anlas 残高とプランを取得
      if (detectedProvider === "novelai") {
        await novelaiAccount.startCheck();
      }
      // selfhost/openrouterの場合はNovelAIチェック不要
    };
    init();
  }, []);

  // 変身実行（送信内容の組み立ては usePlayTurn と共有）
  const handleTransform = usePlayTurn();

  // リセット
  const handleReset = useCallback(async () => {
    await resetSession();
    setScreen("character-select");
    setEnding(null);
  }, [resetSession, setEnding]);

  // コストリセット
  const handleResetCost = useCallback(() => {
    resetTotalCost();
  }, [resetTotalCost]);

  // 007-chat-interactive-ux: 新UIを使用
  // セッション開始時のコールバック（WelcomeScreen → GamePlayScreen → App.tsx）
  const handleSessionStart = useCallback(async () => {
    console.log("[App] Session started, restoring session data...");
    await restoreActiveSession();
    setScreen("game");
    replacePathWithSessionId(readStorage("local", SESSION_STORAGE_KEY));
  }, [replacePathWithSessionId, restoreActiveSession]);

  return (
    <div className="app">
      <GamePlayScreen
        onTransform={handleTransform}
        onResetCost={handleResetCost}
        onSessionStart={handleSessionStart}
      />

      {providerLoading && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="spinner"></div>
            <p>{t("appLoading.initializing")}</p>
          </div>
        </div>
      )}

      {gameState.isLoading && (
        <div className="loading-overlay">
          <div className="spinner"></div>
          <p>{t("appLoading.preparing")}</p>
        </div>
      )}

      {gameState.ending && (
        <EndingModal
          ending={gameState.ending}
          onClose={() => setEnding(null)}
          onRestart={handleReset}
          onGallery={() => {
            setEnding(null);
            window.location.assign("/gallery");
          }}
        />
      )}
      {showSessionList && (
        <SessionListModal
          onClose={() => setShowSessionList(false)}
          onSelectSession={async (sessionId) => {
            try {
              // セッションを復元（アクティブ化）
              const response = await fetch(
                `${API_BASE}/game/sessions/${sessionId}/restore`,
                {
                  method: "POST",
                },
              );
              if (response.ok) {
                // セッション情報を再読み込み
                await restoreSessionById(sessionId);
                // モーダルを閉じてゲーム画面に遷移
                setShowSessionList(false);
                setScreen("game");
              } else {
                console.error("Failed to restore session");
                setError("セッションの復元に失敗しました");
              }
            } catch (err) {
              console.error("Error restoring session:", err);
              setError("セッションの復元に失敗しました");
            }
          }}
        />
      )}

      {gameState.error && (
        <div className="error-modal-overlay" onClick={() => setError(null)}>
          <div className="error-modal" onClick={(e) => e.stopPropagation()}>
            <div className="error-modal-icon">⚠️</div>
            <h3>{t("appLoading.error")}</h3>
            <p>{gameState.error}</p>
            <button className="btn btn-primary" onClick={() => setError(null)}>
              {t("appLoading.close")}
            </button>
          </div>
        </div>
      )}

      <NovelaiAccountModals check={novelaiAccount} />
    </div>
  );
}
export default App;
