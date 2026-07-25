import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useGameSSE } from "./hooks/useGameSSE";
import { useSettings } from "./contexts/SettingsContext";
import { getGameSessionPath } from "./routes";
import { API_BASE } from "./utils/api";

import GamePlayScreen from "./components/GamePlayScreen";
import EndingModal from "./components/EndingModal";
import SessionListModal from "./components/SessionListModal";
import NovelAIWarningModal from "./components/NovelAIWarningModal";
import ApiKeyConsentModal from "./components/ApiKeyConsentModal";
import { hasApiKeyConsent } from "./components/apiKeyConsentStorage";
import { fetchAnlasBalance } from "./apis/anlas";
import NotificationContainer from "./components/notifications/NotificationContainer";
// 007-chat-interactive-ux: ルートベースの画面コンポーネント
import GalleryScreen from "./components/gallery/GalleryScreen";
import AchievementsScreen from "./components/achievements/AchievementsScreen";
import EndingsScreen from "./components/endings/EndingsScreen";
import SettingsScreen from "./components/settings/SettingsScreen";
// MainLayout は各画面コンポーネント内で使用
import type { ChangeSettings, NovelAISubscriptionResponse } from "./types";
import { DEFAULT_INPAINT_SETTINGS } from "./types";
import "./App.css";

// 007-chat-interactive-ux: Context hooks
import { useGame } from "./contexts/GameContext";

function App() {
  // 007-chat-interactive-ux: React Router location
  const location = useLocation();
  const { state: settingsState } = useSettings();

  // ルートに基づいて専用画面を表示（各画面は内部でMainLayoutを持つ）
  if (
    location.pathname === "/gallery" ||
    location.pathname.startsWith("/gallery/")
  ) {
    return <GalleryScreen />;
  }
  if (
    location.pathname === "/endings" &&
    settingsState.experimentalEndingEnabled
  ) {
    return <EndingsScreen />;
  }
  if (location.pathname === "/achievements") {
    return <AchievementsScreen />;
  }
  if (location.pathname === "/settings") {
    return <SettingsScreen />;
  }

  // デフォルト: 新UIゲーム画面（/、/play、/play/new）
  return <AppMain />;
}

function AppMain() {
  // 旧UIで使用していた変数（新UIへの移行後、削除予定）
  const location = useLocation();
  const {
    state: settingsState,
    resetTotalCost,
    setAnlasBalance,
    setNovelaiTier,
  } = useSettings();
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

  // NovelAIサブスクリプション警告関連
  const [showNovelaiWarning, setShowNovelaiWarning] = useState(false);
  const [novelaiCheckLoading, setNovelaiCheckLoading] = useState(false);
  // NovelAI APIキー同意モーダル関連
  const [showApiKeyConsent, setShowApiKeyConsent] = useState(false);
  const [apiKeyConsentDeclined, setApiKeyConsentDeclined] = useState(false);

  const sse = useGameSSE();

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
                localStorage.getItem("current_session_id"),
              );
            }
          }
        }
      } else {
        // 通常のセッション復元（/play や / にアクセス時）
        const restored = await restoreActiveSession();
        if (restored) {
          setScreen("game");
          replacePathWithSessionId(localStorage.getItem("current_session_id"));
        }
      }
      // 画像プロバイダー取得（NovelAI専用UI制御）
      // sessionStorageにキャッシュして同一タブ内での再取得を回避
      let detectedProvider: "selfhost" | "openrouter" | "novelai" = "selfhost";
      const cachedProvider = sessionStorage.getItem("image_provider");
      const cachedShowCost = sessionStorage.getItem("show_cost");
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
            // いずれかのproviderがopenrouterならコスト表示
            const hasCostProvider =
              data.image_provider === "openrouter" ||
              data.image_description_provider === "openrouter" ||
              data.feeling_provider === "openrouter";
            // キャッシュに保存
            sessionStorage.setItem("image_provider", detectedProvider);
            sessionStorage.setItem("show_cost", String(hasCostProvider));
          }
          setProviderLoading(false);
        } catch (e) {
          console.warn("Failed to fetch /health", e);
          setProviderLoading(false);
        }
      }

      // NovelAIプロバイダーの場合、まず同意をチェック
      if (detectedProvider === "novelai") {
        // 同意済みでなければ同意モーダルを表示
        if (!hasApiKeyConsent()) {
          setShowApiKeyConsent(true);
          return; // 同意を待ってから続行
        }

        // 同意済み: Anlas残高を取得
        fetchAnlasBalance().then((balance) => {
          if (balance) {
            setAnlasBalance(balance);
          }
        });

        // 同意済みの場合はサブスクリプションをチェック
        // localStorageで既に確認済みかチェック
        const opusConfirmed = localStorage.getItem("novelai_opus_confirmed");
        if (opusConfirmed === "true") {
          return;
        }

        // チェック開始時にローディング表示
        setNovelaiCheckLoading(true);

        try {
          const subRes = await fetch("/novelai/subscription");
          if (subRes.ok) {
            const subData: NovelAISubscriptionResponse = await subRes.json();
            setNovelaiTier(subData.tier);

            // tier !== 3 (非Opus) の場合、警告を表示
            if (subData.tier !== 3) {
              setShowNovelaiWarning(true);
            }
          }
        } catch (e) {
          console.warn("Failed to check NovelAI subscription:", e);
        } finally {
          setNovelaiCheckLoading(false);
        }
      }
      // selfhost/openrouterの場合はNovelAIチェック不要
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // NovelAI APIキー同意後のサブスクリプションチェック + Anlas取得
  const handleApiKeyConsent = useCallback(async () => {
    setShowApiKeyConsent(false);

    // 同意後、Anlas残高を取得
    fetchAnlasBalance().then((balance) => {
      if (balance) {
        setAnlasBalance(balance);
      }
    });

    // 同意後、サブスクリプションをチェック
    const opusConfirmed = localStorage.getItem("novelai_opus_confirmed");
    if (opusConfirmed === "true") {
      return;
    }

    setNovelaiCheckLoading(true);
    try {
      const subRes = await fetch("/novelai/subscription");
      if (subRes.ok) {
        const subData: NovelAISubscriptionResponse = await subRes.json();
        setNovelaiTier(subData.tier);

        if (subData.tier !== 3) {
          setShowNovelaiWarning(true);
        }
      }
    } catch (e) {
      console.warn("Failed to check NovelAI subscription:", e);
    } finally {
      setNovelaiCheckLoading(false);
    }
  }, [setAnlasBalance, setNovelaiTier]);

  // NovelAI APIキー同意を拒否
  const handleApiKeyConsentDecline = useCallback(() => {
    setShowApiKeyConsent(false);
    setApiKeyConsentDeclined(true);
  }, []);

  // 変身実行
  const handleTransform = useCallback(
    (
      instruction: string,
      costumeImage?: string,
      settings?: ChangeSettings,
      transformationType: string = "costume",
      options?: {
        maskImage?: string;
        maskId?: string;
        inpaintStrength?: number;
        inpaintNoise?: number;
        negativePrompt?: string;
        promptOverride?: string;
        characterReferences?: Array<{
          imageData: string;
          type: string;
          strength: number;
          fidelity: number;
        }>;
      },
      instructionType?: string,
      pendingToken?: string,
      useMemory: boolean = false,
    ) => {
      void pendingToken;
      if (!gameState.sessionId || gameState.isTransforming) return;

      // POST リクエストボディを構築
      const body: Record<string, unknown> = {
        session_id: gameState.sessionId,
        instruction,
        transformation_type: transformationType,
        language: settingsState.language,
      };
      if (instructionType) {
        body.instruction_type = instructionType;
      }
      body.use_memory = useMemory;
      body.use_play_memory = settingsState.playMemoryEnabled;
      // Include seed if specified in settings
      if (settingsState.seed !== null) {
        body.seed = settingsState.seed;
      }
      // US3: Include surroundings image generation setting
      if (settingsState.enableSurroundingsImage) {
        body.enable_surroundings_image = true;
        if (settingsState.surroundingsIncludePeople) {
          body.surroundings_include_people = true;
        }
      }
      // Clothing color consistency experimental feature
      if (settingsState.clothingColorConsistency) {
        body.clothing_color_consistency = true;
      }
      if (settingsState.respectClothingLayers) {
        body.respect_clothing_layers = true;
      }

      // Multiple people experimental feature.
      // パネル OFF でも複数人表示自体は維持し、
      // 画像プロンプトへの session_characters 注入のみ use_character_panel でゲートする。
      if (settingsState.enableMultiplePeople) {
        body.enable_multiple_people = true;
      }
      body.use_character_panel = settingsState.multiCharacterPanelEnabled;
      if (costumeImage) {
        body.costume_image = costumeImage;
      }
      if (options?.maskImage) {
        body.mask_image = options.maskImage;
      } else if (options?.maskId) {
        body.mask_id = options.maskId;
      }

      // NovelAI利用時は常にi2i強度とノイズを送信（Image2Image必須）
      // optionsで明示的に指定された場合はそちらを優先、なければデフォルト値を使用
      if (settingsState.imageProvider === "novelai") {
        body.inpaint_strength =
          options?.inpaintStrength ?? DEFAULT_INPAINT_SETTINGS.i2iStrength;
        body.inpaint_noise =
          options?.inpaintNoise ?? DEFAULT_INPAINT_SETTINGS.inpaintNoise;
      } else {
        // NovelAI以外の場合は、明示的に指定された場合のみ送信
        if (options?.inpaintStrength !== undefined) {
          body.inpaint_strength = options.inpaintStrength;
        }
        if (options?.inpaintNoise !== undefined) {
          body.inpaint_noise = options.inpaintNoise;
        }
      }

      if (options?.negativePrompt) {
        body.negative_prompt = options.negativePrompt;
      }
      if (options?.promptOverride) {
        body.prompt_override = options.promptOverride;
      }
      // Add change settings
      if (settings) {
        body.preserve_elements = settings.preserveElements;
        body.change_scope = settings.changeScope;
        body.custom_preserve_text = settings.customPreserveText;
      }

      // Build character_references for NovelAI precise reference images
      if (
        options?.characterReferences &&
        options.characterReferences.length > 0
      ) {
        body.character_references = options.characterReferences.map((ref) => {
          // Strip data URL prefix (e.g. "data:image/png;base64,") to get raw base64
          let imageBase64 = ref.imageData;
          if (imageBase64.startsWith("data:")) {
            imageBase64 = imageBase64.split(",", 2)[1] || imageBase64;
          }
          return {
            image: imageBase64,
            type: ref.type,
            strength: ref.strength,
            fidelity: ref.fidelity,
          };
        });
      }

      sse.startPostStream(`${API_BASE}/game/play/stream`, body, pendingToken);
    },
    [
      gameState.sessionId,
      gameState.isTransforming,
      sse,
      settingsState.language,
      settingsState.seed,
      settingsState.enableSurroundingsImage,
      settingsState.surroundingsIncludePeople,
      settingsState.clothingColorConsistency,
      settingsState.respectClothingLayers,
      settingsState.enableMultiplePeople,
      settingsState.multiCharacterPanelEnabled,
      settingsState.imageProvider,
      settingsState.playMemoryEnabled,
    ],
  );

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
    replacePathWithSessionId(localStorage.getItem("current_session_id"));
  }, [replacePathWithSessionId, restoreActiveSession]);

  return (
    <div className="app">
      {/* 通知トーストコンテナ */}
      <NotificationContainer />

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

      {novelaiCheckLoading && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="spinner"></div>
            <p>{t("appLoading.checkingNovelai")}</p>
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

      {/* NovelAI非Opusプラン警告モーダル */}
      {showNovelaiWarning && settingsState.novelaiTier !== null && (
        <NovelAIWarningModal
          tier={settingsState.novelaiTier}
          onContinue={() => {
            // 続行を選択: localStorageに保存して警告を閉じる
            localStorage.setItem("novelai_opus_confirmed", "true");
            setShowNovelaiWarning(false);
          }}
          onCancel={() => {
            // キャンセル: 警告を閉じるのみ（次回起動時に再表示）
            setShowNovelaiWarning(false);
          }}
        />
      )}

      {/* NovelAI APIキー利用同意モーダル */}
      {showApiKeyConsent && (
        <ApiKeyConsentModal
          onConsent={handleApiKeyConsent}
          onDecline={handleApiKeyConsentDecline}
        />
      )}

      {/* APIキー同意拒否時のメッセージ */}
      {apiKeyConsentDeclined && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="consent-declined-message">
              <span className="consent-declined-icon">🔒</span>
              <h3>{t("consentDeclined.title")}</h3>
              <p>{t("consentDeclined.message")}</p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => window.location.reload()}
              >
                {t("consentDeclined.reload")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
export default App;
