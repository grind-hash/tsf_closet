/**
 * 設定画面の検索で一致した文字をハイライトする。
 *
 * CSS Custom Highlight API を使い、DOM は書き換えない。
 * 対応していないブラウザではハイライトしない。
 */

import { type RefObject, useEffect } from "react";
import { foldSearchChars, toSearchTerms } from "./settingsSearchIndex";

const HIGHLIGHT_NAME = "settings-search";

/** ハイライトしない要素（選択肢の中身や入力欄） */
const SKIPPED_ANCESTORS = "option, script, style, textarea";

/**
 * text の中で、検索語のいずれかに一致する範囲を返す（元の文字列での位置）。
 * 重なる範囲はまとめる。
 */
export function findTextMatchRanges(
  text: string,
  terms: readonly string[],
): Array<[number, number]> {
  // 1文字ずつそろえ、そろえた後の位置から元の位置へ戻せるようにする
  let folded = "";
  const starts: number[] = [];
  const ends: number[] = [];
  let offset = 0;
  for (const ch of text) {
    const piece = foldSearchChars(ch);
    for (let i = 0; i < piece.length; i++) {
      starts.push(offset);
      ends.push(offset + ch.length);
    }
    folded += piece;
    offset += ch.length;
  }

  const ranges: Array<[number, number]> = [];
  for (const term of terms) {
    if (!term) continue;
    let from = 0;
    for (;;) {
      const at = folded.indexOf(term, from);
      if (at < 0) break;
      ranges.push([starts[at], ends[at + term.length - 1]]);
      from = at + term.length;
    }
  }

  ranges.sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) {
      last[1] = Math.max(last[1], range[1]);
    } else {
      merged.push([range[0], range[1]]);
    }
  }
  return merged;
}

function getHighlightRegistry(): HighlightRegistry | null {
  if (
    typeof CSS === "undefined" ||
    !("highlights" in CSS) ||
    typeof Highlight === "undefined"
  ) {
    return null;
  }
  return CSS.highlights;
}

/**
 * container 内の一致箇所をハイライトする。
 * 中身が後から読み込まれても追従するよう、DOM の変化を監視して付け直す。
 */
export function useSearchHighlight(
  containerRef: RefObject<HTMLElement | null>,
  query: string,
) {
  useEffect(() => {
    const registry = getHighlightRegistry();
    if (!registry) return;
    const container = containerRef.current;
    const terms = toSearchTerms(query);
    if (!container || terms.length === 0) {
      registry.delete(HIGHLIGHT_NAME);
      return;
    }

    let frame = 0;
    const apply = () => {
      frame = 0;
      const highlight = new Highlight();
      const walker = document.createTreeWalker(
        container,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode: (node) =>
            node.parentElement?.closest(SKIPPED_ANCESTORS)
              ? NodeFilter.FILTER_REJECT
              : NodeFilter.FILTER_ACCEPT,
        },
      );
      for (
        let node = walker.nextNode();
        node !== null;
        node = walker.nextNode()
      ) {
        for (const [start, end] of findTextMatchRanges(
          node.nodeValue ?? "",
          terms,
        )) {
          const range = document.createRange();
          range.setStart(node, start);
          range.setEnd(node, end);
          highlight.add(range);
        }
      }
      registry.set(HIGHLIGHT_NAME, highlight);
    };

    apply();
    const observer = new MutationObserver(() => {
      if (frame === 0) frame = requestAnimationFrame(apply);
    });
    observer.observe(container, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => {
      observer.disconnect();
      if (frame !== 0) cancelAnimationFrame(frame);
      registry.delete(HIGHLIGHT_NAME);
    };
  }, [containerRef, query]);
}
