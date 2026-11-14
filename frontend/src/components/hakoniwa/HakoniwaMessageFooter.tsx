import { useTranslation } from "react-i18next";
import type { HakoniwaWebSearch } from "../../apis/hakoniwa";

/** 会話の共通注記と、その返答・出来事で利用した出典を表示する。 */
export default function HakoniwaMessageFooter({
  search,
}: {
  search?: HakoniwaWebSearch | null;
}) {
  const { t, i18n } = useTranslation();
  const seen = new Set<string>();
  const sources = (search?.status === "used" ? search.sources : []).flatMap(
    (source) => {
      try {
        const url = new URL(source.url);
        if (!["http:", "https:"].includes(url.protocol) || seen.has(url.href)) {
          return [];
        }
        seen.add(url.href);
        return [{ title: source.title.trim() || url.hostname, url: url.href }];
      } catch {
        return [];
      }
    },
  );
  const retrievedAt = search ? new Date(search.retrieved_at) : null;
  const retrievedLabel =
    retrievedAt && !Number.isNaN(retrievedAt.getTime())
      ? retrievedAt.toLocaleString(i18n.resolvedLanguage)
      : search?.retrieved_at;

  return (
    // 出典のクリック・キー操作を、背後の幕送りへ伝えない
    <div
      className="hakoniwa-message-footer"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") event.stopPropagation();
      }}
    >
      <p className="hakoniwa-message-footer__notice">
        {t("hakoniwa.webSearch.aiNotice")}
      </p>
      {search && search.status !== "used" && (
        <p className="hakoniwa-message-footer__status">
          {t(`hakoniwa.webSearch.${search.status}`)}
        </p>
      )}
      {sources.length > 0 && search && (
        <details key={`${search.retrieved_at}:${search.query}`}>
          <summary>{t("hakoniwa.webSearch.references")}</summary>
          <p>{t("hakoniwa.webSearch.query", { query: search.query })}</p>
          <p>
            {t("hakoniwa.webSearch.retrievedAt", {
              date: retrievedLabel,
            })}
          </p>
          <ul>
            {sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.title}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
