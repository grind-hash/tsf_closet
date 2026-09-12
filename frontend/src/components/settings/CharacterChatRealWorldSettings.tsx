/**
 * 設定画面「キャラチャット」項目の直後に置く、セレナの調べ物(Web 検索・天気)の ON/OFF。
 *
 * 値は localStorage に保存し、発言のたびにリクエストへ載せる。サーバー側に
 * TAVILY_API_KEY / WEATHER_LOCATION が無いと ON でも調べないため、その場合は
 * 項目の下に理由を添える。スイッチはどの状態でも操作できる。
 * Web 検索を ON にするときは、Tavily の Acceptable Use Policy に従うことと、検索結果に
 * 不正確・不適切な内容が含まれ得ることへの同意を確認する。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchUserSettings } from "../../apis/settings";
import { useSettings } from "../../contexts/SettingsContext";
import ConfirmDialog from "../ui/ConfirmDialog";

const TAVILY_AUP_URL = "https://www.tavily.com/acceptable-use-policy";

/** 同意モーダルに挙げる、検索してはいけない内容 */
const TERMS_PROHIBITED_KEYS = [
  "settings.characterChatWebSearchTermsProhibitedSexual",
  "settings.characterChatWebSearchTermsProhibitedMinors",
  "settings.characterChatWebSearchTermsProhibitedIllegal",
  "settings.characterChatWebSearchTermsProhibitedOther",
] as const;

/** サーバー側の設定状況。取得前・取得失敗・項目の無い応答では undefined(注記を出さない) */
interface RealWorldConfiguration {
  webSearch?: boolean;
  weather?: boolean;
}

interface RealWorldToggleProps {
  label: string;
  description: string;
  /** 動作条件を満たしていないときの説明。null なら出さない */
  note: string | null;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function RealWorldToggle({
  label,
  description,
  note,
  checked,
  onChange,
}: RealWorldToggleProps) {
  return (
    <div className="settings-screen__item">
      <label className="settings-screen__toggle">
        <div className="settings-screen__toggle-info">
          <span className="settings-screen__item-label">{label}</span>
          <span className="settings-screen__item-desc">{description}</span>
        </div>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="settings-screen__toggle-input"
        />
        <span className="settings-screen__toggle-switch" />
      </label>
      {note && (
        <p className="settings-screen__item-note" role="note">
          {note}
        </p>
      )}
    </div>
  );
}

export default function CharacterChatRealWorldSettings() {
  const { t } = useTranslation();
  const {
    state,
    setCharacterChatWebSearchEnabled,
    setCharacterChatWeatherEnabled,
  } = useSettings();
  const [configuration, setConfiguration] = useState<RealWorldConfiguration>(
    {},
  );
  const [termsOpen, setTermsOpen] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetchUserSettings()
      .then((settings) => {
        if (cancelled) return;
        setConfiguration({
          webSearch: settings.web_search_configured,
          weather: settings.weather_configured,
        });
      })
      .catch(() => {
        // 取得できないときは設定状況を不明として注記を出さない
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <RealWorldToggle
        label={t("settings.characterChatWebSearch")}
        description={t("settings.characterChatWebSearchDesc")}
        note={
          configuration.webSearch === false
            ? t("settings.characterChatWebSearchUnavailable")
            : null
        }
        checked={state.characterChatWebSearchEnabled}
        onChange={(checked) => {
          // 有効にするときだけ、利用規約への同意を確認してから ON にする
          if (checked) setTermsOpen(true);
          else setCharacterChatWebSearchEnabled(false);
        }}
      />
      <RealWorldToggle
        label={t("settings.characterChatWeather")}
        description={t("settings.characterChatWeatherDesc")}
        note={
          configuration.weather === false
            ? t("settings.characterChatWeatherUnavailable")
            : null
        }
        checked={state.characterChatWeatherEnabled}
        onChange={setCharacterChatWeatherEnabled}
      />
      <ConfirmDialog
        open={termsOpen}
        title={t("settings.characterChatWebSearchTermsTitle")}
        confirmLabel={t("settings.characterChatWebSearchTermsAccept")}
        cancelLabel={t("settings.characterChatWebSearchTermsCancel")}
        onConfirm={() => {
          setTermsOpen(false);
          setCharacterChatWebSearchEnabled(true);
        }}
        onCancel={() => setTermsOpen(false)}
        className="settings-screen__terms-dialog"
        testId="character-chat-web-search-terms"
      >
        <p>{t("settings.characterChatWebSearchTermsIntro")}</p>
        <p>{t("settings.characterChatWebSearchTermsMustFollow")}</p>
        <p>{t("settings.characterChatWebSearchTermsProhibitedLead")}</p>
        <ul className="settings-screen__terms-list">
          {TERMS_PROHIBITED_KEYS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
        <p>{t("settings.characterChatWebSearchTermsSafeguards")}</p>
        <p>{t("settings.characterChatWebSearchTermsResults")}</p>
        <p>{t("settings.characterChatWebSearchTermsConsent")}</p>
        <p>
          <a href={TAVILY_AUP_URL} target="_blank" rel="noopener noreferrer">
            {t("settings.characterChatWebSearchTermsLink")}
          </a>
        </p>
      </ConfirmDialog>
    </>
  );
}
