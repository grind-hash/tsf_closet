import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useTransparentImages } from "../../hooks/useTransparentImages";
import HakoniwaDigest from "./HakoniwaDigest";
import HakoniwaMessageFooter from "./HakoniwaMessageFooter";
import {
  anchorRatio,
  depthScale,
  initialPosition,
  type Point,
} from "./stage/roomLayout";
import type {
  RoomStageHandle,
  StageFurniture,
  StageResident,
} from "./stage/roomStage";
import { useHakoniwaPlayback } from "./useHakoniwaPlayback";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };
/** 一言の吹き出しを出しておく時間 */
const GREETING_MS = 7000;

interface Bubble {
  residentId: string;
  text: string;
}

/**
 * 箱庭の部屋。Phaser のステージ(遅延読み込み)の上に、吹き出しとキャプションを重ねる。
 * Phaser を起動できなければ、住民を並べただけの静止画の部屋で遊べるようにする。
 */
export default function HakoniwaStage() {
  const { t } = useTranslation();
  const {
    world,
    greeting,
    dismissGreeting,
    greet,
    greetingResidentId,
    selectedResidentId,
    selectResident,
    setPanelTab,
    playbackQueue,
    viewAreaId,
    setViewAreaId,
    digestVisible,
  } = useHakoniwa();
  const reducedMotion = usePrefersReducedMotion();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [stage, setStage] = useState<RoomStageHandle | null>(null);
  const [stageFailed, setStageFailed] = useState(false);
  const playback = useHakoniwaPlayback(stage);
  const playing = playback.event !== null;

  // 再生中は出来事の場所を出し、参加者はその場所にいなくても呼び寄せる
  const areaId = playback.event?.area ?? viewAreaId;
  const participantsKey = playback.event?.participants.join(",") ?? "";
  const allResidents = world?.residents;
  const residents = useMemo(() => {
    const participants = new Set(
      participantsKey ? participantsKey.split(",") : [],
    );
    return (allResidents ?? []).filter(
      (resident) =>
        resident.current_area === areaId || participants.has(resident.id),
    );
  }, [allResidents, areaId, participantsKey]);
  const area = world?.areas.find((item) => item.id === areaId) ?? null;
  const urls = useMemo(
    () => residents.map((r) => hakoniwaMediaUrl(r.display_avatar_url)),
    [residents],
  );
  const transparent = useTransparentImages(urls, ALPHA_OPTIONS);
  const stageResidents = useMemo<StageResident[]>(
    () =>
      residents.map((resident, index) => {
        const src = urls[index];
        return {
          id: resident.id,
          name: resident.name,
          imageUrl: src ? (transparent[src] ?? null) : null,
        };
      }),
    [residents, transparent, urls],
  );
  const backgroundUrl = hakoniwaMediaUrl(
    area?.background_url ?? world?.background_url,
  );
  const catalog = world?.furniture_catalog;
  const furniture = useMemo<StageFurniture[]>(() => {
    if (!area) return [];
    return area.slots.flatMap((slot, index) => {
      const item = catalog?.find((entry) => entry.id === slot.furniture_id);
      const url = item ? hakoniwaMediaUrl(item.url) : null;
      return url
        ? [{ key: `${area.id}:${index}`, url, x: slot.x, y: slot.y }]
        : [];
    });
  }, [area, catalog]);

  // 再生した出来事の場所を、見終わったあとも表示し続ける
  const playingArea = playback.event?.area ?? null;
  useEffect(() => {
    if (playingArea) setViewAreaId(playingArea);
  }, [playingArea, setViewAreaId]);

  // 住民を選んだり一言を頼んだりしたら、その住民のいる場所を出す
  const focusResidentId = greeting?.residentId ?? selectedResidentId;
  const focusArea =
    allResidents?.find((item) => item.id === focusResidentId)?.current_area ??
    null;
  useEffect(() => {
    if (focusArea && !playingArea) setViewAreaId(focusArea);
  }, [focusArea, playingArea, setViewAreaId]);

  // クリックの処理は最新の状態を見る(Phaser 側に渡すのは一度だけ)
  const clickRef = useRef<(id: string) => void>(() => {});
  clickRef.current = (residentId: string) => {
    if (playing || playbackQueue.length > 0) return;
    selectResident(residentId);
    setPanelTab("residents");
    if (greetingResidentId !== residentId) void greet(residentId);
  };

  // Phaser のステージは箱庭の画面を開いたときだけ読み込む
  useEffect(() => {
    const container = canvasRef.current;
    if (!container) return;
    let disposed = false;
    let handle: RoomStageHandle | null = null;
    import("./stage/roomStage")
      .then(({ createRoomStage }) =>
        createRoomStage(container, {
          onResidentClick: (id) => clickRef.current(id),
        }),
      )
      .then((created) => {
        if (disposed) {
          created.destroy();
          return;
        }
        handle = created;
        setStage(created);
      })
      .catch((error) => {
        console.warn("Hakoniwa stage failed to start", error);
        if (!disposed) setStageFailed(true);
      });
    return () => {
      disposed = true;
      handle?.destroy();
      setStage(null);
    };
  }, []);

  useEffect(() => {
    stage?.update(stageResidents, backgroundUrl, furniture);
  }, [stage, stageResidents, backgroundUrl, furniture]);

  useEffect(() => {
    stage?.setMotionEnabled(!reducedMotion);
  }, [stage, reducedMotion]);

  useEffect(() => {
    stage?.setSelected(selectedResidentId);
  }, [stage, selectedResidentId]);

  // 一言はしばらくしたら消す(再生中は出さない)
  useEffect(() => {
    if (!greeting) return;
    const timer = setTimeout(dismissGreeting, GREETING_MS);
    return () => clearTimeout(timer);
  }, [greeting, dismissGreeting]);

  const bubble: Bubble | null = playback.line
    ? { residentId: playback.line.speaker, text: playback.line.text }
    : !playing && greeting
      ? { residentId: greeting.residentId, text: greeting.text }
      : null;

  const fallbackAnchor = useCallback(
    (residentId: string): Point | null => {
      const index = residents.findIndex((item) => item.id === residentId);
      if (index < 0) return null;
      return anchorRatio(initialPosition(index, residents.length));
    },
    [residents],
  );

  // 吹き出しを住民の頭上に追従させる(歩いている間も)
  const bubbleRef = useRef<HTMLDivElement | null>(null);
  const bubbleResidentId = bubble?.residentId ?? null;
  useEffect(() => {
    if (!bubbleResidentId) return;
    let frame = 0;
    const place = () => {
      const anchor = stage
        ? stage.getAnchor(bubbleResidentId)
        : fallbackAnchor(bubbleResidentId);
      const element = bubbleRef.current;
      const room = element?.parentElement;
      if (element && room && anchor) {
        // 吹き出しは頭上(上向きに伸びる)。部屋の上端と左右からはみ出さないように寄せる
        const width = room.clientWidth;
        const height = room.clientHeight;
        const half = element.offsetWidth / 2 + 8;
        const x = Math.min(Math.max(anchor.x * width, half), width - half);
        const y = Math.max(anchor.y * height, element.offsetHeight + 8);
        element.style.left = `${x}px`;
        element.style.top = `${y}px`;
        element.style.visibility = "visible";
      }
      frame = requestAnimationFrame(place);
    };
    place();
    return () => cancelAnimationFrame(frame);
  }, [bubbleResidentId, fallbackAnchor, stage]);

  if (!world) return null;

  const nameOf = (id: string) =>
    residents.find((item) => item.id === id)?.name ?? "";
  const ojousama = world.active_rules.includes("ojousama");

  const handleStageClick = () => {
    if (playing) {
      playback.advance();
      return;
    }
    if (greeting) dismissGreeting();
  };

  const residentCount = (id: string) =>
    world.residents.filter((resident) => resident.current_area === id).length;

  return (
    <div className="hakoniwa-stage">
      <div
        className="hakoniwa-areas"
        role="tablist"
        aria-label={t("hakoniwa.areas.label")}
      >
        {world.areas.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === areaId}
            className={`hakoniwa-areas__chip${item.id === areaId ? " is-active" : ""}`}
            disabled={playing}
            onClick={() => setViewAreaId(item.id)}
          >
            {item.name}
            <span className="hakoniwa-areas__count">
              {t("hakoniwa.areas.count", { count: residentCount(item.id) })}
            </span>
          </button>
        ))}
      </div>
      <div className="hakoniwa-stage__fit">
        <div className="hakoniwa-stage__frame">
          <div
            className={`hakoniwa-stage__room${playing ? " hakoniwa-stage__room--playing" : ""}`}
            onClick={handleStageClick}
            data-testid="hakoniwa-stage"
          >
            {stageFailed ? (
              <FallbackRoom
                backgroundUrl={backgroundUrl}
                residents={stageResidents}
                selectedResidentId={selectedResidentId}
                onResidentClick={(id) => clickRef.current(id)}
              />
            ) : (
              <div className="hakoniwa-stage__canvas" ref={canvasRef} />
            )}
            {!stage && !stageFailed && (
              <div className="hakoniwa-stage__loading" role="status">
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.stage.loading")}
              </div>
            )}
            {bubble && (
              <div
                key={`${bubble.residentId}:${bubble.text}`}
                ref={bubbleRef}
                className={`hakoniwa-bubble${ojousama ? " hakoniwa-bubble--ojousama" : ""}`}
                style={{ visibility: "hidden" }}
                role="status"
              >
                <span className="hakoniwa-bubble__name">
                  {nameOf(bubble.residentId)}
                </span>
                <span className="hakoniwa-bubble__text">{bubble.text}</span>
              </div>
            )}
            {greetingResidentId && !playing && (
              <div className="hakoniwa-stage__hint" role="status">
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.stage.greeting", {
                  name: nameOf(greetingResidentId),
                })}
              </div>
            )}
          </div>
          {playback.event && (
            <div className="hakoniwa-caption" aria-live="polite">
              <div className="hakoniwa-caption__head">
                <span className="hakoniwa-caption__title">
                  {playback.event.title}
                </span>
                <span className="hakoniwa-caption__progress">
                  {t("hakoniwa.stage.progress", {
                    position: playback.position,
                    total: playback.total,
                  })}
                </span>
              </div>
              <p className="hakoniwa-caption__narration">
                {playback.event.narration}
              </p>
              <HakoniwaMessageFooter search={playback.event.web_search} />
              <div className="hakoniwa-caption__actions">
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--ghost"
                  onClick={playback.skipAll}
                >
                  {t("hakoniwa.stage.skip")}
                </button>
                <button
                  type="button"
                  className="hakoniwa-button hakoniwa-button--primary"
                  onClick={playback.advance}
                >
                  {t("hakoniwa.stage.next")}
                </button>
              </div>
            </div>
          )}
          {!playing && digestVisible && world.last_digest && (
            <HakoniwaDigest variant="overlay" />
          )}
        </div>
      </div>
    </div>
  );
}

interface FallbackRoomProps {
  backgroundUrl: string | null;
  residents: StageResident[];
  selectedResidentId: string | null;
  onResidentClick: (id: string) => void;
}

/** Phaser を起動できなかったときの静止画の部屋 */
function FallbackRoom({
  backgroundUrl,
  residents,
  selectedResidentId,
  onResidentClick,
}: FallbackRoomProps) {
  return (
    <div
      className="hakoniwa-stage__fallback"
      style={
        backgroundUrl ? { backgroundImage: `url(${backgroundUrl})` } : undefined
      }
    >
      {residents.map((resident, index) => {
        const position = initialPosition(index, residents.length);
        return (
          <button
            key={resident.id}
            type="button"
            className={`hakoniwa-stage__fallback-avatar${
              resident.id === selectedResidentId ? " is-selected" : ""
            }`}
            style={
              {
                left: `${(position.x / 1216) * 100}%`,
                top: `${(position.y / 832) * 100}%`,
                "--hk-depth-scale": depthScale(position.y),
              } as CSSProperties
            }
            onClick={(event) => {
              event.stopPropagation();
              onResidentClick(resident.id);
            }}
          >
            {resident.imageUrl ? (
              <img src={resident.imageUrl} alt="" />
            ) : (
              <span className="hakoniwa-stage__fallback-initial">
                {Array.from(resident.name)[0] ?? "?"}
              </span>
            )}
            <span className="hakoniwa-stage__fallback-name">
              {resident.name}
            </span>
          </button>
        );
      })}
    </div>
  );
}
