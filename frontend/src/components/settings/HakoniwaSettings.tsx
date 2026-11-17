/**
 * 設定画面「AI箱庭」の項目。新しく作る世界の既定(Web検索・あなたの名前・住民とあなた・
 * 世界の違和感)と、世界を作った直後の開幕を決める。作った世界ごとの設定は、各世界の
 * 「設定」タブで変える。値は localStorage(SettingsContext の hakoniwaPreferences)に保存する。
 */
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  HAKONIWA_PLAYER_NAME_MAX,
  type HakoniwaPlayerPresence,
} from "../../apis/hakoniwa";
import { fetchUserSettings } from "../../apis/settings";
import {
  type HakoniwaOpeningGuide,
  useSettings,
} from "../../contexts/SettingsContext";
import SettingsChoice from "./SettingsChoice";
import WebSearchTermsDialog, {
  useWebSearchTerms,
  type WebSearchTermsMode,
} from "./WebSearchTermsDialog";

interface ToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function Toggle({ label, description, checked, onChange }: ToggleProps) {
  return (
    <label className="settings-screen__toggle">
      <div className="settings-screen__toggle-info">
        <span className="settings-screen__item-label">{label}</span>
        <span className="settings-screen__item-desc">{description}</span>
      </div>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="settings-screen__toggle-input"
      />
      <span className="settings-screen__toggle-switch" />
    </label>
  );
}

/** 新しい世界で Web 検索を使うか。ON にするときは利用条件への同意を確かめる */
export function HakoniwaWebSearchSetting() {
  const { t } = useTranslation();
  const { state, setHakoniwaPreferences } = useSettings();
  const terms = useWebSearchTerms("hakoniwa");
  const [termsMode, setTermsMode] = useState<WebSearchTermsMode | null>(null);
  // サーバーに Tavily の鍵があるか。取得前・取得失敗では注記を出さない
  const [configured, setConfigured] = useState<boolean | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    void fetchUserSettings()
      .then((settings) => {
        if (!cancelled) setConfigured(settings.web_search_configured);
      })
      .catch(() => {
        // 設定状況が分からないときは注記を出さない
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="settings-screen__item">
      <Toggle
        label={t("settings.hakoniwaWebSearch")}
        description={t("settings.hakoniwaWebSearchDesc")}
        checked={state.hakoniwaPreferences.webSearchEnabled}
        onChange={(checked) => {
          if (checked) setTermsMode("consent");
          else setHakoniwaPreferences({ webSearchEnabled: false });
        }}
      />
      {configured === false && (
        <p className="settings-screen__item-note" role="note">
          {t("settings.hakoniwaWebSearchUnavailable")}
        </p>
      )}
      <button
        type="button"
        className="settings-screen__terms-read"
        onClick={() => setTermsMode("read")}
      >
        {terms.read}
      </button>
      <WebSearchTermsDialog
        mode={termsMode}
        variant="hakoniwa"
        onAccept={() => setHakoniwaPreferences({ webSearchEnabled: true })}
        onClose={() => setTermsMode(null)}
        testId="hakoniwa-web-search-terms"
      />
    </div>
  );
}

/** 新しい世界の既定: あなたの名前・住民とあなた・世界の違和感・おまかせの住民の立ち絵 */
export function HakoniwaDefaultsSetting() {
  const { t } = useTranslation();
  const { state, setHakoniwaPreferences } = useSettings();
  const preferences = state.hakoniwaPreferences;
  const nameId = useId();
  const presenceOptions: {
    id: HakoniwaPlayerPresence;
    label: string;
    description: string;
  }[] = [
    {
      id: "known",
      label: t("settings.hakoniwaPresenceKnown"),
      description: t("settings.hakoniwaPresenceKnownDesc"),
    },
    {
      id: "hidden",
      label: t("settings.hakoniwaPresenceHidden"),
      description: t("settings.hakoniwaPresenceHiddenDesc"),
    },
  ];

  return (
    <>
      <div className="settings-screen__item">
        <div className="settings-screen__toggle-info">
          <label className="settings-screen__item-label" htmlFor={nameId}>
            {t("settings.hakoniwaPlayerName")}
          </label>
          <span className="settings-screen__item-desc">
            {t("settings.hakoniwaPlayerNameDesc")}
          </span>
        </div>
        <input
          id={nameId}
          type="text"
          className="settings-screen__text-input"
          value={preferences.playerName}
          maxLength={HAKONIWA_PLAYER_NAME_MAX}
          placeholder={t("settings.hakoniwaPlayerNamePlaceholder")}
          onChange={(event) =>
            setHakoniwaPreferences({ playerName: event.target.value })
          }
        />
      </div>
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.hakoniwaPresence")}
          </span>
        </div>
        <SettingsChoice
          name="hakoniwaPresence"
          label={t("settings.hakoniwaPresence")}
          value={preferences.playerPresence}
          options={presenceOptions}
          onChange={(playerPresence) =>
            setHakoniwaPreferences({ playerPresence })
          }
        />
      </div>
      <div className="settings-screen__item">
        <Toggle
          label={t("settings.hakoniwaDissonance")}
          description={t("settings.hakoniwaDissonanceDesc")}
          checked={preferences.dissonanceEnabled}
          onChange={(dissonanceEnabled) =>
            setHakoniwaPreferences({ dissonanceEnabled })
          }
        />
      </div>
      <div className="settings-screen__item">
        <Toggle
          label={t("settings.hakoniwaRandomPortraits")}
          description={t("settings.hakoniwaRandomPortraitsDesc")}
          checked={preferences.randomPortraits}
          onChange={(randomPortraits) =>
            setHakoniwaPreferences({ randomPortraits })
          }
        />
      </div>
    </>
  );
}

/** 世界を作った直後の開幕と、遊び方の説明の出し方 */
export function HakoniwaOpeningSetting() {
  const { t } = useTranslation();
  const { state, setHakoniwaPreferences } = useSettings();
  const preferences = state.hakoniwaPreferences;
  const guideOptions: {
    id: HakoniwaOpeningGuide;
    label: string;
    description: string;
  }[] = [
    {
      id: "first",
      label: t("settings.hakoniwaOpeningGuideFirst"),
      description: t("settings.hakoniwaOpeningGuideFirstDesc"),
    },
    {
      id: "always",
      label: t("settings.hakoniwaOpeningGuideAlways"),
      description: t("settings.hakoniwaOpeningGuideAlwaysDesc"),
    },
    {
      id: "never",
      label: t("settings.hakoniwaOpeningGuideNever"),
      description: t("settings.hakoniwaOpeningGuideNeverDesc"),
    },
  ];

  return (
    <>
      <div className="settings-screen__item">
        <Toggle
          label={t("settings.hakoniwaOpening")}
          description={t("settings.hakoniwaOpeningDesc")}
          checked={preferences.openingEnabled}
          onChange={(openingEnabled) =>
            setHakoniwaPreferences({ openingEnabled })
          }
        />
      </div>
      {/* 開幕を流さないときも隠さず、効かないことを添える */}
      <div className="settings-screen__item">
        <div className="settings-screen__item-header">
          <span className="settings-screen__item-label">
            {t("settings.hakoniwaOpeningGuide")}
          </span>
        </div>
        <SettingsChoice
          name="hakoniwaOpeningGuide"
          label={t("settings.hakoniwaOpeningGuide")}
          value={preferences.openingGuide}
          options={guideOptions}
          onChange={(openingGuide) => setHakoniwaPreferences({ openingGuide })}
        />
        {!preferences.openingEnabled && (
          <p className="settings-screen__item-note" role="note">
            {t("settings.hakoniwaOpeningGuideUnused")}
          </p>
        )}
      </div>
    </>
  );
}
