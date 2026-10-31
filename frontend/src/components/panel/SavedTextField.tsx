/**
 * SavedTextField - 入力値をローカルに持ち、blur とアンマウントで保存するテキスト欄。
 *
 * IME 変換が途切れないよう保存は確定時だけ行い、欄の右に保存状態を出す。
 * 登場人物の設定（CharacterDetailEditor）とキャラクター画面で共用する。
 */

import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useInsertAtCaret } from "../../hooks/useInsertAtCaret";
import {
  FavoritePromptInsertButton,
  FavoritePromptSaveButton,
} from "../favoritePrompts/FavoritePromptButtons";
import "./CharacterPanel.css";
import "./CharacterCastModal.css";

export type SaveStatus = "saved" | "saving" | "dirty" | "error";

// ---------------------------------------------------------------------------
// 保存状態の表示
// ---------------------------------------------------------------------------

export function SaveStatusIcon({ status }: { status: SaveStatus }) {
  const { t } = useTranslation();
  const label = t(`character.save_status.${status}`);
  const icon =
    status === "saving"
      ? "…"
      : status === "dirty"
        ? "●"
        : status === "error"
          ? "!"
          : "✓";
  return (
    <span
      className={`character-panel__save-status character-panel__save-status--${status}`}
      role="status"
      aria-live="polite"
      aria-label={label}
      title={label}
    >
      <span className="character-panel__save-status-icon" aria-hidden="true">
        {icon}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// テキスト欄（blur とアンマウントで保存）
// ---------------------------------------------------------------------------

export interface SavedTextFieldProps {
  label: string;
  value: string;
  onSave: (next: string) => Promise<void>;
  multiline?: boolean;
  placeholder?: string;
  maxLength?: number;
  /** 欄の右上に置く操作 */
  action?: ReactNode;
  testId?: string;
  /** 入力中の値を親へ知らせる（保存前の下書きを使う操作のため） */
  onTextChange?: (text: string) => void;
  /** お気に入りプロンプトの挿入 / 保存ボタンを欄の右上に出す */
  favoritePrompt?: boolean;
  /** 複数行の欄の高さ（行数） */
  rows?: number;
  /** 欄の下に出す説明 */
  hint?: ReactNode;
}

export default function SavedTextField({
  label,
  value,
  onSave,
  multiline = false,
  placeholder,
  maxLength,
  action,
  testId,
  onTextChange,
  favoritePrompt = false,
  rows,
  hint,
}: SavedTextFieldProps) {
  const [text, setText] = useState(value);
  const fieldRef = useRef<HTMLTextAreaElement & HTMLInputElement>(null);
  const [status, setStatus] = useState<SaveStatus>("saved");

  // 外から値が変わった（再生成・姿の選択など）とき、編集中でなければ取り込む
  const syncedRef = useRef(value);
  useEffect(() => {
    const synced = syncedRef.current;
    if (value !== synced) {
      setText((prev) => (prev === synced ? value : prev));
      syncedRef.current = value;
    }
  }, [value]);

  const textRef = useRef(text);
  textRef.current = text;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;

  const save = useCallback(async (next: string) => {
    setStatus("saving");
    try {
      await onSaveRef.current(next);
      setStatus("saved");
    } catch (err) {
      console.error("Failed to save character field", err);
      setStatus("error");
    }
  }, []);

  // 人物の切り替え・モーダルを閉じたときは blur が起きないため、ここで保存する
  useEffect(
    () => () => {
      if (textRef.current !== syncedRef.current) {
        void onSaveRef
          .current(textRef.current)
          .catch((err) =>
            console.error("Failed to flush character field", err),
          );
      }
    },
    [],
  );

  const handleBlur = () => {
    if (text !== syncedRef.current) {
      void save(text);
    } else {
      setStatus("saved");
    }
  };

  const handleChange = (next: string) => {
    setText(next);
    setStatus(next === syncedRef.current ? "saved" : "dirty");
    onTextChange?.(next);
  };

  // 挿入後は欄へフォーカスが戻るため、保存は通常どおり blur / アンマウントで行われる
  const insertFavoritePrompt = useInsertAtCaret(fieldRef, text, handleChange);

  return (
    <div className="character-cast__field">
      <div className="character-cast__field-head">
        <span className="character-cast__field-label">{label}</span>
        <SaveStatusIcon status={status} />
        {(favoritePrompt || action) && (
          <div className="character-cast__field-action">
            {favoritePrompt && (
              <>
                <FavoritePromptInsertButton onInsert={insertFavoritePrompt} />
                <FavoritePromptSaveButton text={text} />
              </>
            )}
            {action}
          </div>
        )}
      </div>
      {multiline ? (
        <textarea
          ref={fieldRef}
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          maxLength={maxLength}
          rows={rows}
          aria-label={label}
          data-testid={testId}
        />
      ) : (
        <input
          ref={fieldRef}
          type="text"
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          maxLength={maxLength}
          aria-label={label}
          data-testid={testId}
        />
      )}
      {hint && <p className="character-cast__hint">{hint}</p>}
    </div>
  );
}
