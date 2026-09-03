/**
 * RealWorldLookupNote - 現実世界コンテキスト(天気・Web 検索)を参照した記録
 *
 * チャットの心境メッセージや TSF シナリオの手番ログの直下に置く小さな注記。
 * 浮遊要素は使わず、テキスト行と折りたたみ(details)だけで構成する。
 * 展開すると、画像タグと本文の根拠になった素材(検索理由・要約・出典の抜粋)を
 * 確認できる。URL を出すのはここだけで、本文側には書かせない。
 */
import { useTranslation } from "react-i18next";
import type { RealWorldLookup } from "../types";
import "./RealWorldLookupNote.css";

interface RealWorldLookupNoteProps {
  lookup: RealWorldLookup | null | undefined;
  className?: string;
}

export default function RealWorldLookupNote({
  lookup,
  className,
}: RealWorldLookupNoteProps) {
  const { t } = useTranslation();
  if (!lookup || (!lookup.weather && !lookup.search)) {
    return null;
  }
  const classes = ["real-world-note", className].filter(Boolean).join(" ");
  const search = lookup.search;
  return (
    <div className={classes}>
      {lookup.weather && (
        <span className="real-world-note__line">
          {t("realWorld.weatherRef", {
            location: lookup.weather.location,
            label: lookup.weather.label,
            temp: lookup.weather.temperature_c.toFixed(1),
          })}
        </span>
      )}
      {search && (
        <details className="real-world-note__details">
          <summary className="real-world-note__summary">
            {search.found === false
              ? t("realWorld.searchNotFound", { query: search.query })
              : t("realWorld.lookedUp", {
                  query: search.query,
                  count: search.sources.length,
                })}
          </summary>
          <div className="real-world-note__basis">
            {search.found !== false && (
              <p className="real-world-note__caption">
                {t("realWorld.basisCaption")}
              </p>
            )}
            {search.reason && (
              <p className="real-world-note__meta">
                {t("realWorld.searchReason")}: {search.reason}
              </p>
            )}
            {search.answer && (
              <p className="real-world-note__meta">
                {t("realWorld.searchSummary")}: {search.answer}
              </p>
            )}
            <ul className="real-world-note__sources">
              {search.sources.map((source) => (
                <li key={`${source.url}|${source.title}`}>
                  {source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {source.title || source.url}
                    </a>
                  ) : (
                    source.title
                  )}
                  {source.snippet && (
                    <span className="real-world-note__snippet">
                      {source.snippet}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </div>
  );
}
