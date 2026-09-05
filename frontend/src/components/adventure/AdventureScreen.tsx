import { useLocation } from "react-router-dom";
import AdventureHub from "./AdventureHub";
import AdventurePlay from "./AdventurePlay";
import "./AdventureScreen.css";

// /adventure（Hub）と /adventure/:runId（Play）を切り替える入口。

export default function AdventureScreen() {
  const location = useLocation();
  const runId = location.pathname.split("/")[2];
  return runId ? <AdventurePlay runId={runId} /> : <AdventureHub />;
}
