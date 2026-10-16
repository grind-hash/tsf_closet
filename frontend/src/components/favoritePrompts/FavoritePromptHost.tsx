/**
 * お気に入りプロンプトのダイアログを全画面共通で 1 つだけ描画する（App 直下に置く）。
 * 開くたびに key を変え、ダイアログ内部のビュー状態を初期化する。
 */

import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import FavoritePromptDialog from "./FavoritePromptDialog";

export default function FavoritePromptHost() {
  const { dialog } = useFavoritePrompts();
  if (dialog.kind === "closed") return null;
  return <FavoritePromptDialog key={dialog.openId} />;
}
