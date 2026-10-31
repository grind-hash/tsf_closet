import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AVATAR_EXPRESSIONS,
  AVATAR_FRAMINGS,
  AVATAR_GESTURES,
  type AvatarExpressionKey,
  type AvatarGestureKey,
} from "../../constants/companionAvatar";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { useAvatarFraming } from "../../hooks/useAvatarViewPreferences";

/** ステージに出しているものの種類。種類ごとに試せる操作が変わる */
export type CharacterChatStageKind = "vrm" | "live2d" | "portrait";

/** Live2D(案内役)が持つ表情。残りは neutral として描かれる */
const LIVE2D_EXPRESSIONS: ReadonlySet<AvatarExpressionKey> = new Set([
  "neutral",
  "happy",
  "angry",
  "sad",
]);

const PREVIEW_GESTURES = AVATAR_GESTURES.filter((key) => key !== "idle");

/** 2D 立ち絵の表情差分を描ける表情(neutral はいまの立ち絵そのもの) */
const PORTRAIT_EXPRESSIONS = AVATAR_EXPRESSIONS.filter(
  (key) => key !== "neutral",
);

interface CharacterChatExpressionMenuProps {
  open: boolean;
  onToggleOpen: () => void;
  stageKind: CharacterChatStageKind;
  /** 読み込んだ 3D モデルに無いプリセット表情(0.x の surprised など) */
  missingExpressions: readonly string[];
  onPlayGesture: (gesture: AvatarGestureKey) => void;
  /** 2D 立ち絵: いまの立ち絵から作った表情差分({表情: URL}) */
  expressionPortraits: Readonly<Record<string, string>>;
  /** 2D 立ち絵: 表情差分の元にする立ち絵があるか */
  portraitAvailable: boolean;
  /** NovelAI のときだけ精密参照(Anlas 消費)の選択を出す */
  preciseAvailable: boolean;
  /** 表情差分を描く(精密参照の確認は呼び出し側で挟む) */
  onGenerateExpressions: (expressions: string[], usePrecise: boolean) => void;
}

/**
 * 「表情」ボタンとポップオーバー。チャットで指示しなくても、カメラの寄り・表情・
 * しぐさをその場で試せる。選んだ表情は次の返答が届くか「戻す」まで保つ。
 */
export default function CharacterChatExpressionMenu({
  open,
  onToggleOpen,
  stageKind,
  missingExpressions,
  onPlayGesture,
  expressionPortraits,
  portraitAvailable,
  preciseAvailable,
  onGenerateExpressions,
}: CharacterChatExpressionMenuProps) {
  const { t } = useTranslation();
  const { expressionPreview, setExpressionPreview, expressionProgress } =
    useCharacterChat();
  const [framing, setFraming] = useAvatarFraming();
  const vrm = stageKind === "vrm";
  const portrait = stageKind === "portrait";
  const hasVariants = Object.keys(expressionPortraits).length > 0;
  const expressionUsable = (key: AvatarExpressionKey) =>
    stageKind === "live2d"
      ? LIVE2D_EXPRESSIONS.has(key)
      : portrait
        ? key === "neutral" || key in expressionPortraits
        : !missingExpressions.includes(key);
  // 描く表情の選択。既定はまだ差分が無い表情
  const [selected, setSelected] = useState<string[] | null>(null);
  const chosen =
    selected ??
    PORTRAIT_EXPRESSIONS.filter((key) => !(key in expressionPortraits));
  const [usePrecise, setUsePrecise] = useState(false);
  const toggleChosen = (key: string) =>
    setSelected(
      chosen.includes(key)
        ? chosen.filter((item) => item !== key)
        : [...chosen, key],
    );
  const expressionNote = portrait
    ? hasVariants
      ? t("characterChat.room.expressionPortraitVariantsNote")
      : t("characterChat.room.expressionPortraitNote")
    : stageKind === "live2d"
      ? t("characterChat.room.expressionLive2dNote")
      : missingExpressions.length > 0
        ? t("characterChat.room.expressionMissingNote")
        : t("characterChat.room.expressionHint");

  return (
    <div className="character-chat__sound">
      <button
        type="button"
        className={`character-chat-room__action${open ? " is-on" : ""}${
          expressionPreview ? " has-preview" : ""
        }`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={onToggleOpen}
      >
        {t("characterChat.room.expressionMenu")}
      </button>
      {open && (
        <div className="character-chat__popover character-chat-room__menu">
          <p className="character-chat-room__menu-heading">
            {t("characterChat.room.cameraHeading")}
          </p>
          <fieldset
            className="character-chat__segments"
            aria-label={t("characterChat.room.cameraHeading")}
          >
            {AVATAR_FRAMINGS.map((key) => (
              <button
                key={key}
                type="button"
                className={framing === key ? "is-active" : undefined}
                aria-pressed={framing === key}
                disabled={!vrm}
                onClick={() => setFraming(key)}
              >
                {t(`characterChat.room.cameraFramings.${key}`)}
              </button>
            ))}
          </fieldset>
          {!vrm && (
            <p className="character-chat-room__menu-note">
              {stageKind === "live2d"
                ? t("characterChat.room.cameraLive2dNote")
                : t("characterChat.room.cameraPortraitNote")}
            </p>
          )}

          <div className="character-chat-room__menu-heading-row">
            <p className="character-chat-room__menu-heading">
              {t("characterChat.room.expressionHeading")}
            </p>
            <button
              type="button"
              className="character-chat-room__menu-link"
              disabled={expressionPreview === null}
              onClick={() => setExpressionPreview(null)}
            >
              {t("characterChat.room.expressionReset")}
            </button>
          </div>
          <div className="character-chat__preview-chips">
            {AVATAR_EXPRESSIONS.map((key) => {
              const active = expressionPreview === key;
              return (
                <button
                  key={key}
                  type="button"
                  className={`character-chat__preview-chip${active ? " is-active" : ""}`}
                  aria-pressed={active}
                  disabled={!expressionUsable(key)}
                  onClick={() => setExpressionPreview(key)}
                >
                  {t(`settings.avatar.expressions.${key}`)}
                </button>
              );
            })}
          </div>
          <p className="character-chat-room__menu-note">{expressionNote}</p>

          <p className="character-chat-room__menu-heading">
            {t("characterChat.room.gestureHeading")}
          </p>
          <div className="character-chat__preview-chips">
            {PREVIEW_GESTURES.map((key) => (
              <button
                key={key}
                type="button"
                className="character-chat__preview-chip"
                disabled={!vrm}
                onClick={() => onPlayGesture(key)}
              >
                {t(`settings.avatar.gestures.${key}`)}
              </button>
            ))}
          </div>
          {!vrm && (
            <p className="character-chat-room__menu-note">
              {t("characterChat.room.gestureUnavailable")}
            </p>
          )}

          {portrait && (
            <>
              <p className="character-chat-room__menu-heading">
                {t("characterChat.room.expressionVariantsHeading")}
              </p>
              <p className="character-chat-room__menu-note">
                {portraitAvailable
                  ? t("characterChat.room.expressionVariantsHint")
                  : t("characterChat.room.expressionVariantsNoPortrait")}
              </p>
              <fieldset
                className="character-chat__preview-chips character-chat__chip-fieldset"
                aria-label={t("characterChat.room.expressionVariantsHeading")}
              >
                {PORTRAIT_EXPRESSIONS.map((key) => {
                  const on = chosen.includes(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`character-chat__preview-chip${on ? " is-active" : ""}`}
                      aria-pressed={on}
                      disabled={
                        !portraitAvailable || Boolean(expressionProgress)
                      }
                      onClick={() => toggleChosen(key)}
                    >
                      {t(`settings.avatar.expressions.${key}`)}
                      {key in expressionPortraits && (
                        <span aria-hidden> ✓</span>
                      )}
                    </button>
                  );
                })}
              </fieldset>
              {preciseAvailable && (
                <label className="character-chat__switch-row">
                  <span className="character-chat__switch-info">
                    <strong>
                      {t("characterChat.room.adventurePreciseToggle")}
                    </strong>
                    <small>
                      {t("characterChat.room.expressionPreciseHint")}
                    </small>
                  </span>
                  <input
                    type="checkbox"
                    className="character-chat__switch-input"
                    checked={usePrecise}
                    onChange={(event) => setUsePrecise(event.target.checked)}
                  />
                  <span className="character-chat__switch" />
                </label>
              )}
              {expressionProgress ? (
                <p className="character-chat-room__menu-note" role="status">
                  <span className="character-chat__progress">
                    <span />
                    {t("characterChat.room.expressionVariantsProgress", {
                      expression: t(
                        `settings.avatar.expressions.${expressionProgress.expression}`,
                        { defaultValue: expressionProgress.expression },
                      ),
                      current: expressionProgress.done + 1,
                      total: expressionProgress.total,
                    })}
                  </span>
                </p>
              ) : (
                <button
                  type="button"
                  className="character-chat-room__menu-item"
                  disabled={!portraitAvailable || chosen.length === 0}
                  onClick={() => {
                    onGenerateExpressions(
                      PORTRAIT_EXPRESSIONS.filter((key) =>
                        chosen.includes(key),
                      ),
                      preciseAvailable && usePrecise,
                    );
                    setSelected(null);
                  }}
                >
                  <strong>
                    {t("characterChat.room.expressionVariantsGenerate", {
                      count: chosen.length,
                    })}
                  </strong>
                  <small>
                    {t("characterChat.room.expressionVariantsCost")}
                  </small>
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
