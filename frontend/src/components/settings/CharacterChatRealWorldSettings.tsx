/**
 * 設定画面「キャラチャット」項目の直後に置く、セレナの調べ物(Web 検索・天気)の ON/OFF。
 *
 * 値は localStorage に保存し、発言のたびにリクエストへ載せる。サーバー側に
 * TAVILY_API_KEY / WEATHER_LOCATION が無いと ON でも調べないため、その場合は
 * 項目の下に理由を添える。スイッチはどの状態でも操作できる。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchUserSettings } from "../../apis/settings";
import { useSettings } from "../../contexts/SettingsContext";

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
        onChange={setCharacterChatWebSearchEnabled}
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
    </>
  );
}
