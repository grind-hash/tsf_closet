/**
 * AudioControlBar - チャット欄下部の音声再生コントロールバー
 *
 * ChatContext の共有オーディオ再生状態を表示し、再生/一時停止・停止・
 * シークを行う。合成中は進捗（ローディング表示）を出す。
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useChat } from "../../contexts/ChatContext";
import "./AudioControlBar.css";

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export default function AudioControlBar() {
  const { t } = useTranslation();
  const {
    state: chatState,
    audioPlayback,
    toggleAudioPause,
    stopAudio,
    seekAudio,
  } = useChat();

  const nowPlayingText = useMemo(() => {
    const message = chatState.messages.find(
      (item) => item.id === audioPlayback.messageId,
    );
    if (!message) {
      return "";
    }
    const trimmed = message.content.replace(/\s+/g, " ").trim();
    return trimmed.length > 40 ? `${trimmed.slice(0, 40)}...` : trimmed;
  }, [chatState.messages, audioPlayback.messageId]);

  if (audioPlayback.status === "idle") {
    return null;
  }

  const isLoading = audioPlayback.status === "loading";
  const isPlaying = audioPlayback.status === "playing";

  return (
    <div className="audio-control-bar" role="region" aria-live="polite">
      <button
        type="button"
        className="audio-control-bar__btn"
        onClick={toggleAudioPause}
        disabled={isLoading}
        aria-label={t(
          isPlaying ? "chat.audioBar.pause" : "chat.audioBar.resume",
        )}
        title={t(isPlaying ? "chat.audioBar.pause" : "chat.audioBar.resume")}
      >
        {isPlaying ? (
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="7" y1="4" x2="7" y2="20" />
            <line x1="17" y1="4" x2="17" y2="20" />
          </svg>
        ) : (
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
        )}
      </button>

      <button
        type="button"
        className="audio-control-bar__btn"
        onClick={stopAudio}
        aria-label={t("chat.audioBar.stop")}
        title={t("chat.audioBar.stop")}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="5" y="5" width="14" height="14" rx="1" />
        </svg>
      </button>

      <div className="audio-control-bar__body">
        <div className="audio-control-bar__label">
          {isLoading ? t("chat.audioBar.generating") : nowPlayingText}
        </div>

        {isLoading ? (
          <div className="audio-control-bar__progress audio-control-bar__progress--indeterminate">
            <div className="audio-control-bar__progress-fill" />
          </div>
        ) : (
          <div className="audio-control-bar__seek-row">
            <input
              type="range"
              className="audio-control-bar__seek"
              min={0}
              max={audioPlayback.duration || 0}
              step={0.1}
              value={Math.min(
                audioPlayback.currentTime,
                audioPlayback.duration || 0,
              )}
              onChange={(e) => seekAudio(Number(e.target.value))}
              aria-label={t("chat.audioBar.seek")}
            />
            <span className="audio-control-bar__time">
              {formatTime(audioPlayback.currentTime)} /{" "}
              {formatTime(audioPlayback.duration)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
