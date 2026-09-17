/**
 * 設定画面「キャラチャット」項目の直後に置く、セレナの調べ物(Web 検索・天気)の ON/OFF。
 *
 * 値は localStorage に保存し、発言のたびにリクエストへ載せる。サーバー側に
 * TAVILY_API_KEY / WEATHER_LOCATION が無いと ON でも調べないため、その場合は
 * 項目の下に理由を添える。スイッチはどの状態でも操作できる。
 * Web 検索を ON にするときは利用条件(要約と、折りたたんだ詳細な注意事項)への同意を
 * 確認し、同意後も同じ利用条件を読み返せるようにする。
 */

import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchUserSettings } from "../../apis/settings";
import { useSettings } from "../../contexts/SettingsContext";
import ConfirmDialog from "../ui/ConfirmDialog";

const TAVILY_AUP_URL = "https://www.tavily.com/acceptable-use-policy";

/** 利用条件の 1 節。段落、箇条書き、箇条書きの後の段落の順に並べる */
interface TermsSection {
  heading: string;
  paragraphs: string[];
  items?: string[];
  after?: string[];
}

/** i18n の settings.characterChatWebSearchTerms の形 */
interface WebSearchTerms {
  title: string;
  /** 同意のたびに読む要約。詳細は折りたたみの中に置く */
  summary: string[];
  /** 詳細な注意事項の折りたたみの見出し */
  details: string;
  intro: string[];
  sections: TermsSection[];
  consent: string;
  link: string;
  accept: string;
  cancel: string;
  read: string;
  close: string;
}

/** 同意の確認(ON にするとき)か、読み返しか */
type TermsMode = "consent" | "read";

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
  /** 項目の下に添える操作(利用条件を読むなど) */
  children?: ReactNode;
}

function RealWorldToggle({
  label,
  description,
  note,
  checked,
  onChange,
  children,
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
      {children}
    </div>
  );
}

/**
 * 利用条件の本文。要約・規約へのリンク・折りたたんだ詳細な注意事項の順に並べ、
 * 同意の一文は同意を求めるときだけ最後(ボタンの直前)に出す。
 */
function WebSearchTermsBody({
  terms,
  showConsent,
}: {
  terms: WebSearchTerms;
  showConsent: boolean;
}) {
  return (
    <>
      <div className="settings-screen__terms-summary">
        {terms.summary.map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
      <p>
        <a href={TAVILY_AUP_URL} target="_blank" rel="noopener noreferrer">
          {terms.link}
        </a>
      </p>
      <details className="settings-screen__terms-details">
        <summary>{terms.details}</summary>
        {terms.intro.map((text) => (
          <p key={text}>{text}</p>
        ))}
        {terms.sections.map((section) => (
          <section key={section.heading}>
            <h4>{section.heading}</h4>
            {section.paragraphs.map((text) => (
              <p key={text}>{text}</p>
            ))}
            {section.items && (
              <ul className="settings-screen__terms-list">
                {section.items.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            )}
            {section.after?.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </section>
        ))}
      </details>
      {showConsent && (
        <p>
          <strong>{terms.consent}</strong>
        </p>
      )}
    </>
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
  const [termsMode, setTermsMode] = useState<TermsMode | null>(null);
  const terms = t("settings.characterChatWebSearchTerms", {
    returnObjects: true,
  }) as unknown as WebSearchTerms;
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

  const reading = termsMode === "read";

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
          // 有効にするときだけ、利用条件への同意を確認してから ON にする
          if (checked) setTermsMode("consent");
          else setCharacterChatWebSearchEnabled(false);
        }}
      >
        <button
          type="button"
          className="settings-screen__terms-read"
          onClick={() => setTermsMode("read")}
        >
          {terms.read}
        </button>
      </RealWorldToggle>
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
        open={termsMode !== null}
        title={terms.title}
        confirmLabel={reading ? terms.close : terms.accept}
        cancelLabel={reading ? undefined : terms.cancel}
        onConfirm={() => {
          if (termsMode === "consent") setCharacterChatWebSearchEnabled(true);
          setTermsMode(null);
        }}
        onCancel={() => setTermsMode(null)}
        dismissible={reading}
        className="settings-screen__terms-dialog"
        testId="character-chat-web-search-terms"
      >
        <WebSearchTermsBody terms={terms} showConsent={!reading} />
      </ConfirmDialog>
    </>
  );
}
