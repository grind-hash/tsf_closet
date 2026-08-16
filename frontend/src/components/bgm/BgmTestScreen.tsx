/**
 * BgmTestScreen - BGMテスト画面
 *
 * TSFシナリオが使うBGMカタログの全曲を一覧し、その場で試聴する。
 * 本編のループ再生（useAdventureBgm）とは独立した単発再生で、fade も loop も行わない。
 * 音量だけは localStorage を通じて本編と共有する。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AdventureBgmTrack } from "../../apis/adventure";
import { fetchAdventureBgmCatalog } from "../../apis/adventure";
import {
  clamp01,
  loadBgmPreferences,
  saveBgmVolume,
} from "../../utils/bgmPreferences";
import { formatTime } from "../../utils/formatTime";
import MainLayout from "../layout/MainLayout";
import "./BgmTestScreen.css";

// アイコンは AudioControlBar と同じ SVG を使う。記号文字だと環境により
// グリフが欠けるため。
const ICON_PROPS = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function PlayIcon() {
  return (
    <svg width="16" height="16" aria-hidden="true" {...ICON_PROPS}>
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="16" height="16" aria-hidden="true" {...ICON_PROPS}>
      <line x1="7" y1="4" x2="7" y2="20" />
      <line x1="17" y1="4" x2="17" y2="20" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="16" height="16" aria-hidden="true" {...ICON_PROPS}>
      <rect x="5" y="5" width="14" height="14" rx="1" />
    </svg>
  );
}

function VolumeIcon() {
  return (
    <svg width="14" height="14" aria-hidden="true" {...ICON_PROPS}>
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
    </svg>
  );
}

export default function BgmTestScreen() {
  const { t } = useTranslation();
  const [tracks, setTracks] = useState<AdventureBgmTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackError, setPlaybackError] = useState(false);
  const [volume, setVolumeState] = useState(() => loadBgmPreferences().volume);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const volumeRef = useRef(volume);

  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (audioRef.current) {
      return audioRef.current;
    }
    const audio = new Audio();
    // 試聴用途なのでループはせず、末尾で停止表示へ戻す
    audio.loop = false;
    audio.preload = "metadata";
    audio.volume = clamp01(volumeRef.current);
    audioRef.current = audio;
    return audio;
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchAdventureBgmCatalog()
      .then((catalog) => {
        if (cancelled) return;
        setTracks(catalog.tracks);
        setLoading(false);
      })
      .catch((error) => {
        if (cancelled) return;
        console.warn("BGMカタログの取得に失敗しました", error);
        setLoadError(true);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 再生状態と時間表示の同期。Audio 要素は ensureAudio で1つだけ作る
  useEffect(() => {
    const audio = ensureAudio();
    const handleLoadedMetadata = () => setDuration(audio.duration);
    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
    const handlePlay = () => {
      setIsPlaying(true);
      setPlaybackError(false);
    };
    const handlePause = () => setIsPlaying(false);
    const handleEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };
    const handleError = () => {
      setIsPlaying(false);
      setPlaybackError(true);
    };
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("play", handlePlay);
    audio.addEventListener("pause", handlePause);
    audio.addEventListener("ended", handleEnded);
    audio.addEventListener("error", handleError);
    return () => {
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("play", handlePlay);
      audio.removeEventListener("pause", handlePause);
      audio.removeEventListener("ended", handleEnded);
      audio.removeEventListener("error", handleError);
    };
  }, [ensureAudio]);

  // 画面離脱時は完全に停止する
  useEffect(() => {
    return () => {
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      audioRef.current = null;
    };
  }, []);

  const selectedTrack = useMemo(
    () => tracks.find((track) => track.key === selectedKey) ?? null,
    [tracks, selectedKey],
  );

  const handleSelectTrack = useCallback(
    (track: AdventureBgmTrack) => {
      const audio = ensureAudio();
      if (track.key === selectedKey) {
        // 同じ曲の再クリックは再生/一時停止のトグル
        if (audio.paused) {
          void audio.play().catch(() => setPlaybackError(true));
        } else {
          audio.pause();
        }
        return;
      }
      setSelectedKey(track.key);
      setPlaybackError(false);
      setCurrentTime(0);
      setDuration(0);
      audio.pause();
      audio.src = track.url;
      audio.currentTime = 0;
      void audio.play().catch(() => setPlaybackError(true));
    },
    [ensureAudio, selectedKey],
  );

  const handleTogglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !selectedTrack) return;
    if (audio.paused) {
      void audio.play().catch(() => setPlaybackError(true));
    } else {
      audio.pause();
    }
  }, [selectedTrack]);

  const handleStop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    setCurrentTime(0);
  }, []);

  const handleSeek = useCallback((next: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = next;
    setCurrentTime(next);
  }, []);

  const handleVolumeChange = useCallback((next: number) => {
    const clamped = clamp01(next);
    volumeRef.current = clamped;
    setVolumeState(clamped);
    const audio = audioRef.current;
    if (audio) {
      audio.volume = clamped;
    }
    // ミュート状態には触れず、音量だけ本編と共有する
    saveBgmVolume(clamped);
  }, []);

  return (
    <MainLayout>
      <div className="bgm-test-screen">
        <header className="bgm-test-screen__header">
          <h1 className="bgm-test-screen__title">{t("bgmTest.title")}</h1>
          <p className="bgm-test-screen__subtitle">{t("bgmTest.subtitle")}</p>
        </header>

        <section
          className="bgm-test-screen__player"
          aria-label={t("bgmTest.playerLabel")}
        >
          <div className="bgm-test-screen__player-main">
            <button
              type="button"
              className="bgm-test-screen__btn"
              onClick={handleTogglePlay}
              disabled={!selectedTrack}
              aria-label={t(isPlaying ? "bgmTest.pause" : "bgmTest.play")}
              title={t(isPlaying ? "bgmTest.pause" : "bgmTest.play")}
            >
              {isPlaying ? <PauseIcon /> : <PlayIcon />}
            </button>
            <button
              type="button"
              className="bgm-test-screen__btn"
              onClick={handleStop}
              disabled={!selectedTrack}
              aria-label={t("bgmTest.stop")}
              title={t("bgmTest.stop")}
            >
              <StopIcon />
            </button>
            <span className="bgm-test-screen__now-playing">
              {selectedTrack ? selectedTrack.file : t("bgmTest.noTrack")}
            </span>
          </div>

          <div className="bgm-test-screen__seek-row">
            <input
              type="range"
              className="bgm-test-screen__seek"
              min={0}
              max={duration || 0}
              step={0.1}
              value={Math.min(currentTime, duration || 0)}
              onChange={(event) => handleSeek(Number(event.target.value))}
              disabled={!selectedTrack || duration === 0}
              aria-label={t("bgmTest.seek")}
            />
            <span className="bgm-test-screen__time">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>

          <div className="bgm-test-screen__volume-row">
            <span className="bgm-test-screen__volume-icon" aria-hidden="true">
              <VolumeIcon />
            </span>
            <input
              type="range"
              className="bgm-test-screen__volume"
              min={0}
              max={1}
              step={0.01}
              value={volume}
              onChange={(event) =>
                handleVolumeChange(Number(event.target.value))
              }
              aria-label={t("bgmTest.volume")}
            />
            <span className="bgm-test-screen__volume-value">
              {Math.round(volume * 100)}%
            </span>
          </div>

          {playbackError && (
            <p className="bgm-test-screen__error" role="status">
              {t("bgmTest.playbackError")}
            </p>
          )}
        </section>

        <section className="bgm-test-screen__tracks">
          <h2 className="bgm-test-screen__tracks-title">
            {t("bgmTest.trackListTitle")}
          </h2>

          {loading && (
            <p className="bgm-test-screen__status">{t("bgmTest.loading")}</p>
          )}
          {!loading && loadError && (
            <p className="bgm-test-screen__error">{t("bgmTest.loadError")}</p>
          )}
          {!loading && !loadError && tracks.length === 0 && (
            <p className="bgm-test-screen__status">{t("bgmTest.empty")}</p>
          )}

          <ul className="bgm-test-screen__list">
            {tracks.map((track) => (
              <li key={track.key}>
                <button
                  type="button"
                  className={`bgm-test-screen__track${
                    track.key === selectedKey ? " is-active" : ""
                  }`}
                  onClick={() => handleSelectTrack(track)}
                  aria-pressed={track.key === selectedKey}
                >
                  <span className="bgm-test-screen__track-body">
                    <strong className="bgm-test-screen__track-file">
                      {track.file}
                    </strong>
                    <small className="bgm-test-screen__track-desc">
                      {track.description}
                    </small>
                    {/*
                      出所表記は曲ごとの属性なので、全曲が同値でも各行に出す。
                      文面はカタログが持つ表示文そのものなので加工しない
                      （生成AI・配布素材・自作で言い回しが変わるため）。
                    */}
                    {track.credit && (
                      <small className="bgm-test-screen__track-credit">
                        {track.credit}
                      </small>
                    )}
                  </span>
                  {/* 幅が可変なので行末に置く。行頭だと曲名の開始位置がずれる */}
                  <span className="bgm-test-screen__track-key">
                    {track.key}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </MainLayout>
  );
}
