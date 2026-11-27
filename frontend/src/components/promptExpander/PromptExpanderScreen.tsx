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
import { useLocation, useNavigate } from "react-router-dom";
import { isV5ImageModel } from "../../constants/novelaiImageModels";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import { usePersistedState } from "../../hooks/usePersistedState";
import type { TranslationKey } from "../../i18n";
import { ROUTES } from "../../routes";
import ApiKeyConsentModal from "../ApiKeyConsentModal";
import { hasApiKeyConsent } from "../apiKeyConsentStorage";
import MainLayout from "../layout/MainLayout";
import { NovelaiAccountCheckOnOpen } from "../NovelaiAccountModals";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import PromptExpanderComposer from "./PromptExpanderComposer";
import PromptExpanderControlBar from "./PromptExpanderControlBar";
import PromptExpanderEntryList from "./PromptExpanderEntryList";
import PromptExpanderSessionList from "./PromptExpanderSessionList";
import PromptExpanderSessionRenameForm from "./PromptExpanderSessionRenameForm";
import PromptExpanderSettingsPanel, {
  PROMPT_EXPANDER_SETTINGS_PANEL_ID,
} from "./PromptExpanderSettingsPanel";
import "./PromptExpanderShared.css";
import "./PromptExpanderScreen.css";

export const PROMPT_EXPANDER_SETTINGS_PANEL_OPEN_KEY =
  "prompt_expander_settings_panel_open";

// Context 側の検証コードを表示文言に変換する。API 由来のメッセージはそのまま返す
const ERROR_CODE_KEYS: Record<string, TranslationKey> = {
  empty_prompt: "promptExpander.errors.emptyPrompt",
  too_many_characters: "promptExpander.errors.tooManyCharacters",
  session_not_selected: "promptExpander.errors.noSession",
};

export default function PromptExpanderScreen() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
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
    pendingReferenceWarn,
    confirmReferenceWarn,
    cancelReferenceWarn,
  } = usePromptExpander();

  const sessionId = useMemo(() => {
    const segments = location.pathname.split("/");
    const id = segments[2];
    return id ? decodeURIComponent(id) : null;
  }, [location.pathname]);

  const [showSettings, setShowSettings] = usePersistedState<boolean>(
    PROMPT_EXPANDER_SETTINGS_PANEL_OPEN_KEY,
    false,
  );
  const toggleSettings = useCallback(
    () => setShowSettings(!showSettings),
    [setShowSettings, showSettings],
  );

  const [showApiKeyConsent, setShowApiKeyConsent] = useState(
    () => !hasApiKeyConsent(),
  );
  const [apiKeyConsentDeclined, setApiKeyConsentDeclined] = useState(false);
  // 見出しでセッション名を変えている途中か（別のセッションへ移ったら閉じる）
  const [renamingSession, setRenamingSession] = useState(false);
  useEffect(() => {
    void sessionId;
    setRenamingSession(false);
  }, [sessionId]);

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
  const handleReferenceConfirm = useCallback(
    (suppress: boolean) => {
      void confirmReferenceWarn(suppress);
    },
    [confirmReferenceWarn],
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
      {/* 同意画面（と同意拒否の案内）を出している間は、背後の欄・ボタンへ Tab で入れないようにする */}
      <div
        className="prompt-expander"
        inert={showApiKeyConsent || apiKeyConsentDeclined}
      >
        {/* セッション作業中は入力欄と生成履歴を別々にスクロールさせる（幅が広いときだけ。CSS 側） */}
        <div
          className={`prompt-expander__scroll${sessionId ? " prompt-expander__scroll--workspace" : ""}`}
        >
          <header
            className={`prompt-expander__header${sessionId ? " prompt-expander__header--compact" : ""}`}
          >
            <div className="prompt-expander__header-main">
              {sessionId ? (
                // 作業中は入力欄を広く使えるよう、戻る導線・題名・セッション名を 1 行に詰める
                <div className="prompt-expander__breadcrumb">
                  <button
                    type="button"
                    className="prompt-expander__btn prompt-expander__btn--sm"
                    onClick={() => navigate(ROUTES.PROMPT_EXPANDER)}
                  >
                    {t("promptExpander.header.backToList")}
                  </button>
                  <h1 className="prompt-expander__title">
                    {t("promptExpander.header.title")}
                    <span className="feature-chip-experimental">
                      Experimental
                    </span>
                  </h1>
                  {activeSession &&
                    (renamingSession ? (
                      <PromptExpanderSessionRenameForm
                        session={activeSession}
                        onDone={() => setRenamingSession(false)}
                        className="prompt-expander__header-rename"
                      />
                    ) : (
                      <>
                        <span
                          className="prompt-expander__breadcrumb-title"
                          title={activeSession.title}
                        >
                          {activeSession.title ||
                            t("promptExpander.sessions.untitled")}
                        </span>
                        {/* 詳細画面でもセッション名を変えられるようにする（一覧の行と同じ入力欄） */}
                        <button
                          type="button"
                          className="prompt-expander__btn prompt-expander__btn--sm"
                          onClick={() => setRenamingSession(true)}
                        >
                          {t("promptExpander.sessions.rename")}
                        </button>
                      </>
                    ))}
                </div>
              ) : (
                <>
                  <h1 className="prompt-expander__title">
                    {t("promptExpander.header.title")}
                    <span className="feature-chip-experimental">
                      Experimental
                    </span>
                  </h1>
                  <p className="prompt-expander__subtitle">
                    {t("promptExpander.header.subtitle")}
                  </p>
                </>
              )}
            </div>
            <div className="prompt-expander__header-side">
              {/* 作業中の Anlas と V5 上限は下端の生成バーに常に出すので、ここでは一覧画面だけ */}
              {!sessionId && showUsageBar && anlas?.usage && (
                <NovelaiUsageBar
                  usage={anlas.usage}
                  compact
                  className="prompt-expander__usage-bar"
                />
              )}
              {!sessionId && anlas && (
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
            // 生成バーの「詳細を見る」からフォーカスを移せるよう tabIndex を持たせる
            <div
              className="prompt-expander__error-row"
              role="alert"
              tabIndex={-1}
            >
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
        {/* セクションを開いても生成操作が隠れないよう、下端に固定して置く */}
        {sessionId && activeSession && <PromptExpanderControlBar />}
      </div>

      <AnlasConfirmDialog
        open={pendingUsageWarn !== null}
        body={t("gameplay.v5UsageExhaustedBody")}
        onConfirm={handleUsageConfirm}
        onCancel={cancelUsageWarn}
      />
      {/* 精密参照の Anlas 確認。V5 上限警告を確定した後に続けて出す（同時には出さない） */}
      <AnlasConfirmDialog
        open={pendingUsageWarn === null && pendingReferenceWarn !== null}
        body={t("promptExpander.reference.anlasBody", {
          count: pendingReferenceWarn?.references?.length ?? 0,
          total:
            (pendingReferenceWarn?.references?.length ?? 0) *
            options.anlasPerReference,
          cost: options.anlasPerReference,
        })}
        onConfirm={handleReferenceConfirm}
        onCancel={cancelReferenceWarn}
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

      {/* 同意はこの画面のダイアログ(生成元によらず出す)で受け、済んでからプランを確かめる */}
      <NovelaiAccountCheckOnOpen
        ready={!showApiKeyConsent && !apiKeyConsentDeclined}
      />
    </MainLayout>
  );
}
