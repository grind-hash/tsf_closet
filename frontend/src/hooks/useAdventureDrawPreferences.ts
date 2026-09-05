import {
  DRAW_PARTNER_STORAGE_KEY,
  DRAW_PORTRAIT_STORAGE_KEY,
} from "../contexts/AdventureContext";
import { usePersistedState } from "./usePersistedState";

/**
 * 立ち絵を毎ターン描くかの好み（主人公 / 攻略対象）。ブラウザ単位で保持し、
 * セットアップ画面（AdventureHub）とプレイ画面（AdventurePlay）で共有する。
 * 送信時の反映は AdventureContext.submitTurn が同じキーを読む。
 */
export function useAdventureDrawPreferences() {
  const [drawPortraitEveryTurn, setDrawPortraitEveryTurn] =
    usePersistedState<boolean>(DRAW_PORTRAIT_STORAGE_KEY, true);
  const [drawPartnerEveryTurn, setDrawPartnerEveryTurn] =
    usePersistedState<boolean>(DRAW_PARTNER_STORAGE_KEY, true);
  return {
    drawPortraitEveryTurn,
    setDrawPortraitEveryTurn,
    drawPartnerEveryTurn,
    setDrawPartnerEveryTurn,
  };
}
