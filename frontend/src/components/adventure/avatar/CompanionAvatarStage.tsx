/**
 * 対面会話モードのステージに置く 3D アバター(VRM)。
 *
 * 攻略対象の立ち絵 <img> の代わりに描画し、背景画像とスクリムの上に重なる。
 * 描画そのものは vrmAvatarEngine が担い、ここは props をエンジンへ橋渡しする。
 * three.js を含むため React.lazy で遅延読込する前提(default export)。
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  AvatarExpressionKey,
  AvatarGestureKey,
} from "../../../constants/companionAvatar";
import type { VisemeFrame } from "../../../utils/visemeTimeline";
import { createVrmAvatarEngine, type VrmAvatarEngine } from "./vrmAvatarEngine";
import "./CompanionAvatarStage.css";

export interface CompanionAvatarStageProps {
  fileUrl: string;
  expression: AvatarExpressionKey | null;
  gesture: AvatarGestureKey | null;
  /** 変化するたびに gesture を再生する(セリフ到着・再読み上げの識別子) */
  gestureKey: string | null;
  /** 口パク用の音量レベル(0..1)。毎フレーム呼ばれる */
  getVoiceLevel: () => number;
  /**
   * viseme 口パクの供給元(毎フレーム呼ばれる)。null を返す間は
   * getVoiceLevel の音量ベース口パクへフォールバックする
   */
  getVisemeFrame?: (() => VisemeFrame | null) | null;
  onReady?: () => void;
  onError: (error: unknown) => void;
}

type StageStatus = "loading" | "ready" | "error";

export default function CompanionAvatarStage({
  fileUrl,
  expression,
  gesture,
  gestureKey,
  getVoiceLevel,
  getVisemeFrame,
  onReady,
  onError,
}: CompanionAvatarStageProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<VrmAvatarEngine | null>(null);
  const [status, setStatus] = useState<StageStatus>("loading");
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const getVoiceLevelRef = useRef(getVoiceLevel);
  getVoiceLevelRef.current = getVoiceLevel;
  const getVisemeFrameRef = useRef(getVisemeFrame);
  getVisemeFrameRef.current = getVisemeFrame;
  const gestureRef = useRef(gesture);
  gestureRef.current = gesture;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    // canvas はエンジンごとに作る。React の開発モードでは effect が二重実行され、
    // 1 回目の dispose(forceContextLoss)が同じ canvas を使う 2 回目のエンジンへ
    // Context Lost として届いてしまうため、要素を共有しない
    const canvas = document.createElement("canvas");
    canvas.className = "adventure-avatar-stage__canvas";
    container.appendChild(canvas);
    let engine: VrmAvatarEngine;
    try {
      engine = createVrmAvatarEngine({
        canvas,
        container,
        onError: (error) => {
          setStatus("error");
          onErrorRef.current(error);
        },
      });
    } catch (error) {
      canvas.remove();
      setStatus("error");
      onErrorRef.current(error);
      return;
    }
    engine.setLevelSource(() => getVoiceLevelRef.current());
    engine.setVisemeSource(() => getVisemeFrameRef.current?.() ?? null);
    engineRef.current = engine;
    return () => {
      engineRef.current = null;
      engine.dispose();
      canvas.remove();
    };
  }, []);

  useEffect(() => {
    const engine = engineRef.current;
    if (!engine) return;
    let cancelled = false;
    setStatus("loading");
    engine
      .load(fileUrl)
      .then(() => {
        if (cancelled) return;
        setStatus("ready");
        onReadyRef.current?.();
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof Error && error.message === "load_cancelled")
          return;
        setStatus("error");
        onErrorRef.current(error);
      });
    return () => {
      cancelled = true;
    };
  }, [fileUrl]);

  useEffect(() => {
    if (status !== "ready") return;
    engineRef.current?.setExpression(expression);
  }, [expression, status]);

  // gestureKey が変わったときだけ再生する(gesture は ref 経由で読む)
  useEffect(() => {
    if (status !== "ready" || gestureKey === null) return;
    engineRef.current?.playGesture(gestureRef.current);
  }, [gestureKey, status]);

  return (
    <div ref={containerRef} className="adventure-avatar-stage" aria-hidden>
      {status === "loading" && (
        <div className="adventure-avatar-stage__loading" role="status">
          <span className="adventure-avatar-stage__spinner" />
          <span>{t("adventure.avatar.loading")}</span>
        </div>
      )}
    </div>
  );
}
