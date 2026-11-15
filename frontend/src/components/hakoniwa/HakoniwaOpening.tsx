import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { type HakoniwaWorld, hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useTransparentImages } from "../../hooks/useTransparentImages";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };

interface OpeningScene {
  key: string;
  heading: string;
  text: string;
  notes: string[];
}

/**
 * 幕の並び。顔ぶれと「住民とあなた」は毎回、遊び方(掟・関わり方・1日の流れ)は guide のときだけ。
 * 文は固定(LLM は呼ばない)。
 */
function useOpeningScenes(world: HakoniwaWorld, guide: boolean) {
  const { t } = useTranslation();
  const names = world.residents
    .map((resident) => resident.name)
    .join(t("hakoniwa.panel.listJoin"));
  const playerName = world.player_name?.trim() ?? "";
  const known =
    (world.player_presence ?? "known") === "known" ||
    world.dissonance.acknowledged;
  const scenes: OpeningScene[] = [
    {
      key: "welcome",
      heading: t("hakoniwa.opening.welcomeHeading"),
      text: t("hakoniwa.opening.welcome", {
        world: world.name,
        names,
        count: world.residents.length,
      }),
      notes: [],
    },
    {
      key: "presence",
      heading: t("hakoniwa.opening.presenceHeading"),
      text: known
        ? playerName
          ? t("hakoniwa.opening.presenceKnownNamed", { name: playerName })
          : t("hakoniwa.opening.presenceKnown")
        : t("hakoniwa.opening.presenceHidden"),
      notes: known
        ? []
        : [
            world.dissonance.enabled
              ? t("hakoniwa.opening.presenceHiddenDissonance")
              : t("hakoniwa.opening.presenceHiddenOff"),
          ],
    },
  ];
  if (guide) {
    scenes.push(
      {
        key: "rules",
        heading: t("hakoniwa.opening.rulesHeading"),
        text: t("hakoniwa.opening.rules"),
        notes: [],
      },
      {
        key: "residents",
        heading: t("hakoniwa.opening.residentsHeading"),
        text: t("hakoniwa.opening.residents"),
        notes: [],
      },
      {
        key: "day",
        heading: t("hakoniwa.opening.dayHeading"),
        text: t("hakoniwa.opening.day"),
        notes: [
          ...(world.experiment_theme ? [t("hakoniwa.opening.dayTheme")] : []),
          t("hakoniwa.opening.dayAchievements"),
        ],
      },
    );
  }
  return scenes;
}

/** 世界の画面へ移るときに渡す合図。opening は作った直後で、開幕を流す */
export interface HakoniwaWorldLocationState {
  opening?: boolean;
}

/**
 * 作った直後だけ開幕を流す。再読み込みや「戻る」で繰り返さないよう合図は消す。
 * 遊び方の説明の幕は、設定画面の「開幕で遊び方の説明も見せる」に従う。
 */
export function HakoniwaOpeningLauncher({
  worldReady,
}: {
  worldReady: boolean;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { state } = useSettings();
  const { openOpening } = useHakoniwa();
  const requested =
    (location.state as HakoniwaWorldLocationState | null)?.opening === true;
  const preferences = state.hakoniwaPreferences;
  useEffect(() => {
    if (!requested || !worldReady) return;
    navigate(location.pathname, { replace: true, state: null });
    if (!preferences.openingEnabled) return;
    const guide =
      preferences.openingGuide === "always" ||
      (preferences.openingGuide === "first" && !preferences.openingGuideSeen);
    openOpening(guide);
  }, [
    requested,
    worldReady,
    preferences,
    navigate,
    location.pathname,
    openOpening,
  ]);
  return null;
}

/**
 * 開幕。世界を作った直後(設定画面で流さないこともできる)と、設定タブの「もう一度見る」で出す。
 * ADV と同じ窓で1幕ずつ送る。クリック・Enter・Space で次へ、スキップ・Esc で閉じる。
 * 最後の幕には「1日進める」を置かず、掟や住民へ案内する(何も決めずに1日を進めないように)。
 */
export default function HakoniwaOpening() {
  const { world, opening } = useHakoniwa();
  if (!world || !opening) return null;
  return <OpeningView world={world} guide={opening.guide} />;
}

function OpeningView({
  world,
  guide,
}: {
  world: HakoniwaWorld;
  guide: boolean;
}) {
  const { t } = useTranslation();
  const { closeOpening, setPanelTab, selectResident } = useHakoniwa();
  const { state, setHakoniwaPreferences } = useSettings();
  const [step, setStep] = useState(0);
  const nextRef = useRef<HTMLButtonElement | null>(null);
  const scenes = useOpeningScenes(world, guide);
  const current = scenes[Math.min(step, scenes.length - 1)];
  const isLast = step >= scenes.length - 1;
  const urls = useMemo(
    () =>
      world.residents.map((resident) =>
        hakoniwaMediaUrl(resident.display_avatar_url),
      ),
    [world.residents],
  );
  const transparent = useTransparentImages(urls, ALPHA_OPTIONS);
  const living =
    world.areas.find((area) => area.id === "living") ?? world.areas[0];
  const backgroundUrl = hakoniwaMediaUrl(living?.background_url);

  // 幕が替わるたびに「次へ」へフォーカスを置き、Enter で送れるようにする
  useEffect(() => {
    if (step >= 0) nextRef.current?.focus();
  }, [step]);

  const close = () => {
    // 遊び方の説明を一度見たら(飛ばしても)、「最初の世界だけ」では次から出さない
    if (guide && !state.hakoniwaPreferences.openingGuideSeen) {
      setHakoniwaPreferences({ openingGuideSeen: true });
    }
    closeOpening();
  };
  const advance = () => {
    if (isLast) close();
    else setStep(step + 1);
  };
  const goTo = (tab: "rules" | "residents") => {
    setPanelTab(tab);
    if (tab === "residents") selectResident(world.residents[0]?.id ?? null);
    close();
  };

  const handleKeyDown = (keyEvent: KeyboardEvent<HTMLDivElement>) => {
    if (keyEvent.nativeEvent.isComposing) return;
    if (keyEvent.key === "Escape") {
      keyEvent.preventDefault();
      close();
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
      className="hakoniwa-adv hakoniwa-opening"
      role="dialog"
      aria-modal="true"
      aria-label={t("hakoniwa.opening.label")}
      tabIndex={-1}
      onClick={advance}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-opening"
    >
      {backgroundUrl && (
        <img className="hakoniwa-adv__background" src={backgroundUrl} alt="" />
      )}
      <div
        className="hakoniwa-opening__lineup"
        style={{ "--hk-lineup-count": world.residents.length } as CSSProperties}
      >
        {world.residents.map((resident, index) => {
          const src = urls[index];
          const shown = src ? (transparent[src] ?? src) : null;
          return shown ? (
            <img key={resident.id} src={shown} alt={resident.name} />
          ) : null;
        })}
      </div>
      <div className="hakoniwa-adv__window hakoniwa-opening__window">
        <div className="hakoniwa-adv__meta">
          <span className="hakoniwa-adv__speaker">{current.heading}</span>
          <span className="hakoniwa-adv__progress">
            {step + 1} / {scenes.length}
          </span>
        </div>
        <div className="hakoniwa-adv__body">
          <p className="hakoniwa-adv__text is-narration">{current.text}</p>
          {current.notes.map((note) => (
            <p key={note} className="hakoniwa-note">
              {note}
            </p>
          ))}
        </div>
        <div className="hakoniwa-adv__controls">
          {isLast ? (
            <>
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={stop(() => goTo("rules"))}
              >
                {t("hakoniwa.opening.openRules")}
              </button>
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={stop(() => goTo("residents"))}
              >
                {t("hakoniwa.opening.openResidents")}
              </button>
              <button
                ref={nextRef}
                type="button"
                className="hakoniwa-button hakoniwa-button--primary"
                onClick={stop(close)}
              >
                {t("hakoniwa.opening.start")}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={stop(close)}
              >
                {t("hakoniwa.opening.skip")}
              </button>
              <button
                ref={nextRef}
                type="button"
                className="hakoniwa-button hakoniwa-button--primary"
                onClick={stop(advance)}
              >
                {t("hakoniwa.opening.next")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
