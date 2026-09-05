import { useMemo } from "react";
import type { AdventureRun } from "../apis/adventure";
import { PORTRAIT_ALPHA_OPTIONS } from "../constants/adventure";
import type { AdventureStageFrame } from "../utils/adventureFrames";
import { useTransparentImage } from "./useTransparentImage";

/**
 * ステージと主人公ドックに出す白抜き済みの立ち絵。
 * 生成画像の白背景はわずかに灰色に振れるため、既定より広めの許容差で抜く。
 */
export function useAdventureStagePortraits(
  activeRun: AdventureRun | null,
  frames: AdventureStageFrame[],
  selectedFrameIndex: number | null,
) {
  const portraitSource = useMemo(() => {
    // 対面会話モードでは主人公の立ち絵をステージに出さない
    if (
      !activeRun ||
      activeRun.enable_composite_scene ||
      (activeRun.preset === "romance" && activeRun.companion_mode)
    ) {
      return null;
    }
    if (selectedFrameIndex !== null) {
      return (
        frames[selectedFrameIndex]?.imageUrl ?? activeRun.portrait_image_url
      );
    }
    return activeRun.portrait_image_url ?? activeRun.opening_portrait_url;
  }, [activeRun, frames, selectedFrameIndex]);
  const { url: stagePortraitUrl } = useTransparentImage(
    portraitSource,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  // romance 非合成モードの攻略対象立ち絵。過去フレーム閲覧中はその手番の1枚を表示する
  const stagePartnerSource =
    activeRun?.preset === "romance" &&
    (!activeRun?.enable_composite_scene || activeRun?.companion_mode)
      ? selectedFrameIndex !== null
        ? (frames[selectedFrameIndex]?.partnerUrl ?? null)
        : (activeRun?.partner_portrait_url ?? null)
      : null;
  const { url: stagePartnerUrl } = useTransparentImage(
    stagePartnerSource,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  // 主人公ドックは常に最新状態を見せる。過去フレーム閲覧中でも
  // 追従しないよう、ステージ用とは別に最新分を解決する。
  const { url: currentPortraitUrl } = useTransparentImage(
    activeRun?.portrait_image_url ?? activeRun?.opening_portrait_url ?? null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  // 攻略対象も同じく最新分。合成モードでもドックには並べる
  const { url: currentPartnerDockUrl } = useTransparentImage(
    activeRun?.preset === "romance"
      ? (activeRun?.partner_portrait_url ??
          activeRun?.opening_partner_portrait_url ??
          null)
      : null,
    true,
    PORTRAIT_ALPHA_OPTIONS,
  );
  return {
    stagePortraitUrl,
    stagePartnerUrl,
    currentPortraitUrl,
    currentPartnerDockUrl,
  };
}
