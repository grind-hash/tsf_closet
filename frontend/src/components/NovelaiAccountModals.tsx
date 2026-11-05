import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../contexts/SettingsContext";
import {
  type NovelaiAccountCheck,
  useNovelaiAccountCheck,
} from "../hooks/useNovelaiAccountCheck";
import ApiKeyConsentModal from "./ApiKeyConsentModal";
import NovelAIWarningModal from "./NovelAIWarningModal";

/**
 * 通常プレイ以外で NovelAI を使う画面に置く確認。直接開いた・再読み込みしたときも、
 * 生成元が NovelAI と分かった時点(/health の取得後)で同意とプランを1回だけ確かめる。
 * 通常プレイなどから移ってきてプランが分かっていれば何もしない。
 *
 * ready: 画面が自前の同意ダイアログを持つときに、同意が済むまで待たせる(既定 true)
 */
export function NovelaiAccountCheckOnOpen({
  ready = true,
}: {
  ready?: boolean;
}) {
  const { state: settingsState } = useSettings();
  const check = useNovelaiAccountCheck();
  const { startCheck } = check;
  const checkedRef = useRef(false);
  const needsCheck =
    ready &&
    settingsState.imageProvider === "novelai" &&
    settingsState.novelaiTier === null;

  useEffect(() => {
    if (!needsCheck || checkedRef.current) return;
    checkedRef.current = true;
    void startCheck();
  }, [needsCheck, startCheck]);

  return <NovelaiAccountModals check={check} />;
}

/** useNovelaiAccountCheck の確認中表示・非 Opus の警告・API キー利用の同意 */
export default function NovelaiAccountModals({
  check,
}: {
  check: NovelaiAccountCheck;
}) {
  const { t } = useTranslation();
  const { state: settingsState } = useSettings();

  return (
    <>
      {check.checking && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="spinner"></div>
            <p>{t("appLoading.checkingNovelai")}</p>
          </div>
        </div>
      )}

      {/* NovelAI非Opusプラン警告モーダル */}
      {check.showWarning && settingsState.novelaiTier !== null && (
        <NovelAIWarningModal
          tier={settingsState.novelaiTier}
          onContinue={check.continueWithoutOpus}
          onCancel={check.dismissWarning}
        />
      )}

      {/* NovelAI APIキー利用同意モーダル */}
      {check.showConsent && (
        <ApiKeyConsentModal
          onConsent={check.acceptConsent}
          onDecline={check.declineConsent}
        />
      )}

      {/* APIキー同意拒否時のメッセージ */}
      {check.consentDeclined && (
        <div className="backdrop">
          <div className="backdrop-content">
            <div className="consent-declined-message">
              <span className="consent-declined-icon">🔒</span>
              <h3>{t("consentDeclined.title")}</h3>
              <p>{t("consentDeclined.message")}</p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => window.location.reload()}
              >
                {t("consentDeclined.reload")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
