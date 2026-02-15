/**
 * APIキー利用同意モーダル
 * NovelAI APIキーの利用用途を説明し、同意を取得する
 */

import { useState, useEffect } from "react";
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
          <h2 className="consent-modal__title">APIキーの利用について</h2>
        </div>

        <div className="consent-modal__content">
          <p className="consent-modal__intro">
            本アプリでは、config.envに設定されたNovelAI
            APIキーを以下の目的で利用します。よろしいですか？
          </p>

          <div className="consent-modal__usage-list">
            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">📊</span>
              <div className="consent-modal__usage-text">
                <strong>プラン情報の取得</strong>
                <span>Opusプランかどうかの判断に使用します</span>
              </div>
            </div>

            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">🎨</span>
              <div className="consent-modal__usage-text">
                <strong>画像生成</strong>
                <span>キャラクターの変身画像を生成します</span>
              </div>
            </div>

            <div className="consent-modal__usage-item">
              <span className="consent-modal__usage-icon">💬</span>
              <div className="consent-modal__usage-text">
                <strong>テキスト生成</strong>
                <span>キャラクターの心境テキストを生成します</span>
              </div>
            </div>
          </div>

          <div className="consent-modal__safety">
            <span className="consent-modal__safety-icon">🏠</span>
            <p>
              本アプリはOSSであり、ご自身のパソコン環境（localhost）でお楽しみいただくことを想定しています。
              APIキーがブラウザに保存されたり、本アプリから外部に送信されることはありません。
            </p>
          </div>

          <div className="consent-modal__notice">
            <span className="consent-modal__notice-icon">⚠️</span>
            <p>
              なお、一般的なセキュリティ対策として、
              <strong>定期的にAPIキーをリセットすること</strong>
              を推奨いたします。
            </p>
          </div>
        </div>

        <div className="consent-modal__actions">
          <button
            type="button"
            className="consent-modal__btn consent-modal__btn--decline"
            onClick={handleDecline}
          >
            キャンセル
          </button>
          <button
            type="button"
            className="consent-modal__btn consent-modal__btn--consent"
            onClick={handleConsent}
          >
            同意して続行
          </button>
        </div>
      </div>
    </div>
  );
}
