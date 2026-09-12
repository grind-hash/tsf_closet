import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ROUTES } from "../../routes";
import {
  type CitationSource,
  type LookupCitation,
  sessionIdByPrefix,
} from "./lookupCitations";

interface CharacterChatCitationsProps {
  citations: LookupCitation[];
}

/** 調べ物の本文で、行頭の「- [先頭8桁]」がセッションを指す */
const SESSION_REF = /^(- )\[([0-9a-f]{8})\]/;

interface CitationTextProps {
  text: string;
  sessionIds: string[];
}

/** 調べ物の本文。セッション参照はギャラリーのそのセッションへのリンクにする */
function CitationText({ text, sessionIds }: CitationTextProps) {
  const { t } = useTranslation();
  const byPrefix = sessionIdByPrefix(sessionIds);
  return (
    <p className="character-chat__citation-text">
      {text.split("\n").map((line, index) => {
        const match = line.match(SESSION_REF);
        const sessionId = match ? byPrefix.get(match[2]) : undefined;
        return (
          <span
            // biome-ignore lint/suspicious/noArrayIndexKey: 本文の行は同じ文になり得るため位置で識別する
            key={index}
            className="character-chat__citation-line"
          >
            {match && sessionId ? (
              <>
                {match[1]}
                <Link
                  className="character-chat__citation-link"
                  to={`${ROUTES.GALLERY}/${sessionId}`}
                  title={t("characterChat.thread.citationOpenSession")}
                >
                  [{match[2]}]
                </Link>
                {line.slice(match[0].length)}
              </>
            ) : (
              line
            )}
          </span>
        );
      })}
    </p>
  );
}

/** Web 検索の出典。URL は正規化の段階で http(s) のものだけに絞ってある */
function CitationSources({ sources }: { sources: CitationSource[] }) {
  const { t } = useTranslation();
  return (
    <div className="character-chat__citation-sources">
      <span className="character-chat__citation-sources-title">
        {t("characterChat.thread.citationSources")}
      </span>
      <ul className="character-chat__citation-source-list">
        {sources.map((source) => (
          <li key={source.url}>
            <a
              className="character-chat__citation-link"
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {source.title}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 返答の根拠として実行した調べ物(引用)。本文があるものは折りたたみで開け、
 * キャラが実際に読んだ整形済みテキストをそのまま見せる。Web 検索は送った語と
 * 出典のリンクも添え、利用規約で見送ったものは送らなかった語と理由を示す。
 * 旧データ(種類だけ)のときは種類の一覧を 1 行で出す。
 */
export default function CharacterChatCitations({
  citations,
}: CharacterChatCitationsProps) {
  const { t } = useTranslation();
  if (citations.length === 0) return null;
  const kindLabel = (citation: LookupCitation) => {
    const kind = t(`characterChat.thread.lookupKind.${citation.kind}`);
    return citation.refused
      ? t("characterChat.thread.lookupRefused", { kind })
      : kind;
  };
  const queryLabel = (citation: LookupCitation, query: string) => {
    if (citation.refused) {
      return t("characterChat.thread.citationRefusedQuery", { query });
    }
    return citation.kind === "web_search"
      ? t("characterChat.thread.citationWebQuery", { query })
      : t("characterChat.thread.citationQuery", { query });
  };
  const kinds = citations
    .map((citation) => {
      const kind = kindLabel(citation);
      return citation.query
        ? t("characterChat.thread.lookupWithQuery", {
            kind,
            query: citation.query,
          })
        : kind;
    })
    .join(" / ");
  const label = t("characterChat.thread.lookups", { kinds });
  if (
    !citations.some((citation) => citation.text || citation.sources.length > 0)
  ) {
    return <div className="character-chat__citations is-static">{label}</div>;
  }
  return (
    <details className="character-chat__citations">
      <summary>{label}</summary>
      {citations.map((citation, index) => (
        <section
          // biome-ignore lint/suspicious/noArrayIndexKey: 同じ種類・検索語の調べ物が並び得るため位置で識別する
          key={index}
          className="character-chat__citation"
        >
          <div className="character-chat__citation-head">
            <span>{kindLabel(citation)}</span>
            {citation.query && (
              <span className="character-chat__citation-query">
                {queryLabel(citation, citation.query)}
              </span>
            )}
          </div>
          {citation.text ? (
            <CitationText
              text={citation.text}
              sessionIds={citation.sessionIds}
            />
          ) : (
            citation.sources.length === 0 && (
              <p className="character-chat__citation-text">
                {t("characterChat.thread.citationNoText")}
              </p>
            )
          )}
          {citation.sources.length > 0 && (
            <CitationSources sources={citation.sources} />
          )}
        </section>
      ))}
    </details>
  );
}
