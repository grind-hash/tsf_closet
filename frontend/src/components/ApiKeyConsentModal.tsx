/**
 * APIキー利用同意モーダル
 * NovelAI APIキーの利用用途を説明し、同意を取得する
 */

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import "./ApiKeyConsentModal.css";
import { saveApiKeyConsent } from "./apiKeyConsentStorage";

interface ApiKeyConsentModalProps {
  onConsent: () => void;
  onDecline: () => void;
}

export default function ApiKeyConsentModal({
  onConsent,
  onDecline,
}: ApiKeyConsentModalProps) {
  const { t } = useTranslation();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // アニメーション用に少し遅延
    const timer = setTimeout(() => setIsVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  const handleConsent = () => {
    saveApiKeyConsent();
    setIsVisible(false);
    setTimeout(onConsent, 200);
  };

  const handleDecline = () => {
    setIsVisible(false);
    setTimeout(onDecline, 200);
  };

  return (
    <div className={`consent-modal-overlay ${isVisible ? "is-visible" : ""}`}>
      <div className="consent-modal">
        <div className="consent-modal__header">
          <span className="consent-modal__icon">🔑</span>
          <h2 className="consent-modal__title">{t("apiKeyConsent.title")}</h2>
        </div>

        <div className="consent-modal__content">
          <p className="consent-modal__intro">{t("apiKeyConsent.intro")}</p>

          <div className="consent-modal__usage-list">
            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">📊</span>
              <div className="consent-modal__usage-text">
                <strong>{t("apiKeyConsent.usagePlanTitle")}</strong>
                <span>{t("apiKeyConsent.usagePlanDesc")}</span>
              </div>
            </div>

            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">🎨</span>
              <div className="consent-modal__usage-text">
                <strong>{t("apiKeyConsent.usageImageTitle")}</strong>
                <span>{t("apiKeyConsent.usageImageDesc")}</span>
              </div>
            </div>

            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">💬</span>
              <div className="consent-modal__usage-text">
                <strong>{t("apiKeyConsent.usageTextTitle")}</strong>
                <span>{t("apiKeyConsent.usageTextDesc")}</span>
              </div>
            </div>
          </div>

          <div className="consent-modal__safety">
            <span className="consent-modal__safety-icon">🏠</span>
            <p>{t("apiKeyConsent.safety")}</p>
          </div>

          <div className="consent-modal__notice">
            <span className="consent-modal__notice-icon">⚠️</span>
            <p>
              {t("apiKeyConsent.notice")}
              <strong>{t("apiKeyConsent.noticeStrong")}</strong>
              {t("apiKeyConsent.noticeEnd")}
            </p>
          </div>
        </div>

        <div className="consent-modal__actions">
          <button
            type="button"
            className="consent-modal__btn consent-modal__btn--decline"
            onClick={handleDecline}
          >
            {t("apiKeyConsent.decline")}
          </button>
          <button
            type="button"
            className="consent-modal__btn consent-modal__btn--consent"
            onClick={handleConsent}
          >
            {t("apiKeyConsent.consent")}
          </button>
        </div>
      </div>
    </div>
  );
}
