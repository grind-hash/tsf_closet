import type { CharacterChatMessageMeta } from "../../apis/characterChat";

export const LOOKUP_KINDS = [
  "recent_sessions",
  "session_detail",
  "search_sessions",
  "tendencies",
  "recent_adventures",
] as const;
export type LookupKind = (typeof LOOKUP_KINDS)[number];

export function isLookupKind(value: string): value is LookupKind {
  return (LOOKUP_KINDS as readonly string[]).includes(value);
}

/** 返答の根拠にした調べ物 1 件。text が無いものは旧データ(種類だけ保存) */
export interface LookupCitation {
  kind: LookupKind;
  query: string | null;
  /** キャラが実際に読んだ整形済み本文 */
  text: string | null;
  /** 本文に含まれるセッションの ID(「[先頭8桁]」からギャラリーへ飛ぶ対応表) */
  sessionIds: string[];
}

/** meta.lookups(種類の文字列と明細オブジェクトの混在)を引用表示用に正規化する */
export function toLookupCitations(
  meta: CharacterChatMessageMeta | null | undefined,
): LookupCitation[] {
  const citations: LookupCitation[] = [];
  for (const item of meta?.lookups ?? []) {
    if (typeof item === "string") {
      if (isLookupKind(item)) {
        citations.push({ kind: item, query: null, text: null, sessionIds: [] });
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
