import { Fragment, useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { SalonVisit } from "../../apis/salon";
import {
  INSTRUCTION_MAX_LENGTH,
  REQUEST_QUESTION_MAX_LENGTH,
} from "../../constants/playLimits";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { useSalon } from "../../contexts/SalonContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { usePersistedState } from "../../hooks/usePersistedState";
import { usePlayTurn } from "../../hooks/usePlayTurn";
import { useTransformRequest } from "../../hooks/useTransformRequest";
import { getSalonRunPath } from "../../routes";
import { splitHintMarkers, stripHintMarkers } from "../../utils/hintMarkers";
import {
  formatSignedNumber,
  formatYen,
  initialSalonAct,
  type SalonAct,
} from "../../utils/salonView";
import MainLayout from "../layout/MainLayout";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import SalonBgmControl from "./SalonBgmControl";
import SalonPortrait from "./SalonPortrait";

const ACTS: readonly SalonAct[] = ["counsel", "styling", "reveal", "checkout"];

const SALON_TRANSPARENT_PORTRAIT_KEY = "salon_transparent_portrait";

/** お披露目の時点の施術前後の画像。会計でゲームのセッションを手放した後も見せる */
interface RevealFrame {
  before: string | null;
  after: string | null;
  feeling: string;
  emphasizeHints: boolean;
}

/**
 * 接客(/salon/:runId/visits/:visitId)。ADV 風のステージとメッセージ窓で、
 * カウンセリング → 施術 → お披露目 → 会計 の4幕を進める。手番は通常のプレイと
 * 同じ送信処理(usePlayTurn)で送り、満足度の数字は会計まで見せない。
 */
export default function SalonServing({
  runId,
  visitId,
}: {
  runId: string;
  visitId: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const {
    activeRun,
    busy,
    error: salonError,
    openRun,
    startVisit,
    checkoutVisit,
  } = useSalon();
  const { state: game, askRequestQuestion, setError: setGameError } = useGame();
  const { state: chat, setInputText } = useChat();
  const playTurn = usePlayTurn();
  const transformRequest = useTransformRequest(playTurn);
  const [act, setAct] = useState<SalonAct | null>(null);
  const [blocked, setBlocked] = useState<"notFound" | "closed" | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [windowHidden, setWindowHidden] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [reveal, setReveal] = useState<RevealFrame | null>(null);
  const [checkedOut, setCheckedOut] = useState<SalonVisit | null>(null);
  const startedRef = useRef<string | null>(null);
  const language = settingsState.language;
  // お客様の背景を透過してサロンの背景に立たせる。白い服が欠けるなど合わないときは切れる
  const [transparentPortrait, setTransparentPortrait] =
    usePersistedState<boolean>(SALON_TRANSPARENT_PORTRAIT_KEY, true, {
      deserialize: (raw) => {
        const value = JSON.parse(raw);
        if (typeof value !== "boolean") throw new Error("invalid");
        return value;
      },
    });
  // 幕に合わせた BGM。曲がまだ置かれていなければ鳴らさない(シナリオの曲へは倒さない)
  const bgm = useAdventureBgm(
    blocked
      ? null
      : act === "reveal" || act === "checkout"
        ? "salon_reveal"
        : "salon_serving",
    { fallbackToDefault: false },
  );

  // 開いた来店の接客を1度だけ始める(接客中なら同じセッションに戻る)
  useEffect(() => {
    const key = `${runId}:${visitId}`;
    if (startedRef.current === key) return;
    startedRef.current = key;
    void (async () => {
      const loaded = activeRun?.id === runId ? activeRun : await openRun(runId);
      if (!loaded) return;
      const target = loaded.visits.find((item) => item.id === visitId);
      if (!target) {
        setBlocked("notFound");
        return;
      }
      if (target.status === "done") {
        setCheckedOut(target);
        setAct("checkout");
        return;
      }
      if (
        target.status === "declined" ||
        target.week !== loaded.week ||
        loaded.status !== "active"
      ) {
        setBlocked("closed");
        return;
      }
      const started = await startVisit(runId, visitId);
      if (started) setAct(initialSalonAct(started.request));
    })();
  }, [activeRun, openRun, runId, startVisit, visitId]);

  const backToOffice = () => navigate(getSalonRunPath(runId));
  const visit = activeRun?.visits.find((item) => item.id === visitId) ?? null;
  const customerName = visit?.customer.name ?? "";

  if (blocked) {
    return (
      <MainLayout variant="salon">
        <div className="salon-page">
          <p className="salon-empty">{t(`salon.serving.${blocked}`)}</p>
          <button type="button" className="salon-button" onClick={backToOffice}>
            {t("salon.serving.back")}
          </button>
        </div>
      </MainLayout>
    );
  }

  const request = act && act !== "checkout" ? game.request : null;
  const turnsUsed = request?.turns_used ?? 0;
  const turnsRemaining = request?.turns_remaining ?? null;
  const questionsRemaining = request?.questions_remaining ?? 0;
  const latest = game.history.at(-1);
  // やさしい・ふつうの来店では、心境の中のヒントの一文に目印が付いている
  const emphasizeHints = Boolean(request?.emphasize_hints);
  const feeling = game.isTransforming
    ? game.feelingText
    : turnsUsed > 0
      ? latest?.feelingText || game.feelingText
      : "";
  const instruction = chat.inputText;
  const canStyle =
    !game.isTransforming &&
    turnsRemaining !== 0 &&
    instruction.trim().length > 0;

  const handleAsk = async () => {
    const text = question.trim();
    if (!text) return;
    setAsking(true);
    setQuestionError(null);
    try {
      await askRequestQuestion(text);
      setQuestion("");
    } catch (caught) {
      setQuestionError(
        caught instanceof Error ? caught.message : String(caught),
      );
    } finally {
      setAsking(false);
    }
  };

  const handleStyle = () => {
    const message = instruction.trim();
    if (!canStyle || !message) return;
    setGameError(null);
    setInputText("");
    transformRequest.submitTransform(
      message,
      "dress_up",
      false,
      `salon-${visitId}-${Date.now()}`,
    );
  };

  const handleReveal = () => {
    setReveal({
      before: game.history[0]?.imageUrl ?? null,
      after: game.currentImage,
      feeling: latest?.feelingText ?? "",
      emphasizeHints,
    });
    setAct("reveal");
  };

  const handleCheckout = async () => {
    const done = await checkoutVisit(visitId);
    if (done) {
      setCheckedOut(done);
      setAct("checkout");
    }
  };

  const showPair = (act === "reveal" || act === "checkout") && reveal;
  const actIndex = act ? ACTS.indexOf(act) : -1;

  return (
    <MainLayout variant="salon">
      <div className="salon-serving">
        <header className="salon-hud">
          <button
            type="button"
            className="salon-hud__back"
            aria-label={t("salon.serving.back")}
            title={t("salon.serving.back")}
            onClick={backToOffice}
          >
            ←
          </button>
          <div className="salon-hud__title">
            <h1>{customerName}</h1>
            {activeRun && visit && (
              <p>
                {t("salon.serving.hudWeek", {
                  week: visit.week,
                  salon: activeRun.name,
                })}
              </p>
            )}
          </div>
          {request && (
            <>
              <div className="salon-hud__tile">
                <span>{t("salon.serving.turns")}</span>
                <strong>
                  {t("salon.serving.remaining", {
                    remaining: turnsRemaining ?? "∞",
                    limit: request.turn_limit ?? "∞",
                  })}
                </strong>
              </div>
              <div className="salon-hud__tile">
                <span>{t("salon.serving.questions")}</span>
                <strong>
                  {t("salon.serving.remaining", {
                    remaining: questionsRemaining,
                    limit: request.question_limit,
                  })}
                </strong>
              </div>
            </>
          )}
          {settingsState.showCost && (
            <div className="salon-hud__tile" title={t("gameplay.apiCost")}>
              <span>{t("gameplay.apiCost")}</span>
              <strong>${settingsState.totalCost.toFixed(4)}</strong>
            </div>
          )}
          <label
            className="salon-hud__tile salon-hud__toggle"
            title={t("salon.serving.transparentHint")}
          >
            <span>{t("salon.serving.transparent")}</span>
            <input
              type="checkbox"
              className="salon-toggle__input"
              checked={transparentPortrait}
              aria-label={t("salon.serving.transparentHint")}
              onChange={(event) => setTransparentPortrait(event.target.checked)}
            />
            <span className="salon-toggle__switch" aria-hidden />
          </label>
          <SalonBgmControl bgm={bgm} />
        </header>

        <div className="salon-stage">
          <div className="salon-stage__backdrop" aria-hidden />
          {showPair ? (
            <div className="salon-stage__pair">
              <figure>
                {reveal.before && (
                  <SalonPortrait
                    src={reveal.before}
                    alt=""
                    transparent={transparentPortrait}
                  />
                )}
                <figcaption>{t("salon.serving.revealBefore")}</figcaption>
              </figure>
              <figure>
                {reveal.after && (
                  <SalonPortrait
                    src={reveal.after}
                    alt=""
                    transparent={transparentPortrait}
                  />
                )}
                <figcaption>{t("salon.serving.revealAfter")}</figcaption>
              </figure>
            </div>
          ) : game.currentImage && act && act !== "checkout" ? (
            <SalonPortrait
              className={`salon-stage__image${game.isTransforming ? " is-generating" : ""}`}
              src={game.currentImage}
              alt={customerName}
              transparent={transparentPortrait}
            />
          ) : null}
        </div>

        <section
          className={`salon-window${windowHidden ? " is-hidden" : ""}`}
          aria-live="polite"
          inert={windowHidden}
        >
          <div className="salon-window__meta">
            <ol className="salon-acts">
              {ACTS.map((item, index) => (
                <li
                  key={item}
                  className={
                    index === actIndex
                      ? "is-current"
                      : index < actIndex
                        ? "is-done"
                        : undefined
                  }
                  aria-current={index === actIndex ? "step" : undefined}
                >
                  {t(`salon.serving.acts.${item}`)}
                </li>
              ))}
            </ol>
            <button
              type="button"
              className="salon-window__log-button"
              onClick={() => setLogOpen(true)}
              disabled={!request}
            >
              {t("salon.serving.log")}
            </button>
            <button
              type="button"
              className="salon-window__hide-button"
              aria-label={t("salon.serving.hide")}
              title={t("salon.serving.hide")}
              onClick={() => setWindowHidden(true)}
            >
              ✕
            </button>
          </div>

          <div className="salon-window__text">
            {act === null && (
              <p className="salon-progress" role="status">
                <span className="salon-spinner" aria-hidden />
                {t("salon.serving.preparing")}
              </p>
            )}
            {act === "counsel" && request && (
              <>
                {visit?.returning_look && (
                  <p className="salon-window__note">
                    {t("salon.serving.returningLook")}
                  </p>
                )}
                <p className="salon-window__speaker">{customerName}</p>
                <p className="salon-window__line">「{request.wish}」</p>
                {request.questions.map((item) => (
                  <div
                    key={`${item.question}\n${item.answer}`}
                    className="salon-qa"
                  >
                    <p className="salon-qa__question">{item.question}</p>
                    <p className="salon-window__line">「{item.answer}」</p>
                  </div>
                ))}
                <p className="salon-window__note">
                  {t("salon.serving.counselHint")}
                </p>
              </>
            )}
            {act === "styling" && (
              <>
                <p className="salon-window__speaker">{customerName}</p>
                {feeling ? (
                  <SalonFeelingText
                    className="salon-window__line"
                    text={feeling}
                    emphasizeHints={emphasizeHints}
                  />
                ) : game.isTransforming ? null : (
                  <p className="salon-window__note">
                    {t("salon.serving.waiting")}
                  </p>
                )}
                {!game.isTransforming && turnsUsed > 0 && request?.hint && (
                  <p className="salon-window__hint">
                    <span>{t("salon.serving.reaction")}</span>
                    {request.hint}
                  </p>
                )}
              </>
            )}
            {act === "reveal" && reveal && (
              <>
                <p className="salon-window__speaker">{customerName}</p>
                {reveal.feeling && (
                  <SalonFeelingText
                    className="salon-window__line"
                    text={reveal.feeling}
                    emphasizeHints={reveal.emphasizeHints}
                  />
                )}
                <p className="salon-window__note">
                  {t("salon.serving.revealHint")}
                </p>
              </>
            )}
            {act === "checkout" && checkedOut && (
              <>
                <p className="salon-window__speaker">
                  {checkedOut.customer.name}
                </p>
                <p className="salon-window__label">
                  {t("salon.serving.review")}
                </p>
                <p className="salon-window__line">「{checkedOut.review}」</p>
              </>
            )}
          </div>

          <div className="salon-window__panel">
            {(salonError || game.error || questionError) && (
              <p className="salon-error" role="alert">
                {questionError || game.error || salonError}
              </p>
            )}

            {act === "counsel" && request && (
              <>
                <label className="salon-field">
                  <span>{t("salon.serving.questionLabel")}</span>
                  <textarea
                    value={question}
                    rows={2}
                    maxLength={REQUEST_QUESTION_MAX_LENGTH}
                    placeholder={t("salon.serving.questionPlaceholder")}
                    disabled={questionsRemaining === 0 || asking}
                    onChange={(event) => setQuestion(event.target.value)}
                  />
                </label>
                {asking ? (
                  <p className="salon-progress" role="status">
                    <span className="salon-spinner" aria-hidden />
                    {t("salon.serving.asking")}
                  </p>
                ) : questionsRemaining === 0 ? (
                  <p className="salon-window__note">
                    {t("salon.serving.questionsUsed")}
                  </p>
                ) : (
                  <button
                    type="button"
                    className="salon-button"
                    disabled={!question.trim()}
                    onClick={() => void handleAsk()}
                  >
                    {t("salon.serving.ask", { count: questionsRemaining })}
                  </button>
                )}
                <button
                  type="button"
                  className="salon-button salon-button--primary"
                  disabled={asking}
                  onClick={() => setAct("styling")}
                >
                  {t("salon.serving.startStyling")}
                </button>
              </>
            )}

            {act === "styling" && request && (
              <>
                {turnsRemaining === 0 ? (
                  <p className="salon-window__note">
                    {t("salon.serving.turnsUsed")}
                  </p>
                ) : (
                  <>
                    <label className="salon-field">
                      <span>{t("salon.serving.instructionLabel")}</span>
                      <textarea
                        value={instruction}
                        rows={3}
                        maxLength={INSTRUCTION_MAX_LENGTH}
                        placeholder={t("salon.serving.instructionPlaceholder")}
                        disabled={game.isTransforming}
                        onChange={(event) => setInputText(event.target.value)}
                      />
                    </label>
                    {game.isTransforming ? (
                      <p className="salon-progress" role="status">
                        <span className="salon-spinner" aria-hidden />
                        {t("salon.serving.styling")}
                      </p>
                    ) : (
                      <button
                        type="button"
                        className="salon-button salon-button--primary"
                        disabled={!canStyle}
                        onClick={handleStyle}
                      >
                        {t("salon.serving.style", {
                          count: turnsRemaining ?? 0,
                        })}
                      </button>
                    )}
                  </>
                )}
                <button
                  type="button"
                  className="salon-button"
                  disabled={turnsUsed === 0 || game.isTransforming}
                  onClick={handleReveal}
                >
                  {t("salon.serving.toReveal")}
                </button>
              </>
            )}

            {act === "reveal" &&
              (busy === "checkout" ? (
                <p className="salon-progress" role="status">
                  <span className="salon-spinner" aria-hidden />
                  {t("salon.serving.checkingOut")}
                </p>
              ) : (
                <button
                  type="button"
                  className="salon-button salon-button--primary"
                  onClick={() => void handleCheckout()}
                >
                  {t("salon.serving.checkout")}
                </button>
              ))}

            {act === "checkout" && checkedOut && (
              <>
                <dl className="salon-receipt">
                  <div>
                    <dt>{t("salon.serving.satisfaction")}</dt>
                    <dd className="salon-receipt__big">
                      {checkedOut.satisfaction ?? 0}%
                    </dd>
                  </div>
                  <div>
                    <dt>{t("salon.serving.payment")}</dt>
                    <dd>{formatYen(checkedOut.payment, language)}</dd>
                  </div>
                  <div>
                    <dt>{t("salon.serving.reputation")}</dt>
                    <dd>{formatSignedNumber(checkedOut.reputation_delta)}</dd>
                  </div>
                </dl>
                <p
                  className={`salon-receipt__verdict${checkedOut.fulfilled ? " is-fulfilled" : ""}`}
                >
                  {t(
                    checkedOut.fulfilled
                      ? "salon.serving.fulfilled"
                      : "salon.serving.notFulfilled",
                  )}
                </p>
                {(checkedOut.kept_look || !checkedOut.fulfilled) && (
                  <p className="salon-receipt__look">
                    {t(
                      checkedOut.kept_look
                        ? "salon.serving.keptLook"
                        : "salon.serving.revertedLook",
                    )}
                  </p>
                )}
                <button
                  type="button"
                  className="salon-button salon-button--primary"
                  onClick={backToOffice}
                >
                  {t("salon.serving.back")}
                </button>
              </>
            )}
          </div>
        </section>

        {windowHidden && (
          <button
            type="button"
            className="salon-window-restore"
            onClick={() => setWindowHidden(false)}
          >
            {t("salon.serving.show")}
          </button>
        )}

        {logOpen && request && (
          <aside className="salon-log" aria-label={t("salon.serving.logTitle")}>
            <header>
              <h2>{t("salon.serving.logTitle")}</h2>
              <button
                type="button"
                className="salon-button"
                onClick={() => setLogOpen(false)}
              >
                {t("salon.serving.close")}
              </button>
            </header>
            <ol>
              <li>
                <span>{customerName}</span>
                <p>「{request.wish}」</p>
              </li>
              {request.questions.map((item) => (
                <li key={`${item.question}\n${item.answer}`}>
                  <span>{t("salon.serving.logQuestion")}</span>
                  <p>{item.question}</p>
                  <p>「{item.answer}」</p>
                </li>
              ))}
              {game.history.slice(1).map((item) => (
                <li key={item.id}>
                  <span>{t("salon.serving.logInstruction")}</span>
                  <p>{item.instruction}</p>
                  {item.feelingText && (
                    <SalonFeelingText
                      text={item.feelingText}
                      emphasizeHints={emphasizeHints}
                    />
                  )}
                </li>
              ))}
            </ol>
          </aside>
        )}
      </div>

      {/* 精密参照の Anlas 追加消費の確認(通常のプレイ画面と同じ) */}
      <AnlasConfirmDialog
        open={transformRequest.anlasConfirmPending !== null}
        body={
          <Trans
            i18nKey="gameplay.anlasPreciseReferenceBody"
            values={{
              cost: transformRequest.anlasConfirmPending?.anlasCost ?? 0,
            }}
            components={{ strong: <strong /> }}
          />
        }
        onConfirm={transformRequest.handleAnlasConfirm}
        onCancel={transformRequest.handleAnlasCancel}
      />
      <AnlasConfirmDialog
        open={transformRequest.usageWarnPending !== null}
        body={t("gameplay.v5UsageExhaustedBody")}
        onConfirm={transformRequest.handleUsageWarnConfirm}
        onCancel={transformRequest.handleUsageWarnCancel}
      />
    </MainLayout>
  );
}

/**
 * お客様の心境。emphasizeHints なら目印で囲まれたヒントの一文を強調し、
 * そうでなければ目印を取り除いて表示する。
 */
function SalonFeelingText({
  text,
  emphasizeHints,
  className,
}: {
  text: string;
  emphasizeHints: boolean;
  className?: string;
}) {
  if (!emphasizeHints) {
    return <p className={className}>{stripHintMarkers(text)}</p>;
  }
  let offset = 0;
  const segments = splitHintMarkers(text).map((segment) => {
    const key = offset;
    offset += segment.text.length + 1;
    return { ...segment, key };
  });
  return (
    <p className={className}>
      {segments.map((segment) =>
        segment.hint ? (
          <strong key={segment.key} className="salon-hint-mark">
            {segment.text}
          </strong>
        ) : (
          <Fragment key={segment.key}>{segment.text}</Fragment>
        ),
      )}
    </p>
  );
}
