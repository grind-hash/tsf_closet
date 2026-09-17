import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCharacterChat } from "../../../contexts/CharacterChatContext";
import { useNotification } from "../../../contexts/NotificationContext";
import { usePersistedState } from "../../../hooks/usePersistedState";
import {
  CubismPilotRenderer,
  type PilotCamera,
  type PilotEmotion,
  type PilotWeights,
} from "./cubismPilotRenderer";

/** 全身 / 寄りの選択。画面を開き直しても保つ(localStorage) */
export const LIVE2D_CAMERA_KEY = "character_chat_live2d_camera";

function isPilotCamera(value: string): value is PilotCamera {
  return value === "full" || value === "portrait";
}

export default function CharacterChatLive2D() {
  const { t } = useTranslation();
  const { showNotification } = useNotification();
  const { activeThread, sending, pendingInput, error, voice, setAvatarFailed } =
    useCharacterChat();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // 寄りの構図を収める範囲(メッセージ窓の上端まで)。キャンバスは窓の裏まで伸びる
  const frameRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [camera, setCamera] = usePersistedState<PilotCamera>(
    LIVE2D_CAMERA_KEY,
    "full",
    {
      serialize: (value) => value,
      deserialize: (raw) => (isPilotCamera(raw) ? raw : "full"),
    },
  );
  const thinking = sending && pendingInput !== null && !error;
  const messages = activeThread?.messages ?? [];
  const message =
    messages.find((item) => `chat:${item.id}` === voice.currentKey) ??
    [...messages].reverse().find((item) => item.role === "character");
  const expression = message?.meta.expression;
  const emotion: PilotEmotion = thinking
    ? "thinking"
    : expression === "happy" || expression === "angry" || expression === "sad"
      ? expression
      : "neutral";
  const inputRef = useRef({ emotion, voice, camera });
  inputRef.current = { emotion, voice, camera };
  const modelUrl = activeThread?.avatar?.url;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !modelUrl) return;
    const controller = new AbortController();
    let renderer: CubismPilotRenderer | null = null;
    let frame = 0;
    let disposed = false;
    let failed = false;
    const fail = (caught: unknown) => {
      if (disposed || failed) return;
      failed = true;
      controller.abort();
      cancelAnimationFrame(frame);
      renderer?.dispose();
      console.warn("character chat Live2D failed", caught);
      setAvatarFailed(true);
      showNotification("warning", t("characterChat.room.live2dFailed"));
    };
    const lost = (event: Event) => {
      event.preventDefault();
      fail(new Error("WebGL コンテキストが失われました"));
    };
    canvas.addEventListener("webglcontextlost", lost);
    setReady(false);
    const timeout = window.setTimeout(() => {
      fail(new Error("Live2D の読み込みがタイムアウトしました"));
      controller.abort();
    }, 30_000);
    const weights: PilotWeights = {
      neutral: 1,
      happy: 0,
      angry: 0,
      sad: 0,
      thinking: 0,
    };
    let previous = 0;
    const startedAt = performance.now();
    let nextBlink = performance.now() + 2000;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const tick = (now: number) => {
      if (disposed || failed || !renderer) return;
      const input = inputRef.current;
      const blend = 1 - Math.exp(-Math.min(now - previous, 50) / 130);
      previous = now;
      for (const key of Object.keys(weights) as PilotEmotion[])
        weights[key] +=
          ((key === input.emotion ? 1 : 0) - weights[key]) * blend;
      const blinkAge = now - nextBlink;
      const blink =
        blinkAge >= 0 && blinkAge < 180
          ? Math.sin((blinkAge / 180) * Math.PI)
          : 0;
      if (blinkAge >= 180) nextBlink = now + 2800 + Math.random() * 2200;
      const level =
        input.voice.status === "playing" &&
        input.voice.canSpeak &&
        input.voice.volume > 0
          ? input.voice.getLevel()
          : 0;
      const mouth = Number.isFinite(level)
        ? Math.min(1, Math.max(0, (level - 0.015) * 4))
        : 0;
      try {
        renderer.render({
          weights,
          blink,
          mouth,
          timeSeconds: (now - startedAt) / 1000,
          motionEnabled: !reducedMotion.matches,
          camera: input.camera,
          cameraMix: reducedMotion.matches ? 1 : blend,
          frameHeight:
            input.camera === "portrait"
              ? (frameRef.current?.clientHeight ?? null)
              : null,
        });
      } catch (caught) {
        fail(caught);
        return;
      }
      canvas.dataset.mouth = mouth.toFixed(3);
      frame = requestAnimationFrame(tick);
    };
    void CubismPilotRenderer.create(canvas, modelUrl, controller.signal)
      .then((created) => {
        clearTimeout(timeout);
        if (disposed || failed) {
          created.dispose();
          return;
        }
        renderer = created;
        setReady(true);
        frame = requestAnimationFrame(tick);
      })
      .catch((caught: unknown) => {
        clearTimeout(timeout);
        fail(caught);
      });
    return () => {
      disposed = true;
      clearTimeout(timeout);
      controller.abort();
      cancelAnimationFrame(frame);
      canvas.removeEventListener("webglcontextlost", lost);
      renderer?.dispose();
    };
  }, [modelUrl, setAvatarFailed, showNotification, t]);

  return (
    <div
      className="character-chat-room__live2d"
      data-emotion={emotion}
      data-ready={ready}
      data-camera={camera}
      aria-busy={!ready}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={t("characterChat.room.avatarLive2d")}
      />
      <div ref={frameRef} className="character-chat-room__live2d-frame" />
      <div
        className="character-chat-room__live2d-camera"
        role="group"
        aria-label={t("characterChat.room.live2dCamera")}
      >
        {(["full", "portrait"] as const).map((view) => (
          <button
            key={view}
            type="button"
            aria-pressed={camera === view}
            onClick={() => setCamera(view)}
          >
            {t(
              view === "full"
                ? "characterChat.room.live2dFull"
                : "characterChat.room.live2dPortrait",
            )}
          </button>
        ))}
      </div>
      {!ready && (
        <span role="status">{t("characterChat.room.live2dLoading")}</span>
      )}
    </div>
  );
}
