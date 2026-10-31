/**
 * 依頼モードの依頼カード。キャラクター状態パネルの属性セクションと同じ様式で並べる。
 * 願い(全文)・満足度・施術の残り手数・好み(未開示は分類だけ)・カウンセリング・
 * 直近のヒントを出す。
 */

import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { REQUEST_QUESTION_MAX_LENGTH } from "../../constants/playLimits";
import { useGame } from "../../contexts/GameContext";
import "./RequestCard.css";

export default function RequestCard() {
  const { t } = useTranslation();
  const { state, generateRequest, askRequestQuestion } = useGame();
  const {
    request,
    requestGenerating,
    requestError,
    requestTurnLimit,
    sessionId,
    isTransforming,
  } = state;
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  if (!request && !requestGenerating && !requestError) return null;

  // 作り直しても手数と質問の回数は引き継ぐ。依頼が無い(生成失敗)なら開始画面の選択を使う
  const regenerate = () => {
    if (!sessionId) return;
    void generateRequest(
      sessionId,
      request
        ? {
            turnLimit: request.turn_limit,
            questionLimit: request.question_limit,
          }
        : { turnLimit: requestTurnLimit },
    );
  };
  const ask = async (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setAskError(null);
    try {
      await askRequestQuestion(text);
      setQuestion("");
    } catch (error) {
      setAskError(
        error instanceof Error ? error.message : t("chat.request.askFailed"),
      );
    } finally {
      setAsking(false);
    }
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
          {request.listening_bonus > 0 && (
            <p className="request-card__bonus">
              {t("chat.request.listeningBonus", {
                bonus: request.listening_bonus,
              })}
            </p>
          )}

          <div
            className={`request-card__meter${
              request.turns_remaining === 0 ? " is-exhausted" : ""
            }`}
          >
            <span>{t("chat.request.turnsLabel")}</span>
            <strong>
              {request.turn_limit === null
                ? t("chat.request.turnsUnlimited", { used: request.turns_used })
                : t("chat.request.turnsRemaining", {
                    remaining: request.turns_remaining ?? 0,
                    limit: request.turn_limit,
                  })}
            </strong>
          </div>

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

          {request.question_limit > 0 && (
            <div className="request-card__counseling">
              <h5 className="request-card__subtitle">
                {t("chat.request.counseling")}
              </h5>
              {request.questions.length > 0 && (
                <ul className="request-card__qa">
                  {request.questions.map((item) => (
                    <li
                      key={`${item.question}\n${item.answer}`}
                      className={item.reflected ? "is-reflected" : undefined}
                    >
                      <span className="request-card__question">
                        {t("chat.request.questionLabel")}: {item.question}
                        {item.reflected && (
                          <em className="request-card__reflected">
                            {t("chat.request.reflected")}
                          </em>
                        )}
                      </span>
                      <span className="request-card__answer">
                        {item.answer}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {request.questions_remaining > 0 ? (
                <form className="request-card__ask" onSubmit={ask}>
                  <input
                    type="text"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder={t("chat.request.questionPlaceholder")}
                    maxLength={REQUEST_QUESTION_MAX_LENGTH}
                    disabled={asking}
                    aria-label={t("chat.request.questionPlaceholder")}
                  />
                  <button
                    type="submit"
                    className="request-card__button"
                    disabled={asking || isTransforming || !question.trim()}
                  >
                    {t("chat.request.ask")}
                  </button>
                </form>
              ) : null}
              {asking ? (
                <p className="request-card__progress" role="status">
                  <span className="request-card__spinner" aria-hidden />
                  {t("chat.request.asking")}
                </p>
              ) : (
                <p className="request-card__note">
                  {request.questions_remaining > 0
                    ? t("chat.request.questionsRemaining", {
                        count: request.questions_remaining,
                      })
                    : t("chat.request.questionsUsedUp")}
                </p>
              )}
              {askError && <p className="request-card__error">{askError}</p>}
            </div>
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
