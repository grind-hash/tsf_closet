import { type ReactNode, useState } from "react";
import { readStorage, writeStorage } from "../../utils/storage";

interface MakerSectionProps {
  /** 開閉状態を覚えるときの節の ID */
  id: string;
  /** 開閉状態を保存する localStorage のキー(画面ごとに分ける) */
  storageKey: string;
  title: string;
  /** 見出しの右端に置く操作(開いているときだけ出す) */
  action?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

function readOpenMap(storageKey: string): Record<string, boolean> {
  try {
    const parsed: unknown = JSON.parse(
      readStorage("local", storageKey) ?? "{}",
    );
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, boolean>)
      : {};
  } catch {
    return {};
  }
}

/**
 * キャラクター設定の節。見出しで開閉し、開閉状態を localStorage に保存する。
 * 同じキーを複数の節で共有するため、書き込みのたびに保存済みの値を読み直す
 */
export default function MakerSection({
  id,
  storageKey,
  title,
  action,
  defaultOpen = true,
  children,
}: MakerSectionProps) {
  const [open, setOpen] = useState(
    () => readOpenMap(storageKey)[id] ?? defaultOpen,
  );
  const toggle = () => {
    const next = !open;
    setOpen(next);
    writeStorage(
      "local",
      storageKey,
      JSON.stringify({ ...readOpenMap(storageKey), [id]: next }),
    );
  };
  return (
    <section className="character-maker__section">
      <div className="character-maker__section-head">
        <button
          type="button"
          className="character-maker__section-toggle"
          aria-expanded={open}
          onClick={toggle}
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          {title}
        </button>
        {action && open && (
          <div className="character-maker__section-action">{action}</div>
        )}
      </div>
      {open && <div className="character-maker__section-body">{children}</div>}
    </section>
  );
}
