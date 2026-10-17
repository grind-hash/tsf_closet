/**
 * FavoritePromptContext - お気に入りプロンプト（TSF Closet 内保存のタグ・文章）
 *
 * 一覧データと、全画面で共有する 1 つのダイアログ（挿入 / 保存）を管理する。
 * 各画面のボタンは useFavoritePrompts() の openPicker / openSaveDialog を呼ぶだけで、
 * ダイアログ本体は App 直下の FavoritePromptHost が描画する。
 * CSV / JSON ファイルへの書き出し・読み込みと、ドラッグ＆ドロップの並べ替えもここで行う。
 */

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { useTranslation } from "react-i18next";
import {
  createFavoritePrompt,
  createFavoritePromptCategory,
  deleteFavoritePrompt,
  deleteFavoritePromptCategory,
  exportFavoritePrompts,
  type FavoritePrompt,
  type FavoritePromptCategory,
  type FavoritePromptCategoryInput,
  type FavoritePromptFileFormat,
  type FavoritePromptImportPreview,
  type FavoritePromptImportResult,
  type FavoritePromptInput,
  type FavoritePromptPlacement,
  fetchFavoritePrompts,
  importFavoritePrompts,
  previewFavoritePromptImport,
  reorderFavoritePrompts,
  updateFavoritePrompt,
  updateFavoritePromptCategory,
} from "../apis/favoritePrompts";
import {
  type FavoritePromptDropTarget,
  moveFavoritePrompt,
} from "../utils/favoritePromptOrder";
import { useNotification } from "./NotificationContext";

/** picker: 一覧から選んで挿入する / save: 新規フォームを内容入りで開く */
export type FavoritePromptDialog =
  | { kind: "closed" }
  | { kind: "picker"; openId: number }
  | { kind: "save"; openId: number; content: string };

interface FavoritePromptState {
  prompts: FavoritePrompt[];
  categories: FavoritePromptCategory[];
  loaded: boolean;
  loading: boolean;
  dialog: FavoritePromptDialog;
}

type FavoritePromptAction =
  | { type: "LOAD_START" }
  | {
      type: "LOAD_DONE";
      prompts: FavoritePrompt[];
      categories: FavoritePromptCategory[];
    }
  | { type: "LOAD_FAILED" }
  | { type: "UPSERT_PROMPT"; prompt: FavoritePrompt }
  | { type: "APPLY_ORDER"; placements: FavoritePromptPlacement[] }
  | { type: "REMOVE_PROMPT"; promptId: string }
  | { type: "UPSERT_CATEGORY"; category: FavoritePromptCategory }
  | { type: "REMOVE_CATEGORY"; categoryId: string }
  | { type: "OPEN_PICKER"; openId: number }
  | { type: "OPEN_SAVE"; openId: number; content: string }
  | { type: "CLOSE" };

const initialState: FavoritePromptState = {
  prompts: [],
  categories: [],
  loaded: false,
  loading: false,
  dialog: { kind: "closed" },
};

function bySortOrder<T extends { sort_order: number }>(items: T[]): T[] {
  return [...items].sort((a, b) => a.sort_order - b.sort_order);
}

function upsert<T extends { id: string; sort_order: number }>(
  items: T[],
  item: T,
): T[] {
  const exists = items.some((i) => i.id === item.id);
  const next = exists
    ? items.map((i) => (i.id === item.id ? item : i))
    : [...items, item];
  return bySortOrder(next);
}

// ダイアログを開くたびに変わる番号（ダイアログ内部の状態を開き直しでリセットするため）
let openCounter = 0;
function nextOpenId(): number {
  openCounter += 1;
  return openCounter;
}

function favoritePromptReducer(
  state: FavoritePromptState,
  action: FavoritePromptAction,
): FavoritePromptState {
  switch (action.type) {
    case "LOAD_START":
      return { ...state, loading: true };
    case "LOAD_DONE":
      return {
        ...state,
        loading: false,
        loaded: true,
        prompts: bySortOrder(action.prompts),
        categories: bySortOrder(action.categories),
      };
    case "LOAD_FAILED":
      return { ...state, loading: false };
    case "UPSERT_PROMPT":
      return { ...state, prompts: upsert(state.prompts, action.prompt) };
    case "APPLY_ORDER": {
      // 保存の応答を待たずに並びを反映する（失敗したら元へ戻す）
      const placed = new Map(
        action.placements.map((p, index) => [p.id, { ...p, index }]),
      );
      return {
        ...state,
        prompts: bySortOrder(
          state.prompts.map((prompt) => {
            const next = placed.get(prompt.id);
            return next
              ? {
                  ...prompt,
                  category_id: next.category_id,
                  sort_order: next.index,
                }
              : prompt;
          }),
        ),
      };
    }
    case "REMOVE_PROMPT":
      return {
        ...state,
        prompts: state.prompts.filter((p) => p.id !== action.promptId),
      };
    case "UPSERT_CATEGORY":
      return {
        ...state,
        categories: upsert(state.categories, action.category),
      };
    case "REMOVE_CATEGORY":
      // バックエンドと同じく、中のプロンプトは未分類へ移す
      return {
        ...state,
        categories: state.categories.filter((c) => c.id !== action.categoryId),
        prompts: state.prompts.map((p) =>
          p.category_id === action.categoryId ? { ...p, category_id: null } : p,
        ),
      };
    case "OPEN_PICKER":
      return { ...state, dialog: { kind: "picker", openId: action.openId } };
    case "OPEN_SAVE":
      return {
        ...state,
        dialog: {
          kind: "save",
          openId: action.openId,
          content: action.content,
        },
      };
    case "CLOSE":
      return { ...state, dialog: { kind: "closed" } };
    default:
      return state;
  }
}

interface FavoritePromptContextValue {
  prompts: FavoritePrompt[];
  categories: FavoritePromptCategory[];
  loaded: boolean;
  loading: boolean;
  dialog: FavoritePromptDialog;
  /** 一覧ダイアログを開く。選ばれた内容は onInsert に渡す */
  openPicker: (onInsert: (content: string) => void) => void;
  /** 新規フォームを content 入りで開く（保存はフォームの保存ボタンで行う） */
  openSaveDialog: (content: string) => void;
  closeDialog: () => void;
  /** picker で選ばれた内容を呼び出し元へ渡してダイアログを閉じる */
  insertPrompt: (content: string) => void;
  /** 未読み込みなら一覧を取得する */
  ensureLoaded: () => Promise<void>;
  createPrompt: (input: FavoritePromptInput) => Promise<FavoritePrompt | null>;
  updatePrompt: (
    promptId: string,
    changes: Partial<FavoritePromptInput>,
  ) => Promise<FavoritePrompt | null>;
  deletePrompt: (promptId: string) => Promise<boolean>;
  /** 並べ替え・カテゴリー移動（すぐ画面に反映し、保存に失敗したら元へ戻す） */
  movePrompt: (
    promptId: string,
    target: FavoritePromptDropTarget,
  ) => Promise<boolean>;
  createCategory: (
    input: FavoritePromptCategoryInput,
  ) => Promise<FavoritePromptCategory | null>;
  updateCategory: (
    categoryId: string,
    changes: Partial<FavoritePromptCategoryInput>,
  ) => Promise<FavoritePromptCategory | null>;
  deleteCategory: (categoryId: string) => Promise<boolean>;
  /** すべてをファイルとして保存する（CSV の見出しは表示言語に合わせる） */
  exportPrompts: (format: FavoritePromptFileFormat) => Promise<boolean>;
  /** 書き込まずに、追加・上書きされる内容を確認する */
  previewImport: (file: File) => Promise<FavoritePromptImportPreview | null>;
  /** 取り込んで一覧を置き換え、結果を通知する */
  importPrompts: (file: File) => Promise<FavoritePromptImportResult | null>;
}

const FavoritePromptContext = createContext<FavoritePromptContextValue | null>(
  null,
);

export function FavoritePromptProvider({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const { showNotification } = useNotification();
  const [state, dispatch] = useReducer(favoritePromptReducer, initialState);
  const onInsertRef = useRef<((content: string) => void) | null>(null);
  const loadRef = useRef<Promise<void> | null>(null);
  const loadedRef = useRef(false);

  const reportError = useCallback(
    (fallback: string, err: unknown) => {
      const message = err instanceof Error && err.message ? err.message : "";
      showNotification(
        "error",
        t("favoritePrompts.title"),
        message || fallback,
      );
    },
    [showNotification, t],
  );

  const ensureLoaded = useCallback(async () => {
    if (loadedRef.current) return;
    if (loadRef.current) return loadRef.current;
    dispatch({ type: "LOAD_START" });
    const task = (async () => {
      try {
        const data = await fetchFavoritePrompts();
        loadedRef.current = true;
        dispatch({
          type: "LOAD_DONE",
          prompts: data.prompts,
          categories: data.categories,
        });
      } catch (err) {
        dispatch({ type: "LOAD_FAILED" });
        reportError(t("favoritePrompts.loadFailed"), err);
      } finally {
        loadRef.current = null;
      }
    })();
    loadRef.current = task;
    return task;
  }, [reportError, t]);

  const openPicker = useCallback((onInsert: (content: string) => void) => {
    onInsertRef.current = onInsert;
    dispatch({ type: "OPEN_PICKER", openId: nextOpenId() });
  }, []);

  const openSaveDialog = useCallback((content: string) => {
    onInsertRef.current = null;
    dispatch({ type: "OPEN_SAVE", openId: nextOpenId(), content });
  }, []);

  const closeDialog = useCallback(() => {
    onInsertRef.current = null;
    dispatch({ type: "CLOSE" });
  }, []);

  const insertPrompt = useCallback((content: string) => {
    const onInsert = onInsertRef.current;
    onInsertRef.current = null;
    dispatch({ type: "CLOSE" });
    onInsert?.(content);
  }, []);

  const createPrompt = useCallback(
    async (input: FavoritePromptInput) => {
      try {
        const prompt = await createFavoritePrompt(input);
        dispatch({ type: "UPSERT_PROMPT", prompt });
        return prompt;
      } catch (err) {
        reportError(t("favoritePrompts.saveFailed"), err);
        return null;
      }
    },
    [reportError, t],
  );

  const updatePrompt = useCallback(
    async (promptId: string, changes: Partial<FavoritePromptInput>) => {
      try {
        const prompt = await updateFavoritePrompt(promptId, changes);
        dispatch({ type: "UPSERT_PROMPT", prompt });
        return prompt;
      } catch (err) {
        reportError(t("favoritePrompts.saveFailed"), err);
        return null;
      }
    },
    [reportError, t],
  );

  const deletePrompt = useCallback(
    async (promptId: string) => {
      try {
        await deleteFavoritePrompt(promptId);
        dispatch({ type: "REMOVE_PROMPT", promptId });
        return true;
      } catch (err) {
        reportError(t("favoritePrompts.deleteFailed"), err);
        return false;
      }
    },
    [reportError, t],
  );

  const movePrompt = useCallback(
    async (promptId: string, target: FavoritePromptDropTarget) => {
      const placements = moveFavoritePrompt(
        state.prompts,
        state.categories,
        promptId,
        target,
      );
      if (!placements) return true;
      const previous = {
        prompts: state.prompts,
        categories: state.categories,
      };
      dispatch({ type: "APPLY_ORDER", placements });
      try {
        const data = await reorderFavoritePrompts(placements);
        dispatch({
          type: "LOAD_DONE",
          prompts: data.prompts,
          categories: data.categories,
        });
        return true;
      } catch (err) {
        dispatch({ type: "LOAD_DONE", ...previous });
        reportError(t("favoritePrompts.reorderFailed"), err);
        return false;
      }
    },
    [state.prompts, state.categories, reportError, t],
  );

  const createCategory = useCallback(
    async (input: FavoritePromptCategoryInput) => {
      try {
        const category = await createFavoritePromptCategory(input);
        dispatch({ type: "UPSERT_CATEGORY", category });
        return category;
      } catch (err) {
        reportError(t("favoritePrompts.saveFailed"), err);
        return null;
      }
    },
    [reportError, t],
  );

  const updateCategory = useCallback(
    async (
      categoryId: string,
      changes: Partial<FavoritePromptCategoryInput>,
    ) => {
      try {
        const category = await updateFavoritePromptCategory(
          categoryId,
          changes,
        );
        dispatch({ type: "UPSERT_CATEGORY", category });
        return category;
      } catch (err) {
        reportError(t("favoritePrompts.saveFailed"), err);
        return null;
      }
    },
    [reportError, t],
  );

  const deleteCategory = useCallback(
    async (categoryId: string) => {
      try {
        await deleteFavoritePromptCategory(categoryId);
        dispatch({ type: "REMOVE_CATEGORY", categoryId });
        return true;
      } catch (err) {
        reportError(t("favoritePrompts.deleteFailed"), err);
        return false;
      }
    },
    [reportError, t],
  );

  const exportPrompts = useCallback(
    async (format: FavoritePromptFileFormat) => {
      try {
        const language = i18n.language?.startsWith("en") ? "en" : "ja";
        await exportFavoritePrompts(format, language);
        return true;
      } catch (err) {
        reportError(t("favoritePrompts.transfer.exportFailed"), err);
        return false;
      }
    },
    [i18n.language, reportError, t],
  );

  const previewImport = useCallback(
    async (file: File) => {
      try {
        return await previewFavoritePromptImport(file);
      } catch (err) {
        reportError(t("favoritePrompts.transfer.importFailed"), err);
        return null;
      }
    },
    [reportError, t],
  );

  const importPrompts = useCallback(
    async (file: File) => {
      try {
        const result = await importFavoritePrompts(file);
        loadedRef.current = true;
        dispatch({
          type: "LOAD_DONE",
          prompts: result.prompts,
          categories: result.categories,
        });
        const changed =
          result.create_count +
          result.overwrites.length +
          result.new_categories.length;
        if (changed === 0) {
          showNotification(
            "info",
            t("favoritePrompts.title"),
            t("favoritePrompts.transfer.importNothing"),
          );
        } else {
          const counts = {
            created: result.create_count,
            overwritten: result.overwrites.length,
          };
          showNotification(
            "success",
            t("favoritePrompts.title"),
            result.new_categories.length > 0
              ? t("favoritePrompts.transfer.importDoneWithCategories", {
                  ...counts,
                  names: result.new_categories.join(
                    t("favoritePrompts.transfer.listSeparator"),
                  ),
                })
              : t("favoritePrompts.transfer.importDone", counts),
          );
        }
        return result;
      } catch (err) {
        reportError(t("favoritePrompts.transfer.importFailed"), err);
        return null;
      }
    },
    [reportError, showNotification, t],
  );

  const value = useMemo<FavoritePromptContextValue>(
    () => ({
      prompts: state.prompts,
      categories: state.categories,
      loaded: state.loaded,
      loading: state.loading,
      dialog: state.dialog,
      openPicker,
      openSaveDialog,
      closeDialog,
      insertPrompt,
      ensureLoaded,
      createPrompt,
      updatePrompt,
      deletePrompt,
      movePrompt,
      createCategory,
      updateCategory,
      deleteCategory,
      exportPrompts,
      previewImport,
      importPrompts,
    }),
    [
      state,
      openPicker,
      openSaveDialog,
      closeDialog,
      insertPrompt,
      ensureLoaded,
      createPrompt,
      updatePrompt,
      deletePrompt,
      movePrompt,
      createCategory,
      updateCategory,
      deleteCategory,
      exportPrompts,
      previewImport,
      importPrompts,
    ],
  );

  return (
    <FavoritePromptContext.Provider value={value}>
      {children}
    </FavoritePromptContext.Provider>
  );
}

export function useFavoritePrompts(): FavoritePromptContextValue {
  const context = useContext(FavoritePromptContext);
  if (!context) {
    throw new Error(
      "useFavoritePrompts must be used within a FavoritePromptProvider",
    );
  }
  return context;
}
