/**
 * GuideScreen - 遊び方ガイド
 *
 * 基本の画面の説明と、既定ではOFFの遊び方(実験的機能)のカタログ。カードのトグルは
 * 設定画面と同じ SettingsContext の値に直結し、ONにするとサイドメニューへ項目が
 * 現れる。エンジン導入やモデル登録が必要な機能は設定画面へ誘導する。
 * プロバイダー都合で使えない機能もカードは隠さず、注記で説明する。
 * 文面はセレナの機能知識も兼ねる(guideFeatures.ts)。
 */
import { type ReactNode, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { markGuideSeen } from "../../utils/guideSeen";
import MainLayout from "../layout/MainLayout";
import { GUIDE_FEATURES, guideIcon } from "./guideFeatures";
import "./GuideScreen.css";

const BASIC_FEATURES = GUIDE_FEATURES.filter(
  (feature) => feature.section === "basics",
);

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
        <h3 className="guide-screen__card-title">{title}</h3>
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
    setAdventureEnabled,
    setExperimentalPromptExpanderEnabled,
    setCharacterChatEnabled,
    setExperimentalSalonEnabled,
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

        <h2 className="guide-screen__section-title">
          {t("guide.sections.basics")}
        </h2>
        <div className="guide-screen__cards">
          {BASIC_FEATURES.map((feature) => {
            const entry: { title: string; desc: string; note?: string } = t(
              `guide.${feature.key}`,
              { returnObjects: true },
            );
            return (
              <GuideCard
                key={feature.key}
                icon={feature.icon}
                title={entry.title}
                desc={entry.desc}
                note={entry.note}
              />
            );
          })}
        </div>

        <h2 className="guide-screen__section-title">
          {t("guide.sections.features")}
        </h2>
        <div className="guide-screen__cards">
          <GuideCard
            icon={guideIcon("adventure")}
            title={t("guide.adventure.title")}
            desc={t("guide.adventure.desc")}
            note={t("guide.adventure.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.adventureEnabled}
                onChange={setAdventureEnabled}
              />
              {state.adventureEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.adventureEnabled && (
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
            icon={guideIcon("talk")}
            title={t("guide.talk.title")}
            desc={t("guide.talk.desc")}
            note={t("guide.talk.note")}
          >
            {state.characterChatEnabled ? (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.CHARACTER_CHAT)}
              >
                {t("guide.talk.open")}
              </button>
            ) : (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => setCharacterChatEnabled(true)}
              >
                {t("guide.talk.enableParent")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon={guideIcon("inventory")}
            title={t("guide.inventory.title")}
            desc={t("guide.inventory.desc")}
            note={t("guide.inventory.note")}
          >
            {state.adventureEnabled ? (
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
                onClick={() => setAdventureEnabled(true)}
              >
                {t("guide.inventory.enableParent")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon={guideIcon("vrm")}
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
            icon={guideIcon("promptExpander")}
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
            icon={guideIcon("characterChat")}
            title={t("guide.characterChat.title")}
            desc={t("guide.characterChat.desc")}
            note={t("guide.characterChat.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.characterChatEnabled}
                onChange={setCharacterChatEnabled}
              />
              {state.characterChatEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.characterChatEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.CHARACTER_CHAT)}
              >
                {t("guide.characterChat.open")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon={guideIcon("salon")}
            title={t("guide.salon.title")}
            desc={t("guide.salon.desc")}
            note={t("guide.salon.note")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.experimentalSalonEnabled}
                onChange={setExperimentalSalonEnabled}
              />
              {state.experimentalSalonEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.experimentalSalonEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.SALON)}
              >
                {t("guide.salon.open")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            icon={guideIcon("voice")}
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
            icon={guideIcon("playMemory")}
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
        </div>
      </div>
    </MainLayout>
  );
}
