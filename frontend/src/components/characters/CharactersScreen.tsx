import { useLocation } from "react-router-dom";
import { ROUTES } from "../../routes";
import CharacterEditorPage from "./CharacterEditorPage";
import CharacterListView from "./CharacterListView";
import "../characterChat/CharacterChatScreen.css";
import "./CharactersScreen.css";

/** /characters は一覧、/characters/:presetId は 1 人の編集画面 */
export default function CharactersScreen() {
  const location = useLocation();
  const rest = location.pathname.slice(ROUTES.CHARACTERS.length + 1);
  const presetId = decodeURIComponent(rest.split("/")[0] ?? "");
  if (!presetId) return <CharacterListView />;
  // 別のキャラクターへ移ったとき、編集中の状態を持ち越さない
  return <CharacterEditorPage key={presetId} presetId={presetId} />;
}
