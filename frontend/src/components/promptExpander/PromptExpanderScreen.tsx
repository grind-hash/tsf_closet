/**
 * PromptExpanderScreen - Prompt Expander 画面（実験機能）
 *
 * /prompt-expander            → セッション一覧
 * /prompt-expander/:sessionId → コンポーザ + エントリ一覧
 *
 * ヘッダーに V5 利用上限バー / Anlas 残高 / 設定パネルの開閉ボタンを置く。
 * 設定パネルは MainLayout の右サイドパネルとして表示し、開閉状態は PE 専用に
 * localStorage（prompt_expander_settings_panel_open）へ保持する
 * （ゲーム画面の rightPanelOpen 設定とは共有しない）。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import ApiKeyConsentModal from "../ApiKeyConsentModal";
import AdventureAnlasConfirmDialog from "../adventure/AdventureAnlasConfirmDialog";
import { hasApiKeyConsent } from "../apiKeyConsentStorage";
import MainLayout from "../layout/MainLayout";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import PromptExpanderComposer from "./PromptExpanderComposer";
import PromptExpanderEntryList from "./PromptExpanderEntryList";
import PromptExpanderSessionList from "./PromptExpanderSessionList";
import PromptExpanderSettingsPanel, {
  PROMPT_EXPANDER_SETTINGS_PANEL_ID,
} from "./PromptExpanderSettingsPanel";
import "./PromptExpanderShared.css";
import "./PromptExpanderScreen.css";

export const PROMPT_EXPANDER_SETTINGS_PANEL_OPEN_KEY =
  "prompt_expander_settings_panel_open";

function readSettingsPanelOpen(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return (
      window.localStorage.getItem(PROMPT_EXPANDER_SETTINGS_PANEL_OPEN_KEY) ===
      "true"
    );
  } catch {
    return false;
  }
}

function writeSettingsPanelOpen(open: boolean) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      PROMPT_EXPANDER_SETTINGS_PANEL_OPEN_KEY,
      open ? "true" : "false",
    );
  } catch {
    // 保存できなくても開閉は続行する
  }
}

// Context 側の検証コードを表示文言に変換する。API 由来のメッセージはそのまま返す
const ERROR_CODE_KEYS: Record<string, string> = {
  empty_prompt: "promptExpander.errors.emptyPrompt",
  too_many_characters: "promptExpander.errors.tooManyCharacters",
  session_not_selected: "promptExpander.errors.noSession",
};

export default function PromptExpanderScreen() {
  const { t } = useTranslation();
  const location = useLocation();
  const {
    settings,
    options,
    anlas,
    error,
    clearError,
    activeSession,
    loadingSession,
    loadSessions,
    openSession,
    pendingUsageWarn,
    confirmUsageWarn,
    cancelUsageWarn,
  } = usePromptExpander();

  const sessionId = useMemo(() => {
    const segments = location.pathname.split("/");
    const id = segments[2];
    return id ? decodeURIComponent(id) : null;
  }, [location.pathname]);

  const [showSettings, setShowSettingsState] = useState<boolean>(
    readSettingsPanelOpen,
  );
  const setShowSettings = useCallback((open: boolean) => {
    setShowSettingsState(open);
    writeSettingsPanelOpen(open);
  }, []);
  const toggleSettings = useCallback(
    () => setShowSettings(!showSettings),
    [setShowSettings, showSettings],
  );

  const [showApiKeyConsent, setShowApiKeyConsent] = useState(
    () => !hasApiKeyConsent(),
  );
  const [apiKeyConsentDeclined, setApiKeyConsentDeclined] = useState(false);

  // ルートに応じて一覧/詳細を読み込む
  useEffect(() => {
    if (sessionId) {
      void openSession(sessionId);
    } else {
      void loadSessions();
    }
  }, [sessionId, openSession, loadSessions]);

  // 抑止フラグ(sessionStorage)の保存は Context 側の confirmUsageWarn が行う
  const handleUsageConfirm = useCallback(
    (suppress: boolean) => {
      void confirmUsageWarn(suppress);
    },
    [confirmUsageWarn],
  );

  const errorText = error
    ? ERROR_CODE_KEYS[error]
      ? t(ERROR_CODE_KEYS[error])
      : error
    : null;

  const showUsageBar = isV5ImageModel(settings.image_model) && anlas?.usage;

  return (
    <MainLayout
      rightPanel={
        <PromptExpanderSettingsPanel onClose={() => setShowSettings(false)} />
      }
      showRightPanel={showSettings}
      onToggleRightPanel={toggleSettings}
    >
      <div className="prompt-expander">
        <header className="prompt-expander__header">
          <div className="prompt-expander__header-main">
            <h1 className="prompt-expander__title">
              {t("promptExpander.header.title")}
              <span className="feature-chip-experimental">Experimental</span>
            </h1>
            <p className="prompt-expander__subtitle">
              {t("promptExpander.header.subtitle")}
            </p>
          </div>
          <div className="prompt-expander__header-side">
            {showUsageBar && anlas?.usage && (
              <NovelaiUsageBar
                usage={anlas.usage}
                compact
                className="prompt-expander__usage-bar"
              />
            )}
            {anlas && (
              <span
                className="prompt-expander__anlas"
                title={t("promptExpander.header.anlasTitle")}
              >
                {t("promptExpander.header.anlas", {
                  value: anlas.totalAnlas.toLocaleString(),
                })}
              </span>
            )}
            <button
              type="button"
              className={`prompt-expander__btn ${showSettings ? "prompt-expander__btn--primary" : ""}`}
              onClick={toggleSettings}
              aria-expanded={showSettings}
              aria-controls={PROMPT_EXPANDER_SETTINGS_PANEL_ID}
              title={
                showSettings
                  ? t("promptExpander.header.settingsClose")
                  : t("promptExpander.header.settingsOpenTitle")
              }
            >
              {t("promptExpander.header.settingsToggle")}
            </button>
          </div>
        </header>

        {!options.novelaiConfigured && (
          <p className="prompt-expander__notice" role="status">
            {t("promptExpander.header.notConfigured")}
          </p>
        )}

        {errorText && (
          <div className="prompt-expander__error-row" role="alert">
            <p className="prompt-expander__error">{errorText}</p>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={clearError}
            >
              {t("promptExpander.header.dismissError")}
            </button>
          </div>
        )}

        {sessionId ? (
          <div className="prompt-expander__workspace">
            <section
              className="prompt-expander__workspace-composer"
              aria-label={t("promptExpander.composer.sectionLabel")}
            >
              {loadingSession && !activeSession ? (
                <p className="prompt-expander__empty">
                  {t("promptExpander.sessions.loading")}
                </p>
              ) : activeSession ? (
                <PromptExpanderComposer />
              ) : (
                <p className="prompt-expander__empty">
                  {t("promptExpander.sessions.notFound")}
                </p>
              )}
            </section>
            <section
              className="prompt-expander__workspace-entries"
              aria-label={t("promptExpander.entry.sectionLabel")}
            >
              <PromptExpanderEntryList />
            </section>
          </div>
        ) : (
          <PromptExpanderSessionList />
        )}
      </div>

      <AdventureAnlasConfirmDialog
        open={pendingUsageWarn !== null}
        body={t("gameplay.v5UsageExhaustedBody")}
        onConfirm={handleUsageConfirm}
        onCancel={cancelUsageWarn}
      />

      {showApiKeyConsent && (
        <ApiKeyConsentModal
          onConsent={() => setShowApiKeyConsent(false)}
          onDecline={() => {
            setShowApiKeyConsent(false);
            setApiKeyConsentDeclined(true);
          }}
        />
      )}

      {apiKeyConsentDeclined && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="consent-declined-message">
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
    </MainLayout>
  );
}
