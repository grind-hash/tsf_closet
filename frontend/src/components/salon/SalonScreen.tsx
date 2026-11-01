import { useLocation } from "react-router-dom";
import SalonHub from "./SalonHub";
import SalonOffice from "./SalonOffice";
import SalonServing from "./SalonServing";
import "./SalonScreen.css";

// /salon（一覧と開店）・/salon/:runId（帳場）・/salon/:runId/visits/:visitId（接客）を切り替える入口。

export default function SalonScreen() {
  const location = useLocation();
  const [, , runId, section, visitId] = location.pathname.split("/");
  if (runId && section === "visits" && visitId) {
    return <SalonServing runId={runId} visitId={visitId} />;
  }
  return runId ? <SalonOffice runId={runId} /> : <SalonHub />;
}
