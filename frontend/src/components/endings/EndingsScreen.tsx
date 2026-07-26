import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE } from "../../utils/api";
import MainLayout from "../layout/MainLayout";
import "./EndingsScreen.css";

interface EndingItem {
  id: string;
  title: string;
  condition_text: string;
  achieved: boolean;
}

export default function EndingsScreen() {
  const { t } = useTranslation();
  const [endings, setEndings] = useState<EndingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchEndings = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${API_BASE}/game/endings`);
        if (!response.ok) {
          throw new Error(
            t("endings.fetchError", {
              status: response.status,
              statusText: response.statusText,
            }),
          );
        }
        const data = await response.json();
        setEndings(data.endings ?? []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t("endings.genericError"),
        );
      } finally {
        setLoading(false);
      }
    };
    fetchEndings();
  }, [t]);

  return (
    <MainLayout>
      <div className="endings-screen">
        <h1 className="endings-screen__title">{t("endings.title")}</h1>
        {loading && (
          <p className="endings-screen__status">{t("endings.loading")}</p>
        )}
        {error && <p className="endings-screen__status">{error}</p>}
        {!loading && !error && (
          <div className="endings-screen__list">
            {endings.map((ending) => (
              <div key={ending.id} className="endings-screen__item">
                <div className="endings-screen__item-header">
                  <h2>{ending.title}</h2>
                  <span>
                    {ending.achieved
                      ? t("endings.achieved")
                      : t("endings.notAchieved")}
                  </span>
                </div>
                <p>{ending.condition_text}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
