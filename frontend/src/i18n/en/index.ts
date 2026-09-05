// 英語の翻訳リソース。名前空間ごとのファイルを 1 つのオブジェクトにまとめる。
// キーの追加・変更は ja と en の両方に行うこと（型チェックで乖離を検出する）。

import { achievements } from "./achievements";
import { achievementToast } from "./achievementToast";
import { adventure } from "./adventure";
import { apiKeyConsent } from "./apiKeyConsent";
import { appLoading } from "./appLoading";
import { bgmTest } from "./bgmTest";
import { branchSession } from "./branchSession";
import { character } from "./character";
import { characterPanel } from "./characterPanel";
import { chat } from "./chat";
import { common } from "./common";
import { consentDeclined } from "./consentDeclined";
import { endings } from "./endings";
import { favorites } from "./favorites";
import { gallery } from "./gallery";
import { gameplay } from "./gameplay";
import { guide } from "./guide";
import { imagePreview } from "./imagePreview";
import { inpaint } from "./inpaint";
import { layout } from "./layout";
import { menu } from "./menu";
import { novelaiWarning } from "./novelaiWarning";
import { promptExpander } from "./promptExpander";
import { rightPanel } from "./rightPanel";
import { sessionList } from "./sessionList";
import { settings } from "./settings";

export const en = {
  menu,
  guide,
  layout,
  adventure,
  bgmTest,
  settings,
  common,
  rightPanel,
  characterPanel,
  branchSession,
  sessionList,
  imagePreview,
  achievementToast,
  inpaint,
  chat,
  gameplay,
  gallery,
  favorites,
  achievements,
  endings,
  novelaiWarning,
  appLoading,
  consentDeclined,
  apiKeyConsent,
  character,
  promptExpander,
};
