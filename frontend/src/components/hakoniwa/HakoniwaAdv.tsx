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
import { useTransparentImages } from "../../hooks/useTransparentImages";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };
const SLOTS: Record<number, ("left" | "center" | "right")[]> = {
  1: ["center"],
  2: ["left", "right"],
  3: ["left", "center", "right"],
};

/**
 * 年代記の出来事を ADV 風に読む画面。背景(場所、または場面絵)・立ち絵・メッセージ窓。
 * クリック・Enter・Space で1幕ずつ送り、最後の幕で閉じる。スキップと Esc で閉じる。
 */
export default function HakoniwaAdv() {
  const { t } = useTranslation();
  const { world, advEventId, closeAdv, generateSceneImage, busy } =
    useHakoniwa();
  const [step, setStep] = useState(0);
  const [windowHidden, setWindowHidden] = useState(false);
  const nextRef = useRef<HTMLButtonElement | null>(null);
  const showRef = useRef<HTMLButtonElement | null>(null);
  const event = world?.events.find((item) => item.id === advEventId) ?? null;

  // 開いた出来事が変わったら最初から
  useEffect(() => {
    if (!advEventId) return;
    setStep(0);
    setWindowHidden(false);
  }, [advEventId]);

  // 窓の表示を切り替えると押したボタンが消えるため、Enter で送れるよう残る側のボタンへ移す
  useEffect(() => {
    if (!advEventId) return;
    (windowHidden ? showRef : nextRef).current?.focus();
  }, [advEventId, windowHidden]);

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

  const script = [
    { speaker: null as string | null, text: event.narration },
    ...event.lines.map((line) => ({ speaker: line.speaker, text: line.text })),
  ];
  const current = script[Math.min(step, script.length - 1)];
  const isLast = step >= script.length - 1;
  const area = world.areas.find((item) => item.id === event.area);
  const sceneUrl = hakoniwaMediaUrl(event.scene_image_url);
  const backgroundUrl = sceneUrl ?? hakoniwaMediaUrl(area?.background_url);
  const speakerName = current.speaker
    ? (world.residents.find((item) => item.id === current.speaker)?.name ?? "")
    : "";
  const generating = busy === "scene";
  const suggestion = !sceneUrl && !generating ? event.scene_suggestion : null;
  const slots = SLOTS[participants.length] ?? [];

  const advance = () => {
    if (windowHidden) {
      setWindowHidden(false);
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
      className="hakoniwa-adv"
      role="dialog"
      aria-modal="true"
      aria-label={event.title}
      tabIndex={-1}
      onClick={advance}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-adv"
    >
      {backgroundUrl && (
        <img className="hakoniwa-adv__background" src={backgroundUrl} alt="" />
      )}
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
              {speakerName || t("hakoniwa.adv.narration")}
            </span>
            <span className="hakoniwa-adv__progress">
              {step + 1} / {script.length}
            </span>
            <div className="hakoniwa-adv__actions">
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
              <button
                type="button"
                className="hakoniwa-icon-button"
                aria-label={t("common.messageWindow.hide")}
                title={t("common.messageWindow.hide")}
                onClick={stop(() => setWindowHidden(true))}
              >
                ×
              </button>
            </div>
          </div>
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
          <div className="hakoniwa-adv__controls">
            <button
              type="button"
              className="hakoniwa-button hakoniwa-button--ghost"
              onClick={stop(closeAdv)}
            >
              {t("hakoniwa.stage.skip")}
            </button>
            <button
              ref={nextRef}
              type="button"
              className="hakoniwa-button hakoniwa-button--primary"
              onClick={stop(advance)}
            >
              {isLast ? t("hakoniwa.adv.close") : t("hakoniwa.stage.next")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
