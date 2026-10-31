/**
 * 依頼モードの依頼カード。キャラクター状態パネルの属性セクションと同じ様式で並べる。
 * 願い(全文)・満足度・好み(未開示は分類だけ)・直近のヒントを出す。
 */

import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import "./RequestCard.css";

export default function RequestCard() {
  const { t } = useTranslation();
  const { state, generateRequest } = useGame();
  const {
    request,
    requestGenerating,
    requestError,
    sessionId,
    isTransforming,
  } = state;
  if (!request && !requestGenerating && !requestError) return null;

  const regenerate = () => {
    if (sessionId) void generateRequest(sessionId);
  };
  const fulfilled = request?.status === "fulfilled";
  const satisfaction = Math.max(0, Math.min(100, request?.satisfaction ?? 0));

  return (
    <section className="request-card" aria-label={t("chat.request.title")}>
      <div className="request-card__head">
        <h4 className="character-state-panel__section-title">
          {t("chat.request.title")}
        </h4>
        {fulfilled && (
          <em className="request-card__badge">{t("chat.request.fulfilled")}</em>
        )}
      </div>

      {requestGenerating ? (
        <p className="request-card__progress" role="status">
          <span className="request-card__spinner" aria-hidden />
          {t("chat.request.generating")}
        </p>
      ) : request ? (
        <>
          <p className="request-card__wish">{request.wish}</p>

          <div className="request-card__meter">
            <span>{t("chat.request.satisfaction")}</span>
            <strong>
              {t("chat.request.satisfactionValue", { value: satisfaction })}
            </strong>
          </div>
          <div
            className={`request-card__bar${fulfilled ? " is-fulfilled" : ""}`}
            role="progressbar"
            aria-label={t("chat.request.satisfaction")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={satisfaction}
          >
            <i style={{ width: `${satisfaction}%` }} />
            <b
              className="request-card__threshold"
              style={{ left: `${request.threshold}%` }}
              aria-hidden
            />
          </div>
          <p className="request-card__note">
            {request.evaluated_turns === 0
              ? t("chat.request.notEvaluated")
              : t("chat.request.thresholdNote", {
                  threshold: request.threshold,
                })}
          </p>

          <h5 className="request-card__subtitle">
            {t("chat.request.preferences")}
          </h5>
          <ul className="request-card__preferences">
            {request.preferences.map((preference) => (
              <li
                key={preference.id}
                className={preference.met ? "is-met" : undefined}
              >
                <span aria-hidden>{preference.met ? "✓" : "・"}</span>
                <span>
                  {preference.text ??
                    t("chat.request.hiddenPreference", {
                      hint: preference.hint || "?",
                    })}
                </span>
              </li>
            ))}
          </ul>
          {request.hint && (
            <p className="request-card__hint">
              {t("chat.request.hint", { hint: request.hint })}
            </p>
          )}

          {request.can_regenerate && (
            <div className="request-card__actions">
              <button
                type="button"
                className="request-card__button"
                onClick={regenerate}
                disabled={isTransforming}
              >
                {t("chat.request.regenerate")}
              </button>
              <span className="request-card__note">
                {t("chat.request.regenerateHint")}
              </span>
            </div>
          )}
        </>
      ) : (
        <div className="request-card__actions">
          <p className="request-card__error">
            {requestError || t("chat.request.generateFailed")}
          </p>
          <button
            type="button"
            className="request-card__button"
            onClick={regenerate}
            disabled={isTransforming}
          >
            {t("chat.request.retry")}
          </button>
        </div>
      )}
    </section>
  );
}
