import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { hakoniwaMediaUrl } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useTransparentImages } from "../../hooks/useTransparentImages";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import HakoniwaMessageFooter from "./HakoniwaMessageFooter";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らない)
const ALPHA_OPTIONS = { targetColor: null, threshold: 12, featherRadius: 1.8 };
const MESSAGE_MAX = 500;

function pointerIsFine(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(pointer: fine)").matches
  );
}

/**
 * 箱庭の中で住民と話す画面(ADV と同じ枠)。背景はその住民のいる場所、立ち絵はいまの姿。
 * 窓の右上に「ログ」と ✕(ウィンドウを非表示)。変身・元に戻す指示はその場で実行される。
 */
export default function HakoniwaChat() {
  const { t } = useTranslation();
  const { world, chatResidentId, chatHistory, closeChat, sendChat, busy } =
    useHakoniwa();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const [windowHidden, setWindowHidden] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const showRef = useRef<HTMLButtonElement | null>(null);
  const resident =
    world?.residents.find((item) => item.id === chatResidentId) ?? null;
  const urls = useMemo(
    () =>
      resident?.display_avatar_url
        ? [hakoniwaMediaUrl(resident.display_avatar_url)]
        : [],
    [resident?.display_avatar_url],
  );
  const transparent = useTransparentImages(urls, ALPHA_OPTIONS);

  // 開いたら入力欄へ。窓を隠したり戻したりしたら、残る側のボタン・入力欄へ移す
  useEffect(() => {
    if (!chatResidentId) return;
    (windowHidden ? showRef : inputRef).current?.focus();
  }, [chatResidentId, windowHidden]);

  if (!world || !resident) return null;

  const area = world.areas.find((item) => item.id === resident.current_area);
  const backgroundUrl = hakoniwaMediaUrl(area?.background_url);
  const portrait = urls[0] ? (transparent[urls[0]] ?? urls[0]) : null;
  const latest = [...chatHistory]
    .reverse()
    .find((entry) => entry.role !== "player");
  const sending = busy === "chat";

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;
    if (await sendChat(message)) setDraft("");
    inputRef.current?.focus();
  };

  const handleInputKey = (keyEvent: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      keyEvent.key === "Enter" &&
      !keyEvent.shiftKey &&
      !keyEvent.nativeEvent.isComposing &&
      pointerIsFine()
    ) {
      keyEvent.preventDefault();
      void submit();
    }
  };

  const handleKeyDown = (keyEvent: KeyboardEvent<HTMLDivElement>) => {
    if (keyEvent.key !== "Escape" || keyEvent.nativeEvent.isComposing) return;
    keyEvent.preventDefault();
    if (logOpen) setLogOpen(false);
    else closeChat();
  };

  const speakerOf = (role: string) =>
    role === "player"
      ? world.player_name || t("hakoniwa.chat.you")
      : role === "system"
        ? t("hakoniwa.chat.system")
        : resident.name;

  return (
    <div
      className={`hakoniwa-adv hakoniwa-chat${logOpen ? " is-log-open" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label={t("hakoniwa.chat.title", { name: resident.name })}
      onKeyDown={handleKeyDown}
      data-testid="hakoniwa-chat"
    >
      {backgroundUrl && (
        <img className="hakoniwa-adv__background" src={backgroundUrl} alt="" />
      )}
      <HakoniwaErrorBanner placement="overlay" clearOnMount />
      {portrait && (
        <div className="hakoniwa-adv__cast">
          <img
            className="hakoniwa-adv__portrait hakoniwa-adv__portrait--center"
            src={portrait}
            alt={resident.name}
          />
        </div>
      )}
      {windowHidden ? (
        <button
          ref={showRef}
          type="button"
          className="hakoniwa-button hakoniwa-adv__show"
          onClick={() => setWindowHidden(false)}
        >
          {t("common.messageWindow.show")}
        </button>
      ) : (
        <div className="hakoniwa-adv__window hakoniwa-chat__window">
          <div className="hakoniwa-adv__meta">
            <span className="hakoniwa-adv__speaker">
              {latest ? speakerOf(latest.role) : resident.name}
            </span>
            <div className="hakoniwa-adv__actions">
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                aria-expanded={logOpen}
                onClick={() => setLogOpen((open) => !open)}
              >
                {t("hakoniwa.chat.log")}
              </button>
              <button
                type="button"
                className="hakoniwa-icon-button"
                aria-label={t("common.messageWindow.hide")}
                title={t("common.messageWindow.hide")}
                onClick={() => setWindowHidden(true)}
              >
                ×
              </button>
            </div>
          </div>
          <p
            className={`hakoniwa-adv__text${latest?.role === "system" ? " is-narration" : ""}`}
            aria-live="polite"
          >
            {sending ? (
              <span className="hakoniwa-chat__thinking" role="status">
                <span className="hakoniwa-spinner" aria-hidden />
                {t("hakoniwa.chat.thinking", { name: resident.name })}
              </span>
            ) : latest ? (
              latest.role === "resident" ? (
                t("hakoniwa.chronicle.line", { text: latest.text })
              ) : (
                latest.text
              )
            ) : (
              t("hakoniwa.chat.empty", { name: resident.name })
            )}
          </p>
          <HakoniwaMessageFooter search={sending ? null : latest?.web_search} />
          <form className="hakoniwa-chat__form" onSubmit={submit}>
            <label className="hakoniwa-chat__label" htmlFor={inputId}>
              {t("hakoniwa.chat.inputLabel", { name: resident.name })}
            </label>
            <textarea
              ref={inputRef}
              id={inputId}
              rows={2}
              value={draft}
              maxLength={MESSAGE_MAX}
              placeholder={t("hakoniwa.chat.placeholder")}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleInputKey}
            />
            <div className="hakoniwa-adv__controls">
              <button
                type="button"
                className="hakoniwa-button hakoniwa-button--ghost"
                onClick={closeChat}
              >
                {t("hakoniwa.chat.close")}
              </button>
              <button
                type="submit"
                className="hakoniwa-button hakoniwa-button--primary"
                disabled={!draft.trim() || sending}
              >
                {t("hakoniwa.chat.send")}
              </button>
            </div>
          </form>
          <p className="hakoniwa-note hakoniwa-chat__hint">
            {t("hakoniwa.chat.hint")}
          </p>
        </div>
      )}
      {logOpen && (
        <aside
          className="hakoniwa-chat__log"
          aria-label={t("hakoniwa.chat.logTitle")}
        >
          <div className="hakoniwa-chat__log-head">
            <strong>{t("hakoniwa.chat.logTitle")}</strong>
            <button
              type="button"
              className="hakoniwa-icon-button"
              aria-label={t("hakoniwa.chat.logClose")}
              title={t("hakoniwa.chat.logClose")}
              onClick={() => setLogOpen(false)}
            >
              ×
            </button>
          </div>
          {chatHistory.length === 0 ? (
            <p className="hakoniwa-note">{t("hakoniwa.chat.logEmpty")}</p>
          ) : (
            <ol className="hakoniwa-chat__log-list">
              {chatHistory.map((entry, index) => (
                <li
                  // biome-ignore lint/suspicious/noArrayIndexKey: 会話は並び順そのものが識別子
                  key={index}
                  className={`hakoniwa-chat__entry is-${entry.role}`}
                >
                  <span className="hakoniwa-chat__entry-speaker">
                    {speakerOf(entry.role)}
                  </span>
                  <span>{entry.text}</span>
                  {entry.role === "resident" && (
                    <HakoniwaMessageFooter search={entry.web_search} />
                  )}
                </li>
              ))}
            </ol>
          )}
        </aside>
      )}
    </div>
  );
}
