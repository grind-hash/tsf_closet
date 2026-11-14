import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  type HakoniwaPanelTab,
  useHakoniwa,
} from "../../contexts/HakoniwaContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { ROUTES } from "../../routes";
import { readStorage, writeStorage } from "../../utils/storage";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaActivityIndicator from "./HakoniwaActivityIndicator";
import HakoniwaAdv from "./HakoniwaAdv";
import HakoniwaBgmControl from "./HakoniwaBgmControl";
import HakoniwaChat from "./HakoniwaChat";
import HakoniwaChronicle from "./HakoniwaChronicle";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import HakoniwaFurnitureTab from "./HakoniwaFurnitureTab";
import HakoniwaIntro from "./HakoniwaIntro";
import HakoniwaResidentsTab from "./HakoniwaResidentsTab";
import HakoniwaRulesTab from "./HakoniwaRulesTab";
import HakoniwaSettingsTab from "./HakoniwaSettingsTab";
import HakoniwaStage from "./HakoniwaStage";

const TABS: HakoniwaPanelTab[] = [
  "chronicle",
  "residents",
  "rules",
  "furniture",
  "settings",
];
const TAB_STORAGE_KEY = "hakoniwa_panel_tab";
/** 出来事を見せていない間の曲(catalog.json の hakoniwa の曲) */
const HAKONIWA_NORMAL_BGM = "hakoniwa_daily";

function isPanelTab(value: string | null): value is HakoniwaPanelTab {
  return value !== null && (TABS as string[]).includes(value);
}

/** 世界の画面: 左に部屋(ステージ)、右に年代記・住民・掟・設定のパネル */
export default function HakoniwaWorldView({ worldId }: { worldId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    world,
    busy,
    error,
    openWorld,
    closeWorld,
    advanceDay,
    panelTab,
    setPanelTab,
    playbackQueue,
    usageConfirmOpen,
    confirmUsage,
    cancelUsage,
    setIntervention,
    advEventId,
  } = useHakoniwa();
  // ふだんは箱庭の曲、出来事を見せている間(ADV・部屋での再生)は出来事を作るときに選んだ曲。
  // 曲が無い(選ばれなかった・定型文の出来事)ときはふだんの曲。曲を置くまでは既定の曲が鳴る
  const shown = world?.id === worldId ? world : null;
  const advEvent = advEventId
    ? (shown?.events.find((event) => event.id === advEventId) ?? null)
    : null;
  const sceneBgm = advEventId ? advEvent?.bgm : playbackQueue[0]?.bgm;
  const bgm = useAdventureBgm(
    shown ? (sceneBgm ?? HAKONIWA_NORMAL_BGM) : null,
    { prefsScope: "hakoniwa" },
  );
  const [seenEvents, setSeenEvents] = useState<number | null>(null);
  const tabRefs = useRef<Partial<Record<HakoniwaPanelTab, HTMLButtonElement>>>(
    {},
  );

  useEffect(() => {
    void openWorld(worldId);
    return () => closeWorld();
  }, [worldId, openWorld, closeWorld]);

  // 前に開いていたタブを復元し、そのタブにフォーカスを置く
  useEffect(() => {
    const saved = readStorage("local", TAB_STORAGE_KEY);
    const tab = isPanelTab(saved) ? saved : "chronicle";
    setPanelTab(tab);
    requestAnimationFrame(() => tabRefs.current[tab]?.focus());
  }, [setPanelTab]);

  useEffect(() => {
    writeStorage("local", TAB_STORAGE_KEY, panelTab);
  }, [panelTab]);

  const eventCount = world?.id === worldId ? world.events.length : null;
  // 開いた時点の出来事は既読にし、年代記を見ている間は増えた分も既読にする
  useEffect(() => {
    if (eventCount === null) return;
    setSeenEvents((current) =>
      current === null || panelTab === "chronicle" ? eventCount : current,
    );
  }, [eventCount, panelTab]);

  if (!world || world.id !== worldId) {
    return (
      <MainLayout>
        <div className="hakoniwa-page">
          {error ? (
            <div className="hakoniwa-error" role="alert">
              <span>{error}</span>
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={() => navigate(ROUTES.HAKONIWA)}
              >
                {t("hakoniwa.back")}
              </button>
            </div>
          ) : (
            <div className="hakoniwa-progress" role="status">
              <span className="hakoniwa-spinner" aria-hidden />
              {t("hakoniwa.loading")}
            </div>
          )}
        </div>
      </MainLayout>
    );
  }

  const unread =
    seenEvents === null ? 0 : Math.max(0, world.events.length - seenEvents);
  const activeRules = world.rule_cards.filter((card) => card.active);
  const playing = playbackQueue.length > 0;
  const dissonance = world.dissonance;
  const dissonanceTitle = dissonance.acknowledged
    ? t("hakoniwa.world.dissonanceAcknowledgedTitle", {
        value: dissonance.value,
      })
    : dissonance.next_stage && dissonance.remaining !== null
      ? t("hakoniwa.world.dissonanceTitle", {
          value: dissonance.value,
          stage: t(`hakoniwa.story.dissonanceStage.${dissonance.next_stage}`),
          remaining: dissonance.remaining,
        })
      : t("hakoniwa.world.dissonanceMaxTitle", { value: dissonance.value });

  return (
    <MainLayout>
      <div className="hakoniwa-world">
        <header className="hakoniwa-world__bar">
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost"
            onClick={() => navigate(ROUTES.HAKONIWA)}
          >
            ← {t("hakoniwa.back")}
          </button>
          <h1 className="hakoniwa-world__name">{world.name}</h1>
          <span className="hakoniwa-world__day">
            {t("hakoniwa.world.day", { day: world.day })}
          </span>
          <ul
            className="hakoniwa-world__rules"
            aria-label={t("hakoniwa.world.activeRules")}
          >
            {activeRules.length === 0 ? (
              <li className="hakoniwa-world__rule is-empty">
                {t("hakoniwa.world.noActiveRules")}
              </li>
            ) : (
              activeRules.map((card) => (
                <li key={card.id} className="hakoniwa-world__rule">
                  {card.name}
                </li>
              ))
            )}
          </ul>
          {dissonance.enabled && (
            <span
              className={`hakoniwa-world__dissonance is-${dissonance.stage}${
                dissonance.acknowledged ? " is-acknowledged" : ""
              }`}
              title={dissonanceTitle}
              data-testid="hakoniwa-dissonance"
            >
              {t("hakoniwa.world.dissonance", {
                stage: dissonance.acknowledged
                  ? t("hakoniwa.story.acknowledged")
                  : t(`hakoniwa.story.dissonanceStage.${dissonance.stage}`),
                value: dissonance.value,
              })}
            </span>
          )}
          <HakoniwaActivityIndicator />
          <HakoniwaBgmControl bgm={bgm} />
        </header>

        <HakoniwaErrorBanner />

        <div className="hakoniwa-world__body">
          <section className="hakoniwa-world__stage">
            <HakoniwaStage />
            <div className="hakoniwa-world__advance">
              <div className="hakoniwa-world__advance-options">
                <div
                  className="hakoniwa-intervention"
                  role="group"
                  aria-label={t("hakoniwa.intervention.label")}
                >
                  <span className="hakoniwa-intervention__label">
                    {t("hakoniwa.intervention.label")}
                  </span>
                  <div className="hakoniwa-segments">
                    {world.intervention.choices.map((choice) => (
                      <button
                        key={choice}
                        type="button"
                        className={
                          world.intervention.selected === choice
                            ? "is-active"
                            : undefined
                        }
                        aria-pressed={world.intervention.selected === choice}
                        disabled={busy !== null || playing}
                        onClick={() => void setIntervention(choice)}
                      >
                        {t(`hakoniwa.intervention.choice.${choice}`)}
                      </button>
                    ))}
                  </div>
                </div>
                <span className="hakoniwa-note">
                  {t("hakoniwa.world.advanceHint")}{" "}
                  {t(
                    `hakoniwa.intervention.note.${world.intervention.selected}`,
                  )}
                </span>
              </div>
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--primary hakoniwa-button--large hakoniwa-world__advance-button"
                onClick={() => void advanceDay()}
                disabled={busy !== null || playing}
              >
                {busy === "day" ? (
                  <>
                    <span className="hakoniwa-spinner" aria-hidden />
                    {t("hakoniwa.world.advancing")}
                  </>
                ) : (
                  t("hakoniwa.world.advanceDay")
                )}
              </button>
            </div>
          </section>

          <aside className="hakoniwa-world__panel">
            <HakoniwaIntro />
            <div
              className="hakoniwa-tabs"
              role="tablist"
              aria-label={t("hakoniwa.tabs.label")}
            >
              {TABS.map((tab) => (
                <button
                  key={tab}
                  ref={(element) => {
                    if (element) tabRefs.current[tab] = element;
                  }}
                  type="button"
                  role="tab"
                  id={`hakoniwa-tab-${tab}`}
                  aria-selected={panelTab === tab}
                  aria-controls={`hakoniwa-tabpanel-${tab}`}
                  className={`hakoniwa-tabs__chip${panelTab === tab ? " is-active" : ""}`}
                  onClick={() => setPanelTab(tab)}
                >
                  {t(`hakoniwa.tabs.${tab}`)}
                  {tab === "chronicle" && unread > 0 && (
                    <span
                      className="hakoniwa-tabs__badge"
                      title={t("hakoniwa.tabs.unread", { count: unread })}
                    >
                      +{unread}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <div
              className="hakoniwa-world__tabpanel"
              role="tabpanel"
              id={`hakoniwa-tabpanel-${panelTab}`}
              aria-labelledby={`hakoniwa-tab-${panelTab}`}
            >
              {panelTab === "chronicle" && <HakoniwaChronicle />}
              {panelTab === "residents" && <HakoniwaResidentsTab />}
              {panelTab === "rules" && <HakoniwaRulesTab />}
              {panelTab === "furniture" && <HakoniwaFurnitureTab />}
              {panelTab === "settings" && <HakoniwaSettingsTab />}
            </div>
          </aside>
        </div>
      </div>
      <HakoniwaAdv bgm={bgm} />
      <HakoniwaChat />
      <ConfirmDialog
        open={usageConfirmOpen}
        title={t("hakoniwa.usage.title")}
        confirmLabel={t("hakoniwa.usage.confirm")}
        cancelLabel={t("hakoniwa.usage.cancel")}
        doNotShowAgainLabel={t("hakoniwa.usage.suppress")}
        onCancel={cancelUsage}
        onConfirm={({ doNotShowAgain }) => confirmUsage(doNotShowAgain)}
      >
        <p>{t("hakoniwa.usage.body")}</p>
      </ConfirmDialog>
    </MainLayout>
  );
}
