import {
  type KeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import type { UseAdventureBgmResult } from "../../hooks/useAdventureBgm";
import { useTransparentImages } from "../../hooks/useTransparentImages";
import { advLogScenes, advScript } from "./advLog";
import { canContinueEvent, EVENT_TEXT_MAX, maleBodyPairs } from "./eventCast";
import HakoniwaBgmControl from "./HakoniwaBgmControl";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import HakoniwaMessageFooter from "./HakoniwaMessageFooter";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };
// この幅以上では、ログを開いている間メッセージ窓を縮めてログを横に並べる
// (HakoniwaScreen.css の .hakoniwa-adv.is-log-open と同じ幅)
const LOG_BESIDE_WINDOW_QUERY = "(min-width: 900px)";
const SLOTS: Record<number, ("left" | "center" | "right")[]> = {
  1: ["center"],
  2: ["left", "right"],
  3: ["left", "center", "right"],
};

/**
 * 年代記の出来事を ADV 風に読む画面。背景(場所、または場面絵)・立ち絵・メッセージ窓。
 * クリック・Enter・Space で1幕ずつ送り、最後の幕で閉じる。スキップと Esc で閉じる。
 * 今日の出来事なら、メッセージ窓から続きを指示して次の場面を起こせる。
 * 読み終えた幕は、メッセージ窓の右上の「ログ」で読み返せる。
 */
interface HakoniwaAdvProps {
  /** 世界の画面で鳴らしている BGM(メッセージ窓の ♪ から操作する) */
  bgm: UseAdventureBgmResult;
}

export default function HakoniwaAdv({ bgm }: HakoniwaAdvProps) {
  const { t } = useTranslation();
  const {
    world,
    advEventId,
    closeAdv,
    generateSceneImage,
    continueEvent,
    busy,
    clearError,
  } = useHakoniwa();
  const [step, setStep] = useState(0);
  const [windowHidden, setWindowHidden] = useState(false);
  // 場所の背景が読み込めなかった URL(同梱の画像が無いときはエリアの背景に戻す)
  const [brokenBackground, setBrokenBackground] = useState<string | null>(null);
  // 続きの指示を書いている間は、窓の中身を入力欄に替え、幕送りを止める
  const [composing, setComposing] = useState(false);
  const [draft, setDraft] = useState("");
  // 続きの場面の絵も生成するか(入力欄を開くたびに、今の場面に絵があるかで決め直す)
  const [withSceneImage, setWithSceneImage] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const nextRef = useRef<HTMLButtonElement | null>(null);
  const showRef = useRef<HTMLButtonElement | null>(null);
  const draftRef = useRef<HTMLTextAreaElement | null>(null);
  const logRef = useRef<HTMLOListElement | null>(null);
  const event = world?.events.find((item) => item.id === advEventId) ?? null;
  // ログ: 読み終えた幕まで。続きを指示した場面は、元の場面までさかのぼって並べる
  const logScenes = useMemo(
    () =>
      world && advEventId ? advLogScenes(world.events, advEventId, step) : [],
    [world, advEventId, step],
  );

  // 開いた出来事が変わったら最初から(続きを生成できたときも、ここで入力欄を閉じる)
  useEffect(() => {
    if (!advEventId) {
      // 閉じたらログも畳む(続きの場面へ移るときは開いたままにする)
      setLogOpen(false);
      return;
    }
    setStep(0);
    setWindowHidden(false);
    setComposing(false);
    setDraft("");
  }, [advEventId]);

  // 窓の表示を切り替えると押したボタンが消えるため、Enter で送れるよう残る側のボタンへ移す
  useEffect(() => {
    if (!advEventId) return;
    if (windowHidden) showRef.current?.focus();
    else if (composing) draftRef.current?.focus();
    else nextRef.current?.focus();
  }, [advEventId, windowHidden, composing]);

  // ログを開いたとき・幕が進んだときは、いちばん新しい幕が見える位置へ送る
  useEffect(() => {
    if (!logOpen || logScenes.length === 0) return;
    const list = logRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [logOpen, logScenes]);

  const participants = useMemo(
    () =>
      (event?.participants ?? [])
        .slice(0, 3)
        .map((id) => world?.residents.find((item) => item.id === id))
        .filter((item) => item !== undefined),
    [event, world],
  );
  const urls = useMemo(
    () => participants.map((item) => hakoniwaMediaUrl(item.display_avatar_url)),
    [participants],
  );
  const transparent = useTransparentImages(urls, ALPHA_OPTIONS);

  if (!world || !event) return null;

  const script = advScript(event);
  const current = script[Math.min(step, script.length - 1)];
  const isLast = step >= script.length - 1;
  const area = world.areas.find((item) => item.id === event.area);
  const sceneUrl = hakoniwaMediaUrl(event.scene_image_url);
  // 背景は 場面の絵 → 出来事の場所の背景 → エリアの背景。ADV を開いた時点で場所に切り替わる
  const locationUrl = hakoniwaMediaUrl(
    world.locations.find((item) => item.id === event.location)?.background_url,
  );
  const areaUrl = hakoniwaMediaUrl(area?.background_url);
  const backgroundUrl =
    sceneUrl ??
    (locationUrl && locationUrl !== brokenBackground ? locationUrl : areaUrl);
  const nameOf = (speaker: string | null) =>
    speaker
      ? (world.residents.find((item) => item.id === speaker)?.name ?? "")
      : "";
  const speakerName = nameOf(current.speaker);
  const generating = busy === "scene";
  const continuing = busy === "event";
  const suggestion = !sceneUrl && !generating ? event.scene_suggestion : null;
  const slots = SLOTS[participants.length] ?? [];
  const canContinue = canContinueEvent(event, world.day, world.residents);
  const malePairsText = maleBodyPairs(participants)
    .map(([a, b]) => `${a.name}${t("hakoniwa.panel.pairJoin")}${b.name}`)
    .join(t("hakoniwa.panel.listJoin"));

  const openComposer = () => {
    clearError();
    // 絵のある場面の続きは絵つきで続ける(立ち絵に戻ると続きに見えないため)
    setWithSceneImage(Boolean(sceneUrl));
    setComposing(true);
  };

  const submitContinue = () => {
    const text = draft.trim();
    if (!text || busy !== null) return;
    // 成功すると新しい場面が開き、入力欄は閉じる。失敗したら書いた指示を残す
    continueEvent(event.id, text, withSceneImage);
  };

  const advance = () => {
    if (windowHidden) {
      setWindowHidden(false);
      return;
    }
    if (composing) return;
    if (logOpen && !window.matchMedia(LOG_BESIDE_WINDOW_QUERY).matches) {
      // 狭い画面ではログが窓に重なるため、ログの外を押したらログを閉じる(幕は送らない)
      setLogOpen(false);
      return;
    }
    if (isLast) {
      closeAdv();
      return;
    }
    setStep(step + 1);
    nextRef.current?.focus();
  };

  const handleKeyDown = (keyEvent: KeyboardEvent<HTMLDivElement>) => {
    // 日本語入力の変換中のキー(Esc で変換を取り消すなど)は画面の操作にしない
    if (keyEvent.nativeEvent.isComposing) return;
    if (keyEvent.key === "Escape" && logOpen) {
      keyEvent.preventDefault();
      setLogOpen(false);
      return;
    }
    if (composing && !windowHidden) {
      // 入力中: Esc は入力欄だけを閉じ、Ctrl/⌘+Enter で送る(Enter・Space は文字入力)
      if (keyEvent.key === "Escape") {
        keyEvent.preventDefault();
        if (!continuing) setComposing(false);
      } else if (
        keyEvent.key === "Enter" &&
        (keyEvent.ctrlKey || keyEvent.metaKey)
      ) {
        keyEvent.preventDefault();
        submitContinue();
      }
      return;
    }
    if (keyEvent.key === "Escape") {
      keyEvent.preventDefault();
      closeAdv();
      return;
    }
    const onButton = keyEvent.target instanceof HTMLButtonElement;
    if (!onButton && (keyEvent.key === "Enter" || keyEvent.key === " ")) {
      keyEvent.preventDefault();
      advance();
    }
  };

  const stop = (handler: () => void) => (clickEvent: MouseEvent) => {
    clickEvent.stopPropagation();
    handler();
  };

  return (
    <div
      className={`hakoniwa-adv${logOpen ? " is-log-open" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label={event.title}
      tabIndex={-1}
      onClick={advance}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-adv"
    >
      {backgroundUrl && (
        <img
          className="hakoniwa-adv__background"
          src={backgroundUrl}
          alt=""
          onError={() => {
            if (backgroundUrl === locationUrl) setBrokenBackground(locationUrl);
          }}
        />
      )}
      <HakoniwaErrorBanner placement="overlay" clearOnMount />
      {!sceneUrl && (
        <div className="hakoniwa-adv__cast">
          {participants.map((resident, index) => {
            const src = urls[index];
            const shown = src ? (transparent[src] ?? src) : null;
            const dim =
              current.speaker !== null && current.speaker !== resident.id;
            return shown ? (
              <img
                key={resident.id}
                className={`hakoniwa-adv__portrait hakoniwa-adv__portrait--${slots[index]}${
                  dim ? " is-dim" : ""
                }${participants.length === 3 ? " is-trio" : ""}`}
                src={shown}
                alt={resident.name}
              />
            ) : null;
          })}
        </div>
      )}
      {windowHidden ? (
        <button
          ref={showRef}
          type="button"
          className="hakoniwa-button hakoniwa-adv__show"
          onClick={stop(() => setWindowHidden(false))}
        >
          {t("common.messageWindow.show")}
        </button>
      ) : (
        <div className="hakoniwa-adv__window">
          <div className="hakoniwa-adv__meta">
            <span className="hakoniwa-adv__speaker">
              {composing
                ? t("hakoniwa.adv.continueHeading")
                : speakerName || t("hakoniwa.adv.narration")}
            </span>
            {!composing && (
              <span className="hakoniwa-adv__progress">
                {step + 1} / {script.length}
              </span>
            )}
            <div className="hakoniwa-adv__actions">
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                aria-expanded={logOpen}
                onClick={stop(() => setLogOpen((open) => !open))}
              >
                {t("hakoniwa.adv.log")}
              </button>
              {canContinue && !composing && (
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  onClick={stop(openComposer)}
                  disabled={busy !== null}
                >
                  {t("hakoniwa.adv.continue")}
                </button>
              )}
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={stop(() => generateSceneImage(event.id))}
                disabled={busy !== null}
              >
                {generating ? (
                  <>
                    <span className="hakoniwa-spinner" aria-hidden />
                    {t("hakoniwa.adv.generating")}
                  </>
                ) : sceneUrl ? (
                  t("hakoniwa.adv.regenerateScene")
                ) : (
                  t("hakoniwa.adv.generateScene")
                )}
              </button>
              <HakoniwaBgmControl bgm={bgm} placement="up" />
              <button
                type="button"
                className="hakoniwa-icon-button"
                aria-label={t("common.messageWindow.hide")}
                title={t("common.messageWindow.hide")}
                onClick={stop(() => {
                  setWindowHidden(true);
                  setLogOpen(false);
                })}
              >
                ×
              </button>
            </div>
          </div>
          {composing ? (
            <div className="hakoniwa-adv__compose">
              <textarea
                ref={draftRef}
                aria-label={t("hakoniwa.adv.continueHeading")}
                rows={3}
                maxLength={EVENT_TEXT_MAX}
                value={draft}
                placeholder={t("hakoniwa.adv.continuePlaceholder")}
                disabled={continuing}
                onChange={(changeEvent) => setDraft(changeEvent.target.value)}
              />
              <label className="hakoniwa-toggle hakoniwa-adv__scene-toggle">
                <span>
                  <strong>{t("hakoniwa.adv.continueWithScene")}</strong>
                  <small className="hakoniwa-toggle__hint">
                    {t("hakoniwa.adv.continueWithSceneHint")}
                  </small>
                </span>
                <input
                  type="checkbox"
                  className="hakoniwa-toggle__input"
                  checked={withSceneImage}
                  disabled={continuing}
                  onChange={(changeEvent) =>
                    setWithSceneImage(changeEvent.target.checked)
                  }
                />
                <span className="hakoniwa-toggle__switch" aria-hidden />
              </label>
              <p className="hakoniwa-note">{t("hakoniwa.adv.continueNote")}</p>
              {malePairsText && (
                <p className="hakoniwa-note">
                  {t("hakoniwa.panel.maleBodyNote", { pairs: malePairsText })}
                </p>
              )}
              <div className="hakoniwa-adv__controls">
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  onClick={stop(() => setComposing(false))}
                  disabled={continuing}
                >
                  {t("hakoniwa.adv.continueCancel")}
                </button>
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--primary"
                  onClick={stop(submitContinue)}
                  disabled={!draft.trim() || busy !== null}
                >
                  {continuing ? (
                    <>
                      <span className="hakoniwa-spinner" aria-hidden />
                      {withSceneImage
                        ? t("hakoniwa.adv.continuingWithScene")
                        : t("hakoniwa.adv.continuing")}
                    </>
                  ) : (
                    t("hakoniwa.adv.continueSubmit")
                  )}
                </button>
              </div>
            </div>
          ) : (
            <>
              {suggestion && (
                <div
                  className={`hakoniwa-adv__suggest${
                    suggestion.level === "strong" ? " is-strong" : ""
                  }`}
                >
                  {t("hakoniwa.adv.suggest", { reason: suggestion.reason })}
                </div>
              )}
              <p
                className={`hakoniwa-adv__text${current.speaker ? "" : " is-narration"}`}
              >
                {current.speaker
                  ? t("hakoniwa.chronicle.line", { text: current.text })
                  : current.text}
              </p>
              <HakoniwaMessageFooter search={event.web_search} />
              <div className="hakoniwa-adv__controls">
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  onClick={stop(closeAdv)}
                >
                  {t("hakoniwa.stage.skip")}
                </button>
                {isLast && canContinue && (
                  <button
                    type="button"
                    className="hakoniwa-button"
                    onClick={stop(openComposer)}
                    disabled={busy !== null}
                  >
                    {t("hakoniwa.adv.continue")}
                  </button>
                )}
                <button
                  ref={nextRef}
                  type="button"
                  className="hakoniwa-button hakoniwa-button--primary"
                  onClick={stop(advance)}
                >
                  {isLast ? t("hakoniwa.adv.close") : t("hakoniwa.stage.next")}
                </button>
              </div>
            </>
          )}
        </div>
      )}
      {logOpen && (
        <aside
          className="hakoniwa-chat__log"
          aria-label={t("hakoniwa.adv.logTitle")}
          // ログの中を押しても幕を送らない
          onClick={(clickEvent) => clickEvent.stopPropagation()}
        >
          <div className="hakoniwa-chat__log-head">
            <strong>{t("hakoniwa.adv.logTitle")}</strong>
            <button
              type="button"
              className="hakoniwa-icon-button"
              aria-label={t("hakoniwa.adv.logClose")}
              title={t("hakoniwa.adv.logClose")}
              onClick={() => setLogOpen(false)}
            >
              ×
            </button>
          </div>
          <ol ref={logRef} className="hakoniwa-chat__log-list">
            {logScenes.map((scene) => (
              <li key={scene.event.id} className="hakoniwa-adv__log-scene">
                <strong className="hakoniwa-adv__log-title">
                  {scene.event.title}
                </strong>
                {scene.event.instruction && (
                  <span className="hakoniwa-adv__log-order">
                    {t("hakoniwa.chronicle.instruction", {
                      text: scene.event.instruction,
                    })}
                  </span>
                )}
                <ol className="hakoniwa-adv__log-lines">
                  {scene.lines.map((line, index) => (
                    <li
                      // biome-ignore lint/suspicious/noArrayIndexKey: 幕は並び順そのものが識別子
                      key={index}
                      className={`hakoniwa-chat__entry${
                        line.speaker ? "" : " is-system"
                      }`}
                    >
                      <span className="hakoniwa-chat__entry-speaker">
                        {nameOf(line.speaker) || t("hakoniwa.adv.narration")}
                      </span>
                      <span>
                        {line.speaker
                          ? t("hakoniwa.chronicle.line", { text: line.text })
                          : line.text}
                      </span>
                    </li>
                  ))}
                </ol>
                <HakoniwaMessageFooter search={scene.event.web_search} />
              </li>
            ))}
          </ol>
        </aside>
      )}
    </div>
  );
}
