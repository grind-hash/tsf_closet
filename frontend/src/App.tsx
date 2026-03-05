import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSession } from "./hooks/useSession";
import { useSSE } from "./hooks/useSSE";
import { useNotification } from "./contexts/NotificationContext";
import { useSettings } from "./contexts/SettingsContext";
import { getGameSessionPath } from "./routes";
import { API_BASE } from "./utils/api";

import GamePlayScreen from "./components/GamePlayScreen";
import EndingModal from "./components/EndingModal";
import SessionListModal from "./components/SessionListModal";
import NovelAIWarningModal from "./components/NovelAIWarningModal";
import ApiKeyConsentModal from "./components/ApiKeyConsentModal";
import { hasApiKeyConsent } from "./components/apiKeyConsentStorage";
import NotificationContainer from "./components/notifications/NotificationContainer";
// 007-chat-interactive-ux: ルートベースの画面コンポーネント
import GalleryScreen from "./components/gallery/GalleryScreen";
import AchievementsScreen from "./components/achievements/AchievementsScreen";
import EndingsScreen from "./components/endings/EndingsScreen";
import SettingsScreen from "./components/settings/SettingsScreen";
// MainLayout は各画面コンポーネント内で使用
import type {
  Ending,
  ChangeSettings,
  NovelAISubscriptionResponse,
} from "./types";
import { DEFAULT_CHANGE_SETTINGS, DEFAULT_INPAINT_SETTINGS } from "./types";
import "./App.css";

// 007-chat-interactive-ux: Context hooks
import { useGame } from "./contexts/GameContext";

function App() {
  // 007-chat-interactive-ux: React Router location
  const location = useLocation();
  const { state: settingsState } = useSettings();
  console.log("[App] Current route:", location.pathname);

  // ルートに基づいて専用画面を表示（各画面は内部でMainLayoutを持つ）
  if (location.pathname === "/gallery") {
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
  const session = useSession();
  const { state: settingsState } = useSettings();
  const { setTransforming } = useGame();
  const { showNotification, showAchievementNotification } = useNotification();
  const { t } = useTranslation();
  // 旧UI用: 新UIではWelcomeScreenが担当 (型定義用にscreen変数を使用)
  const [screen, setScreen] = useState<"character-select" | "game">(
    "character-select",
  );
  console.log("[App] Current screen:", screen, "route:", location.pathname);
  const [feelingText, setFeelingText] = useState("");
  const [isTransforming, setIsTransforming] = useState(false);
  const [ending, setEnding] = useState<Ending | null>(null);
  const [showSessionList, setShowSessionList] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [imageProvider, setImageProvider] = useState<
    "selfhost" | "openrouter" | "novelai"
  >("selfhost");
  const [providerLoading, setProviderLoading] = useState(true);
  // コスト表示フラグ: いずれかのproviderがopenrouterの場合に表示
  const [showCost, setShowCost] = useState(false);

  // NovelAIサブスクリプション警告関連
  const [novelaiTier, setNovelaiTier] = useState<number | null>(null);
  const [showNovelaiWarning, setShowNovelaiWarning] = useState(false);
  const [novelaiCheckLoading, setNovelaiCheckLoading] = useState(false);
  // NovelAI APIキー同意モーダル関連
  const [showApiKeyConsent, setShowApiKeyConsent] = useState(false);
  const [apiKeyConsentDeclined, setApiKeyConsentDeclined] = useState(false);

  // Last generated seed (from SSE image event)
  const [lastGeneratedSeed, setLastGeneratedSeed] = useState<number | null>(
    null,
  );

  // US2: Last generated surroundings image (from SSE)
  const [lastSurroundingsImage, setLastSurroundingsImage] = useState<{
    imageBase64: string;
    historyId: string;
    seed?: number;
  } | null>(null);

  // US5: Anlas balance state
  const [anlasBalance, setAnlasBalance] = useState<{
    fixedAnlas: number;
    purchasedAnlas: number;
    totalAnlas: number;
  } | null>(null);

  // API累積コスト (localStorage永続化)
  const [totalCost, setTotalCost] = useState<number>(() => {
    const saved = localStorage.getItem("api_total_cost");
    return saved ? parseFloat(saved) : 0;
  });

  // 変更設定 (localStorage永続化)
  const [changeSettings, setChangeSettings] = useState<ChangeSettings>(() => {
    const saved = localStorage.getItem("change_settings");
    if (saved) {
      try {
        return { ...DEFAULT_CHANGE_SETTINGS, ...JSON.parse(saved) };
      } catch {
        return DEFAULT_CHANGE_SETTINGS;
      }
    }
    return DEFAULT_CHANGE_SETTINGS;
  });

  // 変更設定の更新ハンドラ
  const handleChangeSettingsUpdate = useCallback((settings: ChangeSettings) => {
    setChangeSettings(settings);
    localStorage.setItem("change_settings", JSON.stringify(settings));
  }, []);

  // SSEハンドラ
  const sse = useSSE({
    onText: (chunk) => {
      setFeelingText((prev) => prev + chunk);
    },
    onImage: async (image, historyId, seed) => {
      session.updateFromSSE({ image, historyId });
      // Store the last generated seed for display
      if (seed !== undefined) {
        setLastGeneratedSeed(seed);
      }
      // Reload session to update history
      await session.restoreSession();
      // Note: isTransforming is cleared by onComplete, not here.
      // This allows surroundings image generation to continue with
      // the progress indicator still visible.
    },
    // US2: Surroundings image handler
    onSurroundingsImage: (imageBase64, historyId, seed) => {
      setLastSurroundingsImage({ imageBase64, historyId, seed });
    },
    onStats: (stats) => {
      session.updateStats({
        bloom: stats.bloom,
        shame: stats.shame,
        adaptation: stats.adaptation,
      });
    },
    onCritical: (data) => {
      // 臨界点イベント - 心境テキストに特別セリフを追加
      console.log("Critical point reached:", data.name, data.threshold);
      setFeelingText((prev) => prev + `\n\n【${data.name}】\n${data.speech}`);
    },
    onEnding: (data) => {
      if (!settingsState.experimentalEndingEnabled) return;
      // バックエンドのフィールド名をフロントエンドの型にマッピング
      setEnding({
        id: data.ending_id,
        name: data.title, // title → name
        description: data.description,
        triggerCondition: "",
        badge: data.badge,
        speech: data.final_speech, // final_speech → speech
        summary: data.summary,
      });
    },
    // 007-chat-interactive-ux: 実績解除通知
    onAchievement: (data) => {
      showAchievementNotification({
        id: data.achievement_id,
        name: data.name,
        description: data.description,
        icon: data.icon,
        category: data.category,
        condition_type: "",
        condition_target: "",
        condition_value: 0,
        is_hidden: false,
      });
    },
    onComplete: async (_, transformationCount) => {
      session.updateFromSSE({ transformationCount });
      setIsTransforming(false);
      setTransforming(false);
    },
    onCost: (cost) => {
      setTotalCost((prev) => {
        const newTotal = prev + cost;
        localStorage.setItem("api_total_cost", newTotal.toString());
        return newTotal;
      });
    },
    // US5: Anlas balance update
    onAnlas: (balance) => {
      setAnlasBalance(balance);
    },
    // Reality change: auto-added attribute notification
    onRealityAttributeAdded: (data) => {
      // Update local attributes state
      session.updateAttributesFromSSE({
        id: data.attribute_id,
        text: data.attribute_text,
      });
      // Show notification if enabled in settings
      if (settingsState.showRealityAttributeNotification) {
        const msg =
          t("settings.realityAttributeAddedMsg", {
            attr: data.attribute_text,
          }) +
          "\n" +
          t("settings.realityAttributeAddedLink");
        showNotification(
          "info",
          t("settings.realityAttributeAdded"),
          msg,
          8000,
        );
      }
    },
    onError: (message) => {
      console.error("SSE Error:", message);
      setErrorMessage(message);
      setIsTransforming(false);
      setTransforming(false);
    },
  });

  // 初期化: セッション復元を試みる（/play/new の場合は復元しない）
  useEffect(() => {
    const init = async () => {
      await session.loadCharacters();

      // URLからセッションIDを抽出（/play/:sessionId 形式）
      const playMatch = location.pathname.match(/^\/play\/([a-f0-9-]+)$/i);
      const urlSessionId = playMatch ? playMatch[1] : null;

      // /play/new の場合は新規ゲーム開始なのでセッション復元をスキップ
      if (location.pathname === "/play/new") {
        // 新規ゲームなので何もしない
      } else if (urlSessionId) {
        // URLにセッションIDが含まれている場合、そのセッションを復元
        try {
          const response = await fetch(
            `${API_BASE}/game/sessions/${urlSessionId}/restore`,
            { method: "POST" },
          );
          if (response.ok) {
            await session.restoreSession();
            setScreen("game");
            // URLは既にセッションID付きなので更新不要
          } else {
            console.warn("Failed to restore session from URL:", urlSessionId);
            // 復元失敗時はlocalStorageのセッションを復元
            const restored = await session.restoreSession();
            if (restored) {
              setScreen("game");
              // URLをセッションID付きに更新
              if (session.sessionId) {
                window.history.replaceState(
                  null,
                  "",
                  getGameSessionPath(session.sessionId),
                );
              }
            }
          }
        } catch (err) {
          console.error("Error restoring session from URL:", err);
          const restored = await session.restoreSession();
          if (restored) {
            setScreen("game");
            // URLをセッションID付きに更新
            if (session.sessionId) {
              window.history.replaceState(
                null,
                "",
                getGameSessionPath(session.sessionId),
              );
            }
          }
        }
      } else {
        // 通常のセッション復元（/play や / にアクセス時）
        const restored = await session.restoreSession();
        if (restored) {
          setScreen("game");
          // URLをセッションID付きに更新
          if (session.sessionId) {
            window.history.replaceState(
              null,
              "",
              getGameSessionPath(session.sessionId),
            );
          }
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
        setImageProvider(detectedProvider);
        setShowCost(cachedShowCost === "true");
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
              setImageProvider(data.image_provider);
            } else {
              setImageProvider("selfhost");
            }
            // いずれかのproviderがopenrouterならコスト表示
            const hasCostProvider =
              data.image_provider === "openrouter" ||
              data.image_description_provider === "openrouter" ||
              data.feeling_provider === "openrouter";
            setShowCost(hasCostProvider);
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

  // NovelAI APIキー同意後のサブスクリプションチェック
  const handleApiKeyConsent = useCallback(async () => {
    setShowApiKeyConsent(false);

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
  }, []);

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
    ) => {
      if (!session.sessionId || isTransforming) return;

      setIsTransforming(true);
      setTransforming(true);
      setFeelingText("");

      // POST リクエストボディを構築
      const body: Record<string, unknown> = {
        session_id: session.sessionId,
        instruction,
        transformation_type: transformationType,
        language: settingsState.language,
      };
      if (instructionType) {
        body.instruction_type = instructionType;
      }
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
      if (imageProvider === "novelai") {
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

      sse.startPostStream(`${API_BASE}/game/play/stream`, body);
    },
    [
      session.sessionId,
      isTransforming,
      sse,
      imageProvider,
      settingsState.language,
      settingsState.seed,
      settingsState.enableSurroundingsImage,
      settingsState.surroundingsIncludePeople,
      setTransforming,
    ],
  );

  // 画質改善
  const handleImproveQuality = useCallback(() => {
    if (!session.sessionId || isTransforming) return;

    setIsTransforming(true);
    setTransforming(true);
    setFeelingText("");

    const url = `${API_BASE}/game/improve-quality/stream?session_id=${session.sessionId}`;
    sse.startStream(url);
  }, [session.sessionId, isTransforming, sse, setTransforming]);

  // リセット
  const handleReset = useCallback(async () => {
    await session.resetSession();
    setScreen("character-select");
    setFeelingText("");
    setEnding(null);
  }, [session]);

  // コストリセット
  const handleResetCost = useCallback(() => {
    setTotalCost(0);
    localStorage.setItem("api_total_cost", "0");
  }, []);

  // 履歴選択
  const handleSelectHistory = useCallback(
    async (historyId: string) => {
      try {
        const response = await fetch(
          `${API_BASE}/game/history/${historyId}/select`,
          {
            method: "POST",
          },
        );
        if (response.ok) {
          await session.restoreSession();
          // 選択した履歴の心境テキストを表示
          const historyItem = session.history.find((h) => h.id === historyId);
          if (
            historyItem?.feelingText &&
            historyItem.feelingText !== "(画質改善)"
          ) {
            setFeelingText(historyItem.feelingText);
          }
        }
      } catch (err) {
        console.error("Failed to select history:", err);
      }
    },
    [session],
  );

  // 007-chat-interactive-ux: 新UIを使用
  // セッション開始時のコールバック（WelcomeScreen → GamePlayScreen → App.tsx）
  const handleSessionStart = useCallback(async () => {
    console.log("[App] Session started, restoring session data...");
    await session.restoreSession();
    setScreen("game");
    // URLをセッションID付きに更新（ブラウザ履歴を置換）
    if (session.sessionId) {
      window.history.replaceState(
        null,
        "",
        getGameSessionPath(session.sessionId),
      );
    }
  }, [session]);

  return (
    <div className="app">
      {/* 通知トーストコンテナ */}
      <NotificationContainer />

      <GamePlayScreen
        sessionId={session.sessionId}
        currentImageUrl={session.currentImageUrl}
        stats={session.stats}
        transformationCount={session.transformationCount}
        history={session.history}
        attributes={session.attributes}
        feelingText={feelingText}
        isTransforming={isTransforming}
        chatHistory={session.conversationHistory}
        onChatHistoryChange={session.setConversationHistory}
        onTransform={handleTransform}
        onImproveQuality={handleImproveQuality}
        onReset={handleReset}
        onSelectHistory={handleSelectHistory}
        onAddAttribute={session.addAttribute}
        onRemoveAttribute={session.removeAttribute}
        totalCost={totalCost}
        onResetCost={handleResetCost}
        showCost={showCost}
        changeSettings={changeSettings}
        onChangeSettingsUpdate={handleChangeSettingsUpdate}
        imageProvider={imageProvider}
        selfMode={session.selfMode}
        onSessionStart={handleSessionStart}
        lastGeneratedSeed={lastGeneratedSeed}
        anlasBalance={anlasBalance}
        onAnlasBalanceChange={setAnlasBalance}
        lastSurroundingsImage={lastSurroundingsImage}
        onClearSurroundingsImage={() => setLastSurroundingsImage(null)}
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

      {session.isLoading && (
        <div className="loading-overlay">
          <div className="spinner"></div>
          <p>{t("appLoading.preparing")}</p>
        </div>
      )}

      {ending && (
        <EndingModal
          ending={ending}
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
                await session.restoreSession();
                // モーダルを閉じてゲーム画面に遷移
                setShowSessionList(false);
                setScreen("game");
              } else {
                console.error("Failed to restore session");
                setErrorMessage("セッションの復元に失敗しました");
              }
            } catch (err) {
              console.error("Error restoring session:", err);
              setErrorMessage("セッションの復元に失敗しました");
            }
          }}
        />
      )}

      {errorMessage && (
        <div
          className="error-modal-overlay"
          onClick={() => setErrorMessage(null)}
        >
          <div className="error-modal" onClick={(e) => e.stopPropagation()}>
            <div className="error-modal-icon">⚠️</div>
            <h3>{t("appLoading.error")}</h3>
            <p>{errorMessage}</p>
            <button
              className="btn btn-primary"
              onClick={() => setErrorMessage(null)}
            >
              {t("appLoading.close")}
            </button>
          </div>
        </div>
      )}

      {/* NovelAI非Opusプラン警告モーダル */}
      {showNovelaiWarning && novelaiTier !== null && (
        <NovelAIWarningModal
          tier={novelaiTier}
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
