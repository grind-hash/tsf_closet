import { useTranslation } from "react-i18next";
import type { CharacterChatThread } from "../../apis/characterChat";
import { PORTRAIT_ALPHA_OPTIONS } from "../../constants/adventure";
import { useTransparentImage } from "../../hooks/useTransparentImage";

interface CharacterChatStageProps {
  thread: CharacterChatThread;
  /** 立ち絵の描き直し・姿の差し替え中 */
  busy: boolean;
  /** 発言の処理が立ち絵工程にいる */
  drawing: boolean;
  onGenerate: () => void;
}

const BUNDLED_PORTRAIT_FILENAME = "serena.png";

/**
 * 全画面のステージ。Adventure の対面会話モードと同じく、キャラクターを中央に
 * 大きく立たせる。生成した立ち絵(standing)は白抜きし、素材からコピーした
 * 場面画像(scene)は素通しで出す。画像が無ければ案内と生成ボタン。
 * (将来 3D モデル(VRM)を置くときもこの枠に差し替える)
 */
export default function CharacterChatStage({
  thread,
  busy,
  drawing,
  onGenerate,
}: CharacterChatStageProps) {
  const { t } = useTranslation();
  const standing = thread.appearance.portrait_kind === "standing";
  const { url, processing } = useTransparentImage(
    thread.portrait_url,
    standing,
    PORTRAIT_ALPHA_OPTIONS,
  );
  const working = busy || drawing;

  return (
    <div className="character-chat-room__stage" aria-busy={working}>
      <div className="character-chat-room__backdrop" />
      {url ? (
        <img
          className={`character-chat-room__portrait${
            standing ? "" : " character-chat-room__portrait--scene"
          }${working ? " is-working" : ""}`}
          src={url}
          alt={thread.name}
        />
      ) : (
        <div className="character-chat-room__missing">
          <span className="character-chat__placeholder" aria-hidden>
            💬
          </span>
          {thread.portrait_missing && (
            <>
              <p>
                {t("characterChat.room.portraitMissing", {
                  file: BUNDLED_PORTRAIT_FILENAME,
                })}
              </p>
              <button
                type="button"
                className="character-chat__secondary"
                disabled={working}
                onClick={onGenerate}
              >
                {t("characterChat.room.generatePortrait")}
              </button>
            </>
          )}
        </div>
      )}
      <div className="character-chat-room__scrim" />
      {(working || processing) && (
        <div className="character-chat-room__stage-status" role="status">
          <span className="character-chat__progress">
            <span />
            {working
              ? drawing
                ? t("characterChat.room.portraitBusy")
                : t("characterChat.room.appearanceUpdating")
              : ""}
          </span>
          {working && drawing && (
            <small>{t("characterChat.room.portraitBusyHint")}</small>
          )}
        </div>
      )}
    </div>
  );
}
