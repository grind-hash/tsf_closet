import {
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
  key: "welcome" | "presence" | "rules" | "residents" | "day";
  /** 小さな見出し(明朝・字間広め) */
  heading: string;
  /** 大きな見出し(ようこその幕だけ) */
  headline?: string;
  /** 本文。改行(\n)ごとに1行 */
  text: string;
  notes: string[];
  /** 背景にする場所(エリア id または場所 id) */
  place: string;
}

/**
 * 幕の並び。顔ぶれと「住民とあなた」は毎回、遊び方(掟・関わり方・1日の流れ)は guide のときだけ。
 * 文は固定(LLM は呼ばない)。背景は幕ごとに箱庭の場所を変える。
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
      heading: world.name,
      headline: t("hakoniwa.opening.welcomeHeading"),
      text: t("hakoniwa.opening.welcome", {
        names,
        count: world.residents.length,
      }),
      notes: [],
      place: "garden",
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
      place: "living",
    },
  ];
  if (guide) {
    scenes.push(
      {
        key: "rules",
        heading: t("hakoniwa.opening.rulesHeading"),
        text: t("hakoniwa.opening.rules"),
        notes: [],
        place: "study",
      },
      {
        key: "residents",
        heading: t("hakoniwa.opening.residentsHeading"),
        text: t("hakoniwa.opening.residents"),
        notes: [],
        place: "kitchen",
      },
      {
        key: "day",
        heading: t("hakoniwa.opening.dayHeading"),
        text: t("hakoniwa.opening.day"),
        notes: [
          ...(world.experiment_theme ? [t("hakoniwa.opening.dayTheme")] : []),
          t("hakoniwa.opening.dayAchievements"),
        ],
        place: "park",
      },
    );
  }
  return scenes;
}

/** 場所の背景(エリア → 場所の順に探し、無ければリビング) */
function placeBackground(world: HakoniwaWorld, place: string): string | null {
  const area = world.areas.find((item) => item.id === place);
  const location = world.locations?.find((item) => item.id === place);
  const living = world.areas.find((item) => item.id === "living");
  return hakoniwaMediaUrl(
    area?.background_url ?? location?.background_url ?? living?.background_url,
  );
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
 * 開幕(プロローグ)。世界を作った直後(設定画面で流さないこともできる)と、設定タブの
 * 「もう一度見る」で出す。サロンの開業演出と同じく画面全体を使い、幕ごとに箱庭の場所の
 * 背景をクロスフェードし、その上に枠のない文を中央に重ねる。クリック・Enter・Space で次へ、
 * スキップ・Esc で閉じる。最後の幕には「1日進める」を置かず、掟や住民へ案内する
 * (何も決めずに1日を進めないように)。
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
  const { closeOpening, setPanelTab, selectResident, avatarBatch } =
    useHakoniwa();
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
  // 背景は幕ごとの場所。同じ画像は1枚にまとめ、重ねたまま不透明度で切り替える
  const backgrounds = [
    ...new Set(
      scenes
        .map((scene) => placeBackground(world, scene.place))
        .filter((url): url is string => Boolean(url)),
    ),
  ];
  const currentBackground = placeBackground(world, current.place);

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
      className="hakoniwa-opening"
      role="dialog"
      aria-modal="true"
      aria-label={t("hakoniwa.opening.label")}
      // 画面をクリックしてもフォーカスがダイアログの外へ出ず、キー操作を受け続ける
      tabIndex={-1}
      onClick={advance}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-opening"
    >
      {backgrounds.map((url) => (
        <img
          key={url}
          className={`hakoniwa-opening__background${
            url === currentBackground ? " is-active" : ""
          }`}
          src={url}
          alt=""
        />
      ))}
      {/* 文の読みやすさのための、やわらかな陰り(真っ黒にはしない) */}
      <div className="hakoniwa-opening__veil" aria-hidden />

      {/* 住民はようこその幕だけ、庭に並んで立つ。透過前の画像(背景つき)は出さない */}
      <div
        className={`hakoniwa-opening__lineup${
          current.key === "welcome" ? " is-active" : ""
        }`}
        aria-hidden
      >
        {world.residents.map((resident, index) => {
          const src = urls[index];
          const shown = src ? transparent[src] : undefined;
          return shown ? <img key={resident.id} src={shown} alt="" /> : null;
        })}
      </div>

      <button
        type="button"
        className="hakoniwa-opening__skip"
        onClick={stop(close)}
      >
        {t("hakoniwa.opening.skip")}
      </button>

      {/* 文は幕ごとに重ね、今の幕だけを見せる(前の幕はフェードアウト、次の幕はフェードイン) */}
      {scenes.map((scene, index) => {
        const active = index === step;
        return (
          <section
            key={scene.key}
            className={`hakoniwa-opening__caption hakoniwa-opening__caption--${scene.key}${
              active ? " is-active" : ""
            }`}
            aria-hidden={!active}
            inert={!active}
            aria-live={active ? "polite" : undefined}
          >
            <p className="hakoniwa-opening__eyebrow">{scene.heading}</p>
            <span className="hakoniwa-opening__rule" aria-hidden />
            {scene.headline && (
              <p className="hakoniwa-opening__headline">{scene.headline}</p>
            )}
            <p className="hakoniwa-opening__text">{scene.text}</p>
            {scene.notes.map((note) => (
              <p key={note} className="hakoniwa-opening__note">
                {note}
              </p>
            ))}
            {index === scenes.length - 1 && (
              <div className="hakoniwa-opening__links">
                <button type="button" onClick={stop(() => goTo("rules"))}>
                  {t("hakoniwa.opening.openRules")}
                </button>
                <button type="button" onClick={stop(() => goTo("residents"))}>
                  {t("hakoniwa.opening.openResidents")}
                </button>
              </div>
            )}
          </section>
        );
      })}

      {/* 作った直後に、おまかせの住民の立ち絵を描いている進み具合 */}
      {avatarBatch && (
        <p className="hakoniwa-opening__status" role="status">
          <span className="hakoniwa-spinner" aria-hidden />
          {t("hakoniwa.opening.portraits", {
            done: avatarBatch.done,
            total: avatarBatch.total,
          })}
        </p>
      )}
      <p className="hakoniwa-opening__progress" aria-hidden>
        {step + 1} / {scenes.length}
      </p>
      <button
        ref={nextRef}
        type="button"
        className="hakoniwa-opening__next"
        onClick={stop(advance)}
      >
        {isLast ? t("hakoniwa.opening.start") : t("hakoniwa.opening.next")}
        {!isLast && <span aria-hidden>▼</span>}
      </button>
    </div>
  );
}
