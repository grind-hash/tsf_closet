/**
 * 新しい設定画面の左ナビ（設定項目の検索欄とカテゴリ一覧）
 */

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  SETTINGS_CATEGORIES,
  type SettingsCategoryId,
} from "./settingsSearchIndex";

/** 文字を入力しない input（"/" を入力として扱わない対象から外す） */
const NON_TEXT_INPUT_TYPES = new Set([
  "button",
  "checkbox",
  "color",
  "file",
  "image",
  "radio",
  "range",
  "reset",
  "submit",
]);

function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  ) {
    return true;
  }
  if (target instanceof HTMLInputElement) {
    return !NON_TEXT_INPUT_TYPES.has(target.type);
  }
  return false;
}

/** ダイアログを開いている間は、背面の検索欄へフォーカスを移さない */
function isDialogOpen(): boolean {
  return (
    document.querySelector(
      'dialog[open], [role="dialog"], [role="alertdialog"]',
    ) !== null
  );
}

interface SettingsNavProps {
  query: string;
  onQueryChange: (query: string) => void;
  activeCategory: SettingsCategoryId;
  onSelectCategory: (category: SettingsCategoryId) => void;
  /** 検索中のカテゴリ別一致件数。検索していないときは null */
  matchCounts: ReadonlyMap<SettingsCategoryId, number> | null;
}

export default function SettingsNav({
  query,
  onQueryChange,
  activeCategory,
  onSelectCategory,
  matchCounts,
}: SettingsNavProps) {
  const { t } = useTranslation();
  const activeButtonRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // 開いた時点で選択中のカテゴリへフォーカスを移す
  useEffect(() => {
    activeButtonRef.current?.focus({ preventScroll: true });
  }, []);

  // "/"（文字入力中以外）と Ctrl+K / Cmd+K で検索欄へ移る
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey) return;
      const isModK =
        (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      const isSlash =
        event.key === "/" &&
        !event.ctrlKey &&
        !event.metaKey &&
        !isTextEntryTarget(event.target);
      if (!isModK && !isSlash) return;
      if (isDialogOpen()) return;
      event.preventDefault();
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isSearching = matchCounts !== null;

  return (
    <nav
      className="settings-v2__nav"
      aria-label={t("settings.categoryNavLabel")}
    >
      <div className="settings-v2__search">
        <label className="settings-v2__search-label" htmlFor="settings-search">
          <span className="settings-v2__search-icon" aria-hidden="true">
            🔍
          </span>
          <input
            ref={searchInputRef}
            id="settings-search"
            type="search"
            className="settings-v2__search-input"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && query) {
                e.preventDefault();
                onQueryChange("");
              }
            }}
            placeholder={t("settings.searchPlaceholder")}
            aria-label={t("settings.searchAria")}
            aria-keyshortcuts="/ Control+K Meta+K"
            autoComplete="off"
            spellCheck={false}
          />
          {!query && (
            <span className="settings-v2__search-kbd" aria-hidden="true">
              /
            </span>
          )}
        </label>
        {query && (
          <button
            type="button"
            className="settings-v2__search-clear"
            onClick={() => onQueryChange("")}
            aria-label={t("settings.searchClear")}
          >
            ×
          </button>
        )}
      </div>

      <ul className="settings-v2__categories">
        {SETTINGS_CATEGORIES.map((category) => {
          const isActive = !isSearching && category.id === activeCategory;
          const count = matchCounts?.get(category.id) ?? 0;
          const className = [
            "settings-v2__category",
            isActive ? "is-active" : "",
            isSearching && count === 0 ? "is-empty" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <li key={category.id}>
              <button
                type="button"
                ref={
                  category.id === activeCategory ? activeButtonRef : undefined
                }
                className={className}
                aria-current={isActive ? "page" : undefined}
                onClick={() => onSelectCategory(category.id)}
              >
                <span className="settings-v2__category-label">
                  {t(category.titleKey)}
                </span>
                {isSearching && (
                  <span className="settings-v2__category-count">{count}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
