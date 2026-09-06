import { useTranslation } from "react-i18next";
import type { CharacterChatAdventureInfo } from "../../apis/characterChat";

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
  /** adventure 種: run の画像を使う切り替えと、場面画像から描く操作 */
  adventure?: CharacterChatAdventureInfo | null;
  onAdventureMode?: (mode: "default" | "partner_portrait" | "scene") => void;
  onRedrawFromScene?: () => void;
  /** NovelAI のときだけ精密参照(Anlas 消費)の選択を出す */
  preciseAvailable?: boolean;
  usePrecise?: boolean;
  onUsePreciseChange?: (next: boolean) => void;
}

/**
 * 「姿」ボタンとポップオーバー。姿を変更 / 立ち絵を描き直す / 最初の姿に戻す と、
 * セッションの画像を選んだときに立ち絵を生成するかの好み。adventure 種では
 * run の画像(攻略対象の立ち絵 / 場面の画像)への切り替えと場面画像からの描き直しが加わる。
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
  adventure,
  onAdventureMode,
  onRedrawFromScene,
  preciseAvailable = false,
  usePrecise = false,
  onUsePreciseChange,
}: CharacterChatAppearanceMenuProps) {
  const { t } = useTranslation();
  const isAdventure = Boolean(adventure);
  const mode = adventure?.appearance_mode ?? "default";
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
          {isAdventure && adventure && (
            <>
              {adventure.available ? (
                <>
                  <button
                    type="button"
                    className="character-chat-room__menu-item"
                    disabled={busy || mode === "default"}
                    onClick={() => onAdventureMode?.("default")}
                  >
                    <strong>{t("characterChat.room.adventureFollow")}</strong>
                    <small>{t("characterChat.room.adventureFollowHint")}</small>
                  </button>
                  <button
                    type="button"
                    className="character-chat-room__menu-item character-chat-room__menu-item--thumb"
                    disabled={
                      busy ||
                      !adventure.partner_portrait_url ||
                      mode === "partner_portrait"
                    }
                    onClick={() => onAdventureMode?.("partner_portrait")}
                  >
                    {adventure.partner_portrait_url ? (
                      <img
                        className="character-chat-room__menu-thumb"
                        src={adventure.partner_portrait_url}
                        alt=""
                      />
                    ) : (
                      <span
                        className="character-chat-room__menu-thumb"
                        aria-hidden
                      />
                    )}
                    <span>
                      <strong>
                        {t("characterChat.room.adventureUsePartnerPortrait")}
                      </strong>
                      {!adventure.partner_portrait_url && (
                        <small>
                          {t("characterChat.room.adventureNoImage")}
                        </small>
                      )}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="character-chat-room__menu-item character-chat-room__menu-item--thumb"
                    disabled={
                      busy || !adventure.scene_image_url || mode === "scene"
                    }
                    onClick={() => onAdventureMode?.("scene")}
                  >
                    {adventure.scene_image_url ? (
                      <img
                        className="character-chat-room__menu-thumb"
                        src={adventure.scene_image_url}
                        alt=""
                      />
                    ) : (
                      <span
                        className="character-chat-room__menu-thumb"
                        aria-hidden
                      />
                    )}
                    <span>
                      <strong>
                        {t("characterChat.room.adventureUseScene")}
                      </strong>
                      {!adventure.scene_image_url && (
                        <small>
                          {t("characterChat.room.adventureNoImage")}
                        </small>
                      )}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="character-chat-room__menu-item"
                    disabled={busy || !adventure.scene_image_url}
                    onClick={onRedrawFromScene}
                  >
                    <strong>
                      {t("characterChat.room.adventureRedrawFromScene")}
                    </strong>
                    <small>
                      {t("characterChat.room.adventureRedrawFromSceneHint")}
                    </small>
                  </button>
                  {preciseAvailable && (
                    <label className="character-chat__switch-row">
                      <span className="character-chat__switch-info">
                        <strong>
                          {t("characterChat.room.adventurePreciseToggle")}
                        </strong>
                        <small>
                          {t("characterChat.room.adventurePreciseHint")}
                        </small>
                      </span>
                      <input
                        type="checkbox"
                        className="character-chat__switch-input"
                        checked={usePrecise}
                        onChange={(event) =>
                          onUsePreciseChange?.(event.target.checked)
                        }
                      />
                      <span className="character-chat__switch" />
                    </label>
                  )}
                </>
              ) : (
                <p className="character-chat-room__menu-note">
                  {t("characterChat.room.adventureUnavailable")}
                </p>
              )}
              <hr className="character-chat-room__menu-divider" />
            </>
          )}
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
          {!isAdventure && (
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
          )}
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
