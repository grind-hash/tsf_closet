import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { type HakoniwaResident, hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { readStorage, writeStorage } from "../../utils/storage";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaEventComposer from "./HakoniwaEventComposer";
import HakoniwaPortrait from "./HakoniwaPortrait";
import HakoniwaRealityComposer from "./HakoniwaRealityComposer";
import HakoniwaTouchPreview from "./HakoniwaTouchPreview";
import {
  adaptationStageKey,
  affinityLevel,
  moodLevel,
  worldStageKey,
} from "./hakoniwaLabels";

const TRANSFORM_MAX = 500;

/**
 * 変身(姿を変える)か、出来事(いまの姿のまま場面を起こす)か、
 * 改変(その住民の常識を書き換える。本人も周りも昔からそうだと受け止める)か
 */
type DirectiveMode = "transform" | "event" | "reality";
const DIRECTIVE_MODES: DirectiveMode[] = ["transform", "event", "reality"];
const DIRECTIVE_MODE_LABEL_KEYS = {
  transform: "hakoniwa.panel.modeTransform",
  event: "hakoniwa.panel.modeEvent",
  reality: "hakoniwa.panel.modeReality",
} as const;

/**
 * 住民パネルのタブ。名前の下に置き、いちばん使う「変身・出来事」がいつも同じ位置に来るようにする
 * (性格・関係・記憶が増えても、入力欄を押し下げない)
 */
const PANEL_TABS = ["directive", "profile", "looks"] as const;
type ResidentPanelTab = (typeof PANEL_TABS)[number];
const PANEL_TAB_LABEL_KEYS = {
  directive: "hakoniwa.panel.tabDirective",
  profile: "hakoniwa.panel.tabProfile",
  looks: "hakoniwa.panel.tabLooks",
} as const;
// 選んだタブは、ブラウザのタブを開いている間だけ覚えておく
const PANEL_TAB_STORAGE_KEY = "hakoniwa_resident_panel_tab";

function savedPanelTab(): ResidentPanelTab {
  const saved = readStorage("session", PANEL_TAB_STORAGE_KEY);
  return PANEL_TABS.find((tab) => tab === saved) ?? "directive";
}

interface HakoniwaResidentPanelProps {
  resident: HakoniwaResident;
  onEdit: () => void;
}

/**
 * 選んだ住民の詳細。名前・立ち絵・話しかけるの下に、タブで
 * 変身・出来事 ／ プロフィール(性格・関係・名残・覚えていること) ／ 姿・編集 を切り替える
 */
export default function HakoniwaResidentPanel({
  resident,
  onEdit,
}: HakoniwaResidentPanelProps) {
  const { t } = useTranslation();
  const {
    world,
    busy,
    greet,
    greetingResidentId,
    transform,
    clearTransform,
    reapplyTransform,
    generateAvatar,
    removeResident,
    selectResident,
    playbackQueue,
    openChat,
  } = useHakoniwa();
  const [touchOpen, setTouchOpen] = useState(false);
  const transformId = useId();
  // 住民を切り替えても書きかけの指定を残す
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<DirectiveMode>("transform");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [panelTab, setPanelTab] = useState<ResidentPanelTab>(savedPanelTab);
  const tabsId = useId();
  const sectionRef = useRef<HTMLElement | null>(null);
  const tabRefs = useRef<Partial<Record<ResidentPanelTab, HTMLButtonElement>>>(
    {},
  );
  const panelTabRef = useRef(panelTab);
  panelTabRef.current = panelTab;
  const residentId = resident.id;

  useEffect(() => {
    writeStorage("session", PANEL_TAB_STORAGE_KEY, panelTab);
  }, [panelTab]);

  // 住民を選んだら(開いたときも)、選んでいるタブへフォーカスを移す。一覧の下の方で選んだときは、
  // タブの領域だけをパネルの先頭まで戻す(縦長の画面でページごとスクロールさせない)
  useEffect(() => {
    if (!residentId) return;
    tabRefs.current[panelTabRef.current]?.focus({ preventScroll: true });
    const section = sectionRef.current;
    const container = section?.closest(".hakoniwa-world__tabpanel");
    if (!section || !container) return;
    const offset =
      section.getBoundingClientRect().top -
      container.getBoundingClientRect().top;
    if (offset < 0) container.scrollTop += offset;
  }, [residentId]);

  if (!world) return null;
  const draft = drafts[resident.id] ?? "";
  const names = Object.fromEntries(
    world.residents.map((item) => [item.id, item.name]),
  );
  const locked = busy !== null || playbackQueue.length > 0;
  const swappedName = resident.swapped_with
    ? names[resident.swapped_with]
    : null;
  const relations = Object.entries(resident.affinities)
    .filter(([id]) => names[id])
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

  const handleTransform = () => {
    const instruction = draft.trim();
    if (!instruction) return;
    transform(resident.id, instruction);
  };

  return (
    <section
      ref={sectionRef}
      className="hakoniwa-resident"
      aria-label={resident.name}
    >
      <div className="hakoniwa-resident__head">
        <div className="hakoniwa-resident__look">
          {resident.display_avatar_url ? (
            <button
              type="button"
              className="hakoniwa-resident__portrait-button"
              onClick={() => setTouchOpen(true)}
              disabled={locked}
              title={t("hakoniwa.touch.open")}
            >
              <HakoniwaPortrait
                src={hakoniwaMediaUrl(resident.display_avatar_url)}
                alt={t("hakoniwa.panel.lookPreview", { name: resident.name })}
                className="hakoniwa-resident__portrait"
              />
            </button>
          ) : (
            <span className="hakoniwa-resident__portrait hakoniwa-resident__portrait--empty">
              {t("hakoniwa.residents.noAvatar")}
            </span>
          )}
        </div>
        <div className="hakoniwa-resident__summary">
          <div className="hakoniwa-resident__title">
            <h3>{resident.name}</h3>
            <button
              type="button"
              className="hakoniwa-icon-button"
              aria-label={t("hakoniwa.panel.close")}
              title={t("hakoniwa.panel.close")}
              onClick={() => selectResident(null)}
            >
              ×
            </button>
          </div>
          <p className="hakoniwa-resident__meta">
            {t(`hakoniwa.gender.${resident.gender}`)}・{resident.age}・
            {resident.job}
          </p>
          <p className="hakoniwa-resident__meta">
            {t("hakoniwa.residents.mood")}:{" "}
            {t(`hakoniwa.residents.moodLabels.${moodLevel(resident.mood)}`)}（
            {resident.mood}）
          </p>
          <ul className="hakoniwa-resident__states">
            {swappedName && (
              <li className="hakoniwa-badge hakoniwa-badge--accent">
                {t("hakoniwa.residents.swappedWith", { name: swappedName })}
              </li>
            )}
            {resident.transformation && (
              <li className="hakoniwa-badge hakoniwa-badge--accent">
                {t(
                  resident.transformation.kind === "reality"
                    ? "hakoniwa.residents.realityLook"
                    : "hakoniwa.residents.transformed",
                )}
              </li>
            )}
            {resident.display_kind === "dress" && (
              <li className="hakoniwa-badge">
                {t("hakoniwa.residents.dressed")}
              </li>
            )}
            {resident.display_kind === "rule" && (
              <li className="hakoniwa-badge">
                {t("hakoniwa.residents.ruleLook")}
              </li>
            )}
            {resident.display_kind === "combo" && (
              <li className="hakoniwa-badge">
                {t("hakoniwa.residents.comboLook")}
              </li>
            )}
            {resident.display_kind === "memo" && (
              <li className="hakoniwa-badge">
                {t("hakoniwa.residents.memoLook")}
              </li>
            )}
            {resident.adaptation && (
              <li
                className="hakoniwa-badge"
                title={t("hakoniwa.story.adaptationTitle", {
                  subject: t(
                    `hakoniwa.story.subject.${resident.adaptation.kind}`,
                  ),
                })}
              >
                {t("hakoniwa.story.adaptationBadge", {
                  stage: t(
                    `hakoniwa.story.adaptationStage.${adaptationStageKey(resident.adaptation.stage)}`,
                  ),
                })}
              </li>
            )}
            {resident.world_adaptation && (
              <li
                className="hakoniwa-badge"
                title={t("hakoniwa.story.worldTitle")}
              >
                {t("hakoniwa.story.worldBadge", {
                  stage: t(
                    `hakoniwa.story.worldStage.${worldStageKey(resident.world_adaptation.stage)}`,
                  ),
                })}
              </li>
            )}
          </ul>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--primary"
            onClick={() => void greet(resident.id)}
            disabled={greetingResidentId !== null || locked}
          >
            {greetingResidentId === resident.id ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.panel.talking")}
              </>
            ) : (
              t("hakoniwa.panel.talk")
            )}
          </button>
          <button
            type="button"
            className="hakoniwa-button"
            onClick={() => openChat(resident.id)}
            disabled={locked}
          >
            {t("hakoniwa.panel.chat")}
          </button>
        </div>
      </div>

      <div
        className="hakoniwa-resident__tabs"
        role="tablist"
        aria-label={t("hakoniwa.panel.tabsLabel", { name: resident.name })}
      >
        {PANEL_TABS.map((tab) => (
          <button
            key={tab}
            ref={(element) => {
              if (element) tabRefs.current[tab] = element;
            }}
            type="button"
            role="tab"
            id={`${tabsId}-${tab}`}
            aria-selected={panelTab === tab}
            aria-controls={`${tabsId}-${tab}-panel`}
            tabIndex={panelTab === tab ? 0 : -1}
            className={`hakoniwa-resident__tab${panelTab === tab ? " is-active" : ""}`}
            onClick={() => setPanelTab(tab)}
          >
            {t(PANEL_TAB_LABEL_KEYS[tab])}
          </button>
        ))}
      </div>

      {/* 切り替えても書きかけの指示を残すため、3つのタブの中身は置いたまま隠す */}
      <div
        className="hakoniwa-resident__tabpanel"
        role="tabpanel"
        id={`${tabsId}-directive-panel`}
        aria-labelledby={`${tabsId}-directive`}
        hidden={panelTab !== "directive"}
      >
        <div
          className="hakoniwa-segments"
          role="group"
          aria-label={t("hakoniwa.panel.modeLabel")}
        >
          {DIRECTIVE_MODES.map((option) => (
            <button
              key={option}
              type="button"
              className={mode === option ? "is-active" : undefined}
              aria-pressed={mode === option}
              onClick={() => setMode(option)}
            >
              {t(DIRECTIVE_MODE_LABEL_KEYS[option])}
            </button>
          ))}
        </div>
        {/* 切り替えても書きかけを残すため、両方を置いたまま隠す */}
        <div className="hakoniwa-resident__mode" hidden={mode !== "transform"}>
          <label htmlFor={transformId}>
            <strong>{t("hakoniwa.panel.transformHeading")}</strong>
          </label>
          <textarea
            id={transformId}
            rows={3}
            maxLength={TRANSFORM_MAX}
            value={draft}
            placeholder={t("hakoniwa.panel.transformPlaceholder")}
            onChange={(event) =>
              setDrafts((current) => ({
                ...current,
                [resident.id]: event.target.value,
              }))
            }
          />
          <p className="hakoniwa-note">{t("hakoniwa.panel.transformNote")}</p>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--primary"
            onClick={handleTransform}
            disabled={!draft.trim() || locked}
          >
            {busy === "transform" ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.panel.transforming")}
              </>
            ) : (
              t("hakoniwa.panel.transform")
            )}
          </button>
        </div>
        <div className="hakoniwa-resident__mode" hidden={mode !== "event"}>
          <HakoniwaEventComposer resident={resident} />
        </div>
        <div className="hakoniwa-resident__mode" hidden={mode !== "reality"}>
          <HakoniwaRealityComposer resident={resident} />
        </div>
        {resident.transformation && (
          <div className="hakoniwa-resident__current">
            <p>
              {t(
                resident.transformation.kind === "reality"
                  ? "hakoniwa.panel.currentReality"
                  : "hakoniwa.panel.currentTransform",
                { description: resident.transformation.description },
              )}
            </p>
            <button
              type="button"
              className="hakoniwa-button"
              onClick={() => void clearTransform(resident.id)}
              disabled={locked}
            >
              {t("hakoniwa.panel.clearTransform")}
            </button>
          </div>
        )}
        {resident.transformation_history.length > 0 && (
          <>
            <p className="hakoniwa-resident__subheading">
              {t("hakoniwa.panel.historyHeading")}
            </p>
            <ul className="hakoniwa-resident__history">
              {[...resident.transformation_history].reverse().map((entry) => (
                <li key={entry.image}>
                  <HakoniwaPortrait
                    src={hakoniwaMediaUrl(entry.image_url)}
                    alt=""
                    className="hakoniwa-resident__history-face"
                  />
                  <span className="hakoniwa-resident__history-text">
                    {entry.description}
                  </span>
                  <button
                    type="button"
                    className="hakoniwa-button hakoniwa-button--ghost"
                    onClick={() =>
                      void reapplyTransform(resident.id, entry.image)
                    }
                    disabled={
                      locked || resident.transformation?.image === entry.image
                    }
                  >
                    {t("hakoniwa.panel.reapply")}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div
        className="hakoniwa-resident__tabpanel"
        role="tabpanel"
        id={`${tabsId}-profile-panel`}
        aria-labelledby={`${tabsId}-profile`}
        hidden={panelTab !== "profile"}
      >
        <dl className="hakoniwa-resident__details">
          <dt>{t("hakoniwa.panel.personality")}</dt>
          <dd>{resident.personality}</dd>
          {relations.length > 0 && (
            <>
              <dt>{t("hakoniwa.panel.relations")}</dt>
              <dd>
                <ul className="hakoniwa-resident__relations">
                  {relations.map(([id, value]) => (
                    <li key={id}>
                      <span>
                        {names[id]}
                        {resident.addresses[id] && (
                          <span className="hakoniwa-resident__relation-address">
                            {t("hakoniwa.panel.callsThem", {
                              address: resident.addresses[id],
                            })}
                          </span>
                        )}
                      </span>
                      <span className="hakoniwa-resident__relation-level">
                        {t(
                          `hakoniwa.residents.affinityLabels.${affinityLevel(value)}`,
                        )}
                        （{value}）
                      </span>
                    </li>
                  ))}
                </ul>
              </dd>
            </>
          )}
          {resident.remnant && (
            <>
              <dt>{t("hakoniwa.story.remnantHeading")}</dt>
              <dd>
                {t("hakoniwa.story.remnant", {
                  text: resident.remnant.text,
                  days: resident.remnant.days_left,
                })}
              </dd>
            </>
          )}
          <dt>{t("hakoniwa.story.memoriesHeading")}</dt>
          <dd>
            {resident.memories.length === 0 ? (
              <span className="hakoniwa-note">
                {t("hakoniwa.story.memoriesEmpty")}
              </span>
            ) : (
              <ul className="hakoniwa-resident__memories">
                {resident.memories.map((memory, index) => (
                  <li
                    // biome-ignore lint/suspicious/noArrayIndexKey: 同じ日に同じ記憶が並ぶことがあり、並び順が識別子になる
                    key={`${memory.day}:${memory.kind}:${index}`}
                  >
                    <span className="hakoniwa-resident__memory-day">
                      {t("hakoniwa.chronicle.day", { day: memory.day })}
                    </span>
                    <span>{memory.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </dl>
      </div>

      <div
        className="hakoniwa-resident__tabpanel"
        role="tabpanel"
        id={`${tabsId}-looks-panel`}
        aria-labelledby={`${tabsId}-looks`}
        hidden={panelTab !== "looks"}
      >
        <strong>{t("hakoniwa.panel.avatarHeading")}</strong>
        <p className="hakoniwa-note">{t("hakoniwa.panel.avatarNote")}</p>
        <div className="hakoniwa-resident__buttons">
          <button
            type="button"
            className="hakoniwa-button"
            onClick={() => generateAvatar(resident.id, "base")}
            disabled={locked}
          >
            {busy === "avatar" ? (
              <>
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.panel.generating")}
              </>
            ) : (
              t("hakoniwa.panel.generateBase")
            )}
          </button>
          <button
            type="button"
            className="hakoniwa-button"
            onClick={() => generateAvatar(resident.id, "dress")}
            disabled={locked}
          >
            {t("hakoniwa.panel.generateDress")}
          </button>
        </div>
        <strong className="hakoniwa-resident__section-heading">
          {t("hakoniwa.panel.editHeading")}
        </strong>
        <div className="hakoniwa-resident__buttons">
          <button
            type="button"
            className="hakoniwa-button"
            onClick={onEdit}
            disabled={locked}
          >
            {t("hakoniwa.panel.edit")}
          </button>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost"
            onClick={() => setConfirmRemove(true)}
            disabled={locked || world.residents.length <= 2}
          >
            {t("hakoniwa.panel.remove")}
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmRemove}
        title={t("hakoniwa.panel.removeTitle")}
        confirmLabel={t("hakoniwa.panel.removeConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmRemove(false)}
        onConfirm={() => {
          setConfirmRemove(false);
          selectResident(null);
          void removeResident(resident.id);
        }}
      >
        <p>{t("hakoniwa.panel.removeBody", { name: resident.name })}</p>
      </ConfirmDialog>
      {touchOpen && (
        <HakoniwaTouchPreview
          resident={resident}
          onClose={() => setTouchOpen(false)}
        />
      )}
    </section>
  );
}
