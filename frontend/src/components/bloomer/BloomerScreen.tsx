import { useEffect } from "react";
import { useBloomer } from "../../contexts/BloomerContext";
import BloomerHub from "./BloomerHub";
import BloomerRoom from "./BloomerRoom";

export default function BloomerScreen() {
  const { activeRun, loadRuns, loadCatalog } = useBloomer();

  useEffect(() => {
    loadRuns();
    loadCatalog();
  }, [loadRuns, loadCatalog]);

  if (activeRun) {
    return <BloomerRoom />;
  }
  return <BloomerHub />;
}
