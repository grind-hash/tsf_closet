/**
 * useTagSuggest hook - タグサジェスト機能のカスタムフック
 *
 * NovelAI suggest-tags APIを呼び出し、プロンプト入力補助用のタグ候補を取得する。
 *
 * @module hooks/useTagSuggest
 * @see specs/006-novelai-prompt-enhancement
 */

import { useState, useCallback } from "react";
import type { TagSuggestion, TagSuggestResponse } from "../types";
import { prepareTagSearchQuery } from "../utils/katakanaToHiragana";
import { API_BASE } from "../utils/api";

export type TagSuggestState = "idle" | "loading" | "success" | "error";

export interface UseTagSuggestReturn {
  /** 現在の状態 */
  state: TagSuggestState;
  /** タグ候補リスト */
  tags: TagSuggestion[];
  /** エラーメッセージ */
  error: string | null;
  /** 最後に検索したクエリ */
  lastQuery: string | null;
  /** タグ検索を実行 */
  searchTags: (query: string) => Promise<void>;
  /** 状態をリセット */
  reset: () => void;
}

/**
 * タグサジェスト機能のカスタムフック
 *
 * @returns {UseTagSuggestReturn} タグサジェスト機能の状態と操作
 *
 * @example
 * ```tsx
 * const { state, tags, error, searchTags, reset } = useTagSuggest();
 *
 * const handleSearch = async () => {
 *   await searchTags("ティファ");
 *   // tags: [{ tag: "tifa_lockhart", count: 12345 }, ...]
 * };
 * ```
 */
export function useTagSuggest(): UseTagSuggestReturn {
  const [state, setState] = useState<TagSuggestState>("idle");
  const [tags, setTags] = useState<TagSuggestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState<string | null>(null);

  /**
   * タグ検索を実行
   *
   * @param query - 検索クエリ（ユーザー入力）
   */
  const searchTags = useCallback(async (query: string): Promise<void> => {
    // 空入力チェック
    if (!query || query.trim() === "") {
      setError("検索するキーワードを入力してください");
      setState("error");
      return;
    }

    // カタカナ→ひらがな変換を適用
    const preparedQuery = prepareTagSearchQuery(query.trim());

    setState("loading");
    setError(null);
    setLastQuery(query);

    try {
      const params = new URLSearchParams({
        prompt: preparedQuery,
        model: "nai-diffusion-4-5-full",
        lang: "jp",
      });

      const response = await fetch(
        `${API_BASE}/novelai/suggest-tags?${params.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage =
          errorData.detail || `API error: ${response.status}`;
        throw new Error(errorMessage);
      }

      const data: TagSuggestResponse = await response.json();

      if (data.tags.length === 0) {
        setTags([]);
        setError("候補が見つかりませんでした");
        setState("success"); // 成功だが結果なし
        return;
      }

      setTags(data.tags);
      setState("success");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "タグ検索に失敗しました";
      setError(message);
      setState("error");
      setTags([]);
    }
  }, []);

  /**
   * 状態をリセット
   */
  const reset = useCallback(() => {
    setState("idle");
    setTags([]);
    setError(null);
    setLastQuery(null);
  }, []);

  return {
    state,
    tags,
    error,
    lastQuery,
    searchTags,
    reset,
  };
}
