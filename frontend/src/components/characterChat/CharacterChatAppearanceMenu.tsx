import { useTranslation } from "react-i18next";

interface CharacterChatAppearanceMenuProps {
  open: boolean;
  onToggleOpen: () => void;
  /** 姿の差し替え・描き直し・送信中は操作を止める */
  busy: boolean;
  canReset: boolean;
  generatePortrait: boolean;
  onGeneratePortraitChange: (next: boolean) => void;
  onChangeAppearance: () => void;
  onRegenerate: () => void;
  onReset: () => void;
}

/**
 * 「姿」ボタンとポップオーバー。姿を変更 / 立ち絵を描き直す / 最初の姿に戻す と、
 * セッションの画像を選んだときに立ち絵を生成するかの好み。
 */
export default function CharacterChatAppearanceMenu({
  open,
  onToggleOpen,
  busy,
  canReset,
  generatePortrait,
  onGeneratePortraitChange,
  onChangeAppearance,
  onRegenerate,
  onReset,
}: CharacterChatAppearanceMenuProps) {
  const { t } = useTranslation();
  return (
    <div className="character-chat__sound">
      <button
        type="button"
        className={`character-chat-room__action${open ? " is-on" : ""}`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={onToggleOpen}
      >
        {t("characterChat.room.appearanceMenu")}
      </button>
      {open && (
        <div className="character-chat__popover character-chat-room__menu">
          <button
            type="button"
            className="character-chat-room__menu-item"
            disabled={busy}
            onClick={onChangeAppearance}
          >
            <strong>{t("characterChat.room.changeAppearance")}</strong>
          </button>
          <button
            type="button"
            className="character-chat-room__menu-item"
            disabled={busy}
            onClick={onRegenerate}
          >
            <strong>{t("characterChat.room.regeneratePortrait")}</strong>
            <small>{t("characterChat.room.regeneratePortraitHint")}</small>
          </button>
          <button
            type="button"
            className="character-chat-room__menu-item"
            disabled={busy || !canReset}
            onClick={onReset}
          >
            <strong>{t("characterChat.room.resetAppearance")}</strong>
            <small>
              {t(
                canReset
                  ? "characterChat.room.resetAppearanceHint"
                  : "characterChat.room.resetAppearanceUnavailable",
              )}
            </small>
          </button>
          <label className="character-chat__switch-row">
            <span className="character-chat__switch-info">
              <strong>{t("characterChat.hub.generatePortraitToggle")}</strong>
              <small>{t("characterChat.hub.generatePortraitToggleHint")}</small>
            </span>
            <input
              type="checkbox"
              className="character-chat__switch-input"
              checked={generatePortrait}
              onChange={(event) =>
                onGeneratePortraitChange(event.target.checked)
              }
            />
            <span className="character-chat__switch" />
          </label>
        </div>
      )}
    </div>
  );
}
