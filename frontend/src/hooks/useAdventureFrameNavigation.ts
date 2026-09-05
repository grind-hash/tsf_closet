import { useCallback, useEffect, useMemo, useState } from "react";
import type { AdventureRun } from "../apis/adventure";
import {
  type AdventureStageFrame,
  buildStageFrames,
} from "../utils/adventureFrames";

export type AdventureLightboxView =
  | "scene"
  | "background"
  | "portrait"
  | "partner"
  | "overview";

/**
 * ステージのフレーム（手番ごとの画像）と、その閲覧位置・ライトボックスの状態。
 *
 * ステージ側の閲覧位置（selectedFrameIndex。null は最新）とモーダル内の位置
 * （lightboxIndex）は独立させ、モーダル内の前後送りでステージを動かさない。
 */
export function useAdventureFrameNavigation(activeRun: AdventureRun | null) {
  const frames = useMemo(() => buildStageFrames(activeRun), [activeRun]);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number | null>(
    null,
  );
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [lightboxView, setLightboxView] =
    useState<AdventureLightboxView>("scene");

  // 新しいターン到着・画像再生成時は自動的に最新表示へ復帰する
  // biome-ignore lint/correctness/useExhaustiveDependencies: turn_count/current_image_url の変化を検知するための依存
  useEffect(() => {
    setSelectedFrameIndex(null);
  }, [activeRun?.turn_count, activeRun?.current_image_url]);

  const isViewingPast = selectedFrameIndex !== null;
  const effectiveIndex =
    selectedFrameIndex ?? (frames.length > 0 ? frames.length - 1 : -1);
  const selectedFrame: AdventureStageFrame | undefined =
    effectiveIndex >= 0 ? frames[effectiveIndex] : undefined;
  const latestFrame: AdventureStageFrame | undefined =
    frames[frames.length - 1];

  // ターンストリップ専用。モーダルの送りはここを通さない
  const goToFrame = useCallback(
    (index: number) => {
      if (index < 0 || index >= frames.length) return;
      setSelectedFrameIndex(index === frames.length - 1 ? null : index);
    },
    [frames.length],
  );

  // モーダル内だけを動かす。前後送りと閉じてからの開き直しのどちらも
  // 直前に見ていたタブを引き継ぎ(タブ選択の復元)、
  // 送り先に存在しないタブへ着地しないようシーンへ戻す
  const openLightboxFrame = useCallback(
    (index: number, view?: AdventureLightboxView) => {
      if (index < 0 || index >= frames.length) return;
      const target = frames[index];
      const requested = view ?? lightboxView;
      const supported =
        requested === "partner"
          ? Boolean(target.partnerUrl)
          : requested === "portrait"
            ? Boolean(target.portraitUrl)
            : requested === "background"
              ? Boolean(target.backgroundUrl)
              : true;
      setLightboxIndex(index);
      setLightboxView(supported ? requested : "scene");
    },
    [frames, lightboxView],
  );
  const closeLightbox = useCallback(() => setLightboxIndex(null), []);
  const lightboxFrame =
    lightboxIndex !== null ? frames[lightboxIndex] : undefined;

  return {
    frames,
    selectedFrameIndex,
    setSelectedFrameIndex,
    isViewingPast,
    effectiveIndex,
    selectedFrame,
    latestFrame,
    goToFrame,
    lightboxIndex,
    lightboxView,
    setLightboxView,
    lightboxFrame,
    openLightboxFrame,
    closeLightbox,
  };
}
