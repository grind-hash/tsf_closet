import type {
  CharacterChatLookupCitation,
  CharacterChatMessageMeta,
} from "../../apis/characterChat";

export const LOOKUP_KINDS = [
  "recent_sessions",
  "session_detail",
  "search_sessions",
  "tendencies",
  "recent_adventures",
  "web_search",
  "weather",
] as const;
export type LookupKind = (typeof LOOKUP_KINDS)[number];

export function isLookupKind(value: string): value is LookupKind {
  return (LOOKUP_KINDS as readonly string[]).includes(value);
}

/** Web 検索の出典 1 件 */
export interface CitationSource {
  title: string;
  url: string;
}

/** 返答の根拠にした調べ物 1 件。text が無いものは旧データ(種類だけ保存) */
export interface LookupCitation {
  kind: LookupKind;
  query: string | null;
  /** キャラが実際に読んだ整形済み本文 */
  text: string | null;
  /** 本文に含まれるセッションの ID(「[先頭8桁]」からギャラリーへ飛ぶ対応表) */
  sessionIds: string[];
  /** Web 検索の出典。出典を持たない種類と旧データは空 */
  sources: CitationSource[];
  /** 検索サービスの利用規約で見送った Web 検索。query は送らなかった検索語 */
  refused?: boolean;
}

/**
 * 出典をリンクにできるものだけへ絞る。http(s) 以外(javascript: 等)と解釈できない
 * URL は捨て、題名が空ならホスト名で補う。同じ URL は先頭の 1 件だけ残す。
 */
function toCitationSources(
  raw: CharacterChatLookupCitation["sources"],
): CitationSource[] {
  if (!Array.isArray(raw)) return [];
  const sources: CitationSource[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (!item || typeof item !== "object" || typeof item.url !== "string") {
      continue;
    }
    let url: URL;
    try {
      url = new URL(item.url.trim());
    } catch {
      continue;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") continue;
    if (seen.has(url.href)) continue;
    seen.add(url.href);
    const title = typeof item.title === "string" ? item.title.trim() : "";
    sources.push({ title: title || url.hostname, url: url.href });
  }
  return sources;
}

/** meta.lookups(種類の文字列と明細オブジェクトの混在)を引用表示用に正規化する */
export function toLookupCitations(
  meta: CharacterChatMessageMeta | null | undefined,
): LookupCitation[] {
  const citations: LookupCitation[] = [];
  for (const item of meta?.lookups ?? []) {
    if (typeof item === "string") {
      if (isLookupKind(item)) {
        citations.push({
          kind: item,
          query: null,
          text: null,
          sessionIds: [],
          sources: [],
        });
      }
      continue;
    }
    if (!item || typeof item !== "object" || !isLookupKind(item.kind)) continue;
    citations.push({
      kind: item.kind,
      query: item.query?.trim() || null,
      text: item.text?.trim() || null,
      sessionIds: (item.session_ids ?? []).filter(
        (id): id is string => typeof id === "string" && id.length > 0,
      ),
      sources: toCitationSources(item.sources),
      ...(item.refused ? { refused: true } : {}),
    });
  }
  return citations;
}

/** 本文中の「[先頭8桁]」を完全なセッション ID へ引き当てる対応表 */
export function sessionIdByPrefix(sessionIds: string[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const id of sessionIds) map.set(id.slice(0, 8), id);
  return map;
}
