/**
 * お気に入りプロンプトのダイアログ本体。
 *
 * 1 枚のパネルの中で「一覧 / プロンプト編集 / カテゴリー編集」を切り替える。
 * 他のモーダル（キャスト編集・画像タグ編集など）の上に重なるため、キー入力は window の
 * capture 段で受け取り、親モーダルや背後の画面のショートカットまで届かないようにする。
 */

import { useCallback, useEffect, useId, useState } from "react";
import type {
  FavoritePrompt,
  FavoritePromptCategory,
} from "../../apis/favoritePrompts";
import { useFavoritePrompts } from "../../contexts/FavoritePromptContext";
import FavoritePromptCategoryForm from "./FavoritePromptCategoryForm";
import FavoritePromptForm from "./FavoritePromptForm";
import FavoritePromptList from "./FavoritePromptList";
import "./FavoritePromptDialog.css";

type View =
  | { kind: "list" }
  | { kind: "prompt"; prompt: FavoritePrompt | null; initialContent?: string }
  | { kind: "category"; category: FavoritePromptCategory | null };

export default function FavoritePromptDialog() {
  const { dialog, closeDialog, ensureLoaded } = useFavoritePrompts();
  const titleId = useId();
  const saveMode = dialog.kind === "save";
  const [view, setView] = useState<View>(() =>
    dialog.kind === "save"
      ? { kind: "prompt", prompt: null, initialContent: dialog.content }
      : { kind: "list" },
  );
  const [childOpen, setChildOpen] = useState(false);

  useEffect(() => {
    void ensureLoaded();
  }, [ensureLoaded]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // 背後の画面のキー操作（親モーダルの Escape、TSFシナリオの数字キー選択や
      // L/H/M など）まで届かないよう、開いている間はすべてここで止める。
      // 文字入力・Tab 移動・Enter 送信は既定動作なので影響しない。
      event.stopPropagation();
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (!childOpen) closeDialog();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [childOpen, closeDialog]);

  // 保存ボタンから開いたときはフォームを閉じたらダイアログごと閉じる
  const leaveForm = useCallback(() => {
    if (saveMode) closeDialog();
    else setView({ kind: "list" });
  }, [saveMode, closeDialog]);

  return (
    <div
      className="favorite-prompts-overlay"
      onMouseDown={(event) => {
        // 入力途中のフォームは背景クリックで閉じない
        if (event.currentTarget === event.target && view.kind === "list") {
          closeDialog();
        }
      }}
    >
      <section
        className="favorite-prompts"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {view.kind === "list" && (
          <FavoritePromptList
            titleId={titleId}
            onClose={closeDialog}
            onAddPrompt={() => setView({ kind: "prompt", prompt: null })}
            onAddCategory={() => setView({ kind: "category", category: null })}
            onEditPrompt={(prompt) => setView({ kind: "prompt", prompt })}
            onEditCategory={(category) =>
              setView({ kind: "category", category })
            }
          />
        )}
        {view.kind === "prompt" && (
          <FavoritePromptForm
            titleId={titleId}
            prompt={view.prompt}
            initialContent={view.initialContent}
            onDone={leaveForm}
            onCancel={leaveForm}
            onChildOpenChange={setChildOpen}
          />
        )}
        {view.kind === "category" && (
          <FavoritePromptCategoryForm
            titleId={titleId}
            category={view.category}
            onDone={leaveForm}
            onCancel={leaveForm}
            onChildOpenChange={setChildOpen}
          />
        )}
      </section>
    </div>
  );
}
