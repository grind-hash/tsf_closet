/**
 * 設定画面の項目・セクションの表示制御。
 *
 * 従来の画面（classic）では、今までと同じ DOM をそのまま出す。
 * 新しい画面（v2）では、選択中のカテゴリと検索結果に合わせて出し分ける。
 */

import { createContext, type ReactNode, useContext } from "react";
import {
  SETTINGS_ITEMS,
  type SettingsCategoryId,
  type SettingsItemId,
} from "./settingsSearchIndex";

export interface SettingsViewState {
  mode: "classic" | "v2";
  activeCategory: SettingsCategoryId;
  /** 検索に一致した項目。検索していないときは null */
  matchedIds: ReadonlySet<SettingsItemId> | null;
  /** 現在の設定・環境では表示しない項目 */
  unavailableIds: ReadonlySet<SettingsItemId>;
}

const DEFAULT_VIEW: SettingsViewState = {
  mode: "classic",
  activeCategory: "game",
  matchedIds: null,
  unavailableIds: new Set(),
};

export const SettingsViewContext =
  createContext<SettingsViewState>(DEFAULT_VIEW);

function isCategoryVisible(
  view: SettingsViewState,
  category: SettingsCategoryId,
): boolean {
  if (view.mode === "classic") return true;
  const { matchedIds } = view;
  if (matchedIds === null) return category === view.activeCategory;
  return SETTINGS_ITEMS.some(
    (item) => item.category === category && matchedIds.has(item.id),
  );
}

interface SettingsSectionProps {
  category: SettingsCategoryId;
  /** 見出し（h2）の中身 */
  title: ReactNode;
  /** 追加の修飾クラス */
  className?: string;
  children: ReactNode;
}

export function SettingsSection({
  category,
  title,
  className,
  children,
}: SettingsSectionProps) {
  const view = useContext(SettingsViewContext);
  if (!isCategoryVisible(view, category)) return null;
  return (
    <section
      className={
        className
          ? `settings-screen__section ${className}`
          : "settings-screen__section"
      }
    >
      <h2 className="settings-screen__section-title">{title}</h2>
      {children}
    </section>
  );
}

interface CollapsibleSettingsSectionProps {
  category: SettingsCategoryId;
  /** 見出しの中身（開閉ボタンの中に入る） */
  title: ReactNode;
  /** 見出しに添える要約。null なら出さない */
  summary: ReactNode | null;
  open: boolean;
  onToggle: () => void;
  bodyId: string;
  toggleTestId: string;
  children: ReactNode;
}

/**
 * 開閉できるセクション（3Dモデル・Live2D）。
 * classic では閉じている間も中身を DOM に残す（hidden）。
 * v2 ではカテゴリが1ページになるため、常に開いた状態で出す。
 */
export function CollapsibleSettingsSection({
  category,
  title,
  summary,
  open,
  onToggle,
  bodyId,
  toggleTestId,
  children,
}: CollapsibleSettingsSectionProps) {
  const view = useContext(SettingsViewContext);
  if (!isCategoryVisible(view, category)) return null;
  const summaryNode = summary !== null && (
    <span className="settings-screen__section-summary">{summary}</span>
  );

  if (view.mode === "v2") {
    return (
      <section className="settings-screen__section">
        <h2 className="settings-screen__section-title">
          {title}
          {summaryNode}
        </h2>
        <div id={bodyId}>{children}</div>
      </section>
    );
  }

  return (
    <section
      className={`settings-screen__section settings-screen__section--collapsible${
        open ? " is-open" : " is-collapsed"
      }`}
    >
      <h2 className="settings-screen__section-title">
        <button
          type="button"
          className="settings-screen__section-toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          data-testid={toggleTestId}
          onClick={onToggle}
        >
          <span className="settings-screen__section-chevron" aria-hidden>
            ▾
          </span>
          {title}
          {summaryNode}
        </button>
      </h2>
      <div id={bodyId} hidden={!open}>
        {children}
      </div>
    </section>
  );
}

interface SettingsItemProps {
  id: SettingsItemId;
  children: ReactNode;
}

/** 設定項目。中身はそのまま出し、表示しない場合は何も出さない */
export function SettingsItem({ id, children }: SettingsItemProps) {
  const view = useContext(SettingsViewContext);
  if (view.unavailableIds.has(id)) return null;
  if (
    view.mode === "v2" &&
    view.matchedIds !== null &&
    !view.matchedIds.has(id)
  ) {
    return null;
  }
  return children;
}
