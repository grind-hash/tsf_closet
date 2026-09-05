/**
 * GuideScreen - 遊び方ガイド
 *
 * 既定ではOFFの遊び方(実験的機能)のカタログ。カードのトグルは設定画面と
 * 同じ SettingsContext の値に直結し、ONにするとサイドメニューへ項目が
 * 現れる。エンジン導入やモデル登録が必要な機能は設定画面へ誘導する。
 * プロバイダー都合で使えない機能もカードは隠さず、注記で説明する。
 */
import { type ReactNode, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { markGuideSeen } from "../../utils/guideSeen";
import MainLayout from "../layout/MainLayout";
import "./GuideScreen.css";

interface GuideCardProps {
  icon: string;
  title: string;
  desc: string;
  note?: string;
  children?: ReactNode;
}

function GuideCard({ icon, title, desc, note, children }: GuideCardProps) {
  return (
    <section className="guide-screen__card">
      <div className="guide-screen__card-head">
        <span className="guide-screen__card-icon" aria-hidden="true">
          {icon}
        </span>
        <h2 className="guide-screen__card-title">{title}</h2>
      </div>
      <p className="guide-screen__card-desc">{desc}</p>
      {note && <p className="guide-screen__card-note">ⓘ {note}</p>}
      {children && <div className="guide-screen__card-actions">{children}</div>}
    </section>
  );
}

interface GuideToggleProps {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}

function GuideToggle({ label, checked, onChange }: GuideToggleProps) {
  return (
    <label className="guide-screen__toggle">
      <span className="guide-screen__toggle-label">{label}</span>
      <input
        type="checkbox"
        className="guide-screen__toggle-input"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="guide-screen__toggle-switch" />
    </label>
  );
}

export default function GuideScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    state,
    setExperimentalAdventureEnabled,
    setExperimentalPromptExpanderEnabled,
    setExperimentalEndingEnabled,
    setPlayMemoryEnabled,
  } = useSettings();

  // サイドメニューの未読ドットは、この画面を一度開いたら消す
  useEffect(() => {
    markGuideSeen();
  }, []);

  return (
    <MainLayout>
      <div className="guide-screen">
        <header className="guide-screen__header">
          <h1 className="guide-screen__title">{t("guide.title")}</h1>
          <p className="guide-screen__intro">{t("guide.intro")}</p>
        </header>

        <div className="guide-screen__cards">
          <GuideCard
            icon="📖"
            title={t("guide.adventure.title")}
            desc={t("guide.adventure.desc")}
            note={t("guide.adventure.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.experimentalAdventureEnabled}
                onChange={setExperimentalAdventureEnabled}
              />
              {state.experimentalAdventureEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.experimentalAdventureEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.ADVENTURE)}
              >
                {t("guide.adventure.open")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon="🗨️"
            title={t("guide.talk.title")}
            desc={t("guide.talk.desc")}
            note={t("guide.talk.note")}
          >
            {state.experimentalAdventureEnabled ? (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.ADVENTURE)}
              >
                {t("guide.talk.open")}
              </button>
            ) : (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => setExperimentalAdventureEnabled(true)}
              >
                {t("guide.talk.enableParent")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon="🎒"
            title={t("guide.inventory.title")}
            desc={t("guide.inventory.desc")}
            note={t("guide.inventory.note")}
          >
            {state.experimentalAdventureEnabled ? (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.ADVENTURE)}
              >
                {t("guide.inventory.open")}
              </button>
            ) : (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => setExperimentalAdventureEnabled(true)}
              >
                {t("guide.inventory.enableParent")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon="🧍"
            title={t("guide.vrm.title")}
            desc={t("guide.vrm.desc")}
            note={t("guide.vrm.note")}
          >
            <button
              type="button"
              className="guide-screen__cta"
              onClick={() => navigate(ROUTES.SETTINGS)}
            >
              {t("guide.openSettings")}
            </button>
          </GuideCard>

          <GuideCard
            icon="✨"
            title={t("guide.promptExpander.title")}
            desc={t("guide.promptExpander.desc")}
            note={t("guide.promptExpander.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.experimentalPromptExpanderEnabled}
                onChange={setExperimentalPromptExpanderEnabled}
              />
              {state.experimentalPromptExpanderEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.experimentalPromptExpanderEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.PROMPT_EXPANDER)}
              >
                {t("guide.promptExpander.open")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon="🔊"
            title={t("guide.voice.title")}
            desc={t("guide.voice.desc")}
            note={t("guide.voice.note")}
          >
            <button
              type="button"
              className="guide-screen__cta"
              onClick={() => navigate(ROUTES.SETTINGS)}
            >
              {t("guide.openSettings")}
            </button>
          </GuideCard>

          <GuideCard
            icon="📝"
            title={t("guide.playMemory.title")}
            desc={t("guide.playMemory.desc")}
            note={t("guide.playMemory.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.playMemoryEnabled}
                onChange={setPlayMemoryEnabled}
              />
            </div>
            {state.playMemoryEnabled && (
              <span className="guide-screen__added" role="status">
                {t("guide.playMemory.enabledHint")}
              </span>
            )}
          </GuideCard>

          <GuideCard
            icon="🎬"
            title={t("guide.endings.title")}
            desc={t("guide.endings.desc")}
            note={t("guide.endings.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.experimentalEndingEnabled}
                onChange={setExperimentalEndingEnabled}
              />
              {state.experimentalEndingEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.experimentalEndingEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.ENDINGS)}
              >
                {t("guide.endings.open")}
              </button>
            )}
          </GuideCard>
        </div>
      </div>
    </MainLayout>
  );
}
