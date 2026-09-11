import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AvatarModel, listAvatarModels } from "../../apis/avatars";
import type {
  CharacterChatAdventureInfo,
  CharacterChatAvatarInfo,
  CharacterChatAvatarMode,
} from "../../apis/characterChat";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { live2dCoreAvailable } from "./live2d/cubismPilotRenderer";

/** 登録済みモデルの表示名(分類済みなら「キャラクター / 差分」) */
function avatarModelLabel(model: AvatarModel): string {
  if (!model.character_name) return model.name;
  return `${model.character_name} / ${model.variant_label ?? model.name}`;
}

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
  /** 3D モデル(VRM)の解決結果と切り替え(自動 / 2D 立ち絵 / 登録済みモデル) */
  avatar?: CharacterChatAvatarInfo | null;
  onAvatarChange?: (
    mode: CharacterChatAvatarMode,
    avatarId?: string | null,
  ) => void;
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
  avatar,
  onAvatarChange,
  adventure,
  onAdventureMode,
  onRedrawFromScene,
  preciseAvailable = false,
  usePrecise = false,
  onUsePreciseChange,
}: CharacterChatAppearanceMenuProps) {
  const { t } = useTranslation();
  const { activeThread, setAvatar, promptPreviewEnabled } = useCharacterChat();
  const isAdventure = Boolean(adventure);
  const mode = adventure?.appearance_mode ?? "default";
  const avatarMode = avatar?.mode ?? "auto";
  // Cubism Core は同梱しない。未配置なら Live2D は選べないので、判定できるまでは
  // 押せない状態にしておく(判定前は null)
  const [coreAvailable, setCoreAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    if (!open || coreAvailable !== null) return;
    let cancelled = false;
    void live2dCoreAvailable().then((available) => {
      if (!cancelled) setCoreAvailable(available);
    });
    return () => {
      cancelled = true;
    };
  }, [open, coreAvailable]);
  // 登録済みモデルの一覧は、メニューを最初に開いたときに 1 回だけ取る
  const [models, setModels] = useState<AvatarModel[] | null>(null);
  const [modelsFailed, setModelsFailed] = useState(false);
  useEffect(() => {
    if (!open || models !== null) return;
    let cancelled = false;
    listAvatarModels()
      .then((items) => {
        if (cancelled) return;
        setModels(
          [...items].sort((a, b) =>
            avatarModelLabel(a).localeCompare(avatarModelLabel(b), "ja"),
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setModelsFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, models]);
  const avatarSourceLabel =
    avatar?.source === "bundled"
      ? t("characterChat.room.avatarSourceBundled")
      : avatar?.source === "run"
        ? t("characterChat.room.avatarSourceRun")
        : avatar?.source === "registered"
          ? t("characterChat.room.avatarSourceRegistered")
          : "";
  const avatarCurrentLabel =
    avatarMode === "live2d"
      ? t("characterChat.room.avatarLive2d")
      : avatar?.url
        ? t("characterChat.room.avatarCurrent", {
            name: avatar.name ?? "",
            source: avatarSourceLabel,
          })
        : t("characterChat.room.avatarCurrentNone");
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
          <p className="character-chat-room__menu-heading">
            {t("characterChat.room.avatarSection")}
          </p>
          <p className="character-chat-room__menu-note">{avatarCurrentLabel}</p>
          {activeThread?.kind === "base" && (
            <button
              type="button"
              className={`character-chat-room__menu-item${avatarMode === "live2d" ? " is-active" : ""}`}
              aria-pressed={avatarMode === "live2d"}
              disabled={busy || !coreAvailable}
              onClick={() => {
                onToggleOpen();
                void setAvatar("live2d");
              }}
            >
              <strong>{t("characterChat.room.avatarLive2d")}</strong>
              <small>
                {coreAvailable === false
                  ? t("characterChat.room.avatarLive2dUnavailable")
                  : t("characterChat.room.avatarLive2dHint")}
              </small>
              {/* 開発者向け。ENABLE_PROMPT_PREVIEW のときだけ配置先を出す */}
              {coreAvailable === false && promptPreviewEnabled && (
                <>
                  <small>{t("characterChat.room.live2dSdkPathPackaged")}</small>
                  <small>{t("characterChat.room.live2dSdkPathDev")}</small>
                </>
              )}
            </button>
          )}
          <button
            type="button"
            className={`character-chat-room__menu-item${avatarMode === "auto" ? " is-active" : ""}`}
            aria-pressed={avatarMode === "auto"}
            disabled={busy}
            onClick={() => onAvatarChange?.("auto")}
          >
            <strong>{t("characterChat.room.avatarAuto")}</strong>
            <small>{t("characterChat.room.avatarAutoHint")}</small>
          </button>
          <button
            type="button"
            className={`character-chat-room__menu-item${avatarMode === "none" ? " is-active" : ""}`}
            aria-pressed={avatarMode === "none"}
            disabled={busy}
            onClick={() => onAvatarChange?.("none")}
          >
            <strong>{t("characterChat.room.avatarNone")}</strong>
          </button>
          <p className="character-chat-room__menu-heading character-chat-room__menu-heading--sub">
            {t("characterChat.room.avatarRegistered")}
          </p>
          {modelsFailed ? (
            <p className="character-chat-room__menu-note">
              {t("characterChat.room.avatarRegisteredFailed")}
            </p>
          ) : models === null ? (
            <p className="character-chat-room__menu-note">
              {t("characterChat.room.avatarRegisteredLoading")}
            </p>
          ) : models.length === 0 ? (
            <p className="character-chat-room__menu-note">
              {t("characterChat.room.avatarRegisteredEmpty")}
            </p>
          ) : (
            <div className="character-chat-room__menu-models">
              {models.map((model) => {
                const chosen =
                  avatarMode === "model" && avatar?.id === model.id;
                const shown = avatar?.id === model.id;
                return (
                  <button
                    key={model.id}
                    type="button"
                    className={`character-chat-room__menu-item${chosen ? " is-active" : ""}`}
                    aria-pressed={chosen}
                    disabled={busy}
                    onClick={() => onAvatarChange?.("model", model.id)}
                  >
                    <strong>{avatarModelLabel(model)}</strong>
                    {shown && !chosen && avatarSourceLabel && (
                      <small>{avatarSourceLabel}</small>
                    )}
                  </button>
                );
              })}
            </div>
          )}
          <hr className="character-chat-room__menu-divider" />
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
