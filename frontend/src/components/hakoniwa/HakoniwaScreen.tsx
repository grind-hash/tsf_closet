import { useLocation } from "react-router-dom";
import HakoniwaHub from "./HakoniwaHub";
import HakoniwaWorldView from "./HakoniwaWorldView";
import "./HakoniwaScreen.css";

// /hakoniwa(世界の一覧と作成)・/hakoniwa/:worldId(世界の画面)を切り替える入口。

export default function HakoniwaScreen() {
  const location = useLocation();
  const [, , worldId] = location.pathname.split("/");
  return worldId ? <HakoniwaWorldView worldId={worldId} /> : <HakoniwaHub />;
}
