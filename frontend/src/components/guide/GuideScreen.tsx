/**
 * GuideScreen - 遊び方ガイド
 *
 * 基本の画面の説明と、既定ではOFFの遊び方(実験的機能)のカタログ。カードのトグルは
 * 設定画面と同じ SettingsContext の値に直結し、ONにするとサイドメニューへ項目が
 * 現れる。エンジン導入やモデル登録が必要な機能は設定画面へ誘導する。
 * プロバイダー都合で使えない機能もカードは隠さず、注記で説明する。
 * 文面はセレナの機能知識も兼ねる(guideFeatures.ts)。長い機能の細かい仕様は「くわしく見る」に
 * 畳み、開閉はカードごとにブラウザへ覚えさせる。
 */
import type { TFunction } from "i18next";
import { type ReactNode, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { AppGuideDetail } from "../../apis/characterChat";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { markGuideSeen } from "../../utils/guideSeen";
import { readStorageFlag, writeStorageFlag } from "../../utils/storage";
import MainLayout from "../layout/MainLayout";
import {
  GUIDE_FEATURES,
  type GuideEntryKey,
  type GuideEntryText,
  guideIcon,
} from "./guideFeatures";
import "./GuideScreen.css";

const BASIC_FEATURES = GUIDE_FEATURES.filter(
  (feature) => feature.section === "basics",
);

// 「くわしく見る」の開閉をカードごとに覚えておくキーの接頭辞
const DETAILS_OPEN_STORAGE_PREFIX = "guide_details_open:";

/** ガイドの項目の「くわしく見る」の中身(無ければ空) */
function guideDetails(t: TFunction, key: GuideEntryKey): AppGuideDetail[] {
  const entry = t(`guide.${key}`, { returnObjects: true }) as GuideEntryText;
  return (entry.details ?? []).map((section) => ({
    heading: section.heading,
    items: [...section.items],
  }));
}

interface GuideCardProps {
  id: GuideEntryKey;
  icon: string;
  title: string;
  desc: string;
  note?: string;
  details?: readonly AppGuideDetail[];
  children?: ReactNode;
}

function GuideCard({
  id,
  icon,
  title,
  desc,
  note,
  details = [],
  children,
}: GuideCardProps) {
  const { t } = useTranslation();
  const detailsId = useId();
  const storageKey = `${DETAILS_OPEN_STORAGE_PREFIX}${id}`;
  const [detailsOpen, setDetailsOpen] = useState(() =>
    readStorageFlag("local", storageKey),
  );

  const toggleDetails = () => {
    const next = !detailsOpen;
    setDetailsOpen(next);
    writeStorageFlag("local", storageKey, next);
  };

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
      {details.length > 0 && (
        <div className="guide-screen__details">
          <button
            type="button"
            className="guide-screen__details-toggle"
            aria-expanded={detailsOpen}
            aria-controls={detailsId}
            onClick={toggleDetails}
          >
            <span
              className={`guide-screen__details-chevron${detailsOpen ? "" : " is-collapsed"}`}
              aria-hidden="true"
            >
              ▾
            </span>
            {detailsOpen ? t("guide.detailsHide") : t("guide.detailsShow")}
          </button>
          <div id={detailsId} hidden={!detailsOpen}>
            {details.map((section) => (
              <section
                key={section.heading}
                className="guide-screen__details-section"
              >
                <h4 className="guide-screen__details-heading">
                  {section.heading}
                </h4>
                <ul className="guide-screen__details-list">
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      )}
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
    setExperimentalHakoniwaEnabled,
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
            const entry = t(`guide.${feature.key}`, {
              returnObjects: true,
            }) as GuideEntryText;
            return (
              <GuideCard
                key={feature.key}
                id={feature.key}
                icon={feature.icon}
                title={entry.title}
                desc={entry.desc}
                note={entry.note}
                details={guideDetails(t, feature.key)}
              />
            );
          })}
        </div>

        <h2 className="guide-screen__section-title">
          {t("guide.sections.features")}
        </h2>
        <div className="guide-screen__cards">
          <GuideCard
            id="adventure"
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
            id="talk"
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
            id="inventory"
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
            id="vrm"
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
            id="promptExpander"
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
            id="characterChat"
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
            id="salon"
            icon={guideIcon("salon")}
            title={t("guide.salon.title")}
            desc={t("guide.salon.desc")}
            note={t("guide.salon.note")}
            details={guideDetails(t, "salon")}
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
            id="hakoniwa"
            icon={guideIcon("hakoniwa")}
            title={t("guide.hakoniwa.title")}
            desc={t("guide.hakoniwa.desc")}
            note={t("guide.hakoniwa.note")}
            details={guideDetails(t, "hakoniwa")}
          >
            <div className="guide-screen__card-status">
              <GuideToggle
                label={t("guide.enable")}
                checked={state.experimentalHakoniwaEnabled}
                onChange={setExperimentalHakoniwaEnabled}
              />
              {state.experimentalHakoniwaEnabled && (
                <span className="guide-screen__added" role="status">
                  {t("guide.addedToMenu")}
                </span>
              )}
            </div>
            {state.experimentalHakoniwaEnabled && (
              <button
                type="button"
                className="guide-screen__cta"
                onClick={() => navigate(ROUTES.HAKONIWA)}
              >
                {t("guide.hakoniwa.open")}
              </button>
            )}
          </GuideCard>

          <GuideCard
            id="voice"
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
            id="playMemory"
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
