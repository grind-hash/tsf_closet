import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  type HakoniwaPanelTab,
  useHakoniwa,
} from "../../contexts/HakoniwaContext";
import { ROUTES } from "../../routes";
import { readStorage, writeStorage } from "../../utils/storage";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaAdv from "./HakoniwaAdv";
import HakoniwaChronicle from "./HakoniwaChronicle";
import HakoniwaFurnitureTab from "./HakoniwaFurnitureTab";
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
    clearError,
    openWorld,
    closeWorld,
    advanceDay,
    panelTab,
    setPanelTab,
    playbackQueue,
    usageConfirmOpen,
    confirmUsage,
    cancelUsage,
  } = useHakoniwa();
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
        </header>

        {error && (
          <div className="hakoniwa-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="hakoniwa-button hakoniwa-button--ghost"
              onClick={clearError}
            >
              {t("hakoniwa.dismissError")}
            </button>
          </div>
        )}

        <div className="hakoniwa-world__body">
          <section className="hakoniwa-world__stage">
            <HakoniwaStage />
            <div className="hakoniwa-world__advance">
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--primary hakoniwa-button--large"
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
              <span className="hakoniwa-note">
                {t("hakoniwa.world.advanceHint")}
              </span>
            </div>
          </section>

          <aside className="hakoniwa-world__panel">
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
      <HakoniwaAdv />
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
