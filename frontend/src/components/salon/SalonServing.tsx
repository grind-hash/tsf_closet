import {
  Fragment,
  type RefObject,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
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
import { useCountUp } from "../../hooks/useCountUp";
import { useInsertAtCaret } from "../../hooks/useInsertAtCaret";
import { usePersistedState } from "../../hooks/usePersistedState";
import { usePlayTurn } from "../../hooks/usePlayTurn";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import {
  type TransformHandler,
  useTransformRequest,
} from "../../hooks/useTransformRequest";
import { getSalonRunPath } from "../../routes";
import { splitHintMarkers, stripHintMarkers } from "../../utils/hintMarkers";
import {
  type ExperienceFrame,
  formatYen,
  initialSalonAct,
  isAdultSalonTurn,
  isExperienceTurn,
  lastStyledHistory,
  type SalonAct,
  settleExperience,
} from "../../utils/salonView";
import { FavoritePromptInsertButton } from "../favoritePrompts/FavoritePromptButtons";
import ComparisonSliderModal from "../gallery/ComparisonSliderModal";
import InpaintModal from "../InpaintModal";
import MainLayout from "../layout/MainLayout";
import AnlasConfirmDialog from "../ui/AnlasConfirmDialog";
import ConfirmDialog from "../ui/ConfirmDialog";
import SalonBgmControl from "./SalonBgmControl";
import SalonGenerationSettings from "./SalonGenerationSettings";
import SalonPortrait from "./SalonPortrait";
import SalonReceipt, { RECEIPT_CASH_ARRIVAL_MS } from "./SalonReceipt";

const ACTS: readonly SalonAct[] = ["counsel", "styling", "reveal", "checkout"];

const SALON_TRANSPARENT_PORTRAIT_KEY = "salon_transparent_portrait";

/**
 * 施術する範囲(インペイントのマスク)。来店ごとに持ち、通常プレイのマスクとは
 * 共有しない(別の画像のために描いたマスクがお客様にかからないように)
 */
interface StylingRange {
  visitId: string;
  maskDataUrl: string;
  maskId: string | null;
  /** システムマスク・プリセットマスクの名前。手描きは null */
  name: string | null;
}

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
  const { state: settingsState, setInpaintSettings } = useSettings();
  const {
    activeRun,
    busy,
    error: salonError,
    openRun,
    startVisit,
    buyExtraTurn,
    checkoutVisit,
    soundEffects,
  } = useSalon();
  const { state: game, askRequestQuestion, setError: setGameError } = useGame();
  const { state: chat, setInputText } = useChat();
  const playTurn = usePlayTurn();
  const adultTurn = isAdultSalonTurn(game.request, settingsState.nsfwMode);
  const isNovelAI = settingsState.imageProvider === "novelai";
  const [rangeState, setRangeState] = useState<StylingRange | null>(null);
  const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
  // 別のお客様へ移ったら、前のお客様のために選んだ範囲は使わない
  const range = rangeState?.visitId === visitId ? rangeState : null;
  // マスクを使えるのは NovelAI だけ
  const activeRange = isNovelAI ? range : null;
  const salonTurn = useCallback<TransformHandler>(
    (
      instruction,
      costumeImage,
      transformationType,
      options,
      instructionType,
      ...rest
    ) =>
      playTurn(
        instruction,
        costumeImage,
        transformationType,
        {
          ...options,
          nsfwMode: adultTurn,
          // マスクは接客画面で選んだ範囲だけを送り、通常プレイのマスクは使わない。
          // 体験の場面は構図が変わるため、範囲を選んでいても全体を描く
          maskImage:
            instructionType === "action" ? undefined : activeRange?.maskDataUrl,
          maskId:
            instructionType === "action"
              ? undefined
              : (activeRange?.maskId ?? undefined),
          // 体験の場面(行動の手番)は、主人公と相手役のタグを書き分けて描く。
          // 混ざると主人公の髪型などが相手役へ移り、主人公の性別が入れ替わって見える
          ...(instructionType === "action"
            ? { enableMultiplePeople: true }
            : {}),
        },
        instructionType,
        ...rest,
      ),
    [playTurn, adultTurn, activeRange],
  );
  const transformRequest = useTransformRequest(salonTurn);
  const [act, setAct] = useState<SalonAct | null>(null);
  const [blocked, setBlocked] = useState<"notFound" | "closed" | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [windowHidden, setWindowHidden] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [reveal, setReveal] = useState<RevealFrame | null>(null);
  const [experience, setExperience] = useState<ExperienceFrame | null>(null);
  const [fallbackNotice, setFallbackNotice] = useState(false);
  const [checkedOut, setCheckedOut] = useState<SalonVisit | null>(null);
  // この画面で会計したときだけ演出する(済んだ来店を開き直したときは立てない)
  const [celebrate, setCelebrate] = useState(false);
  const cashTileRef = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const playSound = soundEffects.play;
  const [extraOpen, setExtraOpen] = useState(false);
  const startedRef = useRef<string | null>(null);
  // 体験の手番を送った時点の履歴の件数・現在の画像と、送信後に生成中になったか
  const experienceBaseRef = useRef(0);
  const experienceBaseImageRef = useRef<string | null>(null);
  const experienceSeenRef = useRef(false);
  const instructionId = useId();
  const instructionRef = useRef<HTMLTextAreaElement>(null);
  const insertFavoritePrompt = useInsertAtCaret(
    instructionRef,
    chat.inputText,
    setInputText,
    " ",
  );
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
  // 上端バーのパネル(♪ / ⚙)。重ならないよう同時には1つだけ開く
  const [hudPanel, setHudPanel] = useState<"bgm" | "generation" | null>(null);
  const setBgmOpen = useCallback(
    (next: boolean) => setHudPanel(next ? "bgm" : null),
    [],
  );
  const setGenerationOpen = useCallback(
    (next: boolean) => setHudPanel(next ? "generation" : null),
    [],
  );
  // 幕に合わせた BGM。曲がまだ置かれていなければ鳴らさない(シナリオの曲へは倒さない)
  const bgm = useAdventureBgm(
    blocked
      ? null
      : act === "reveal" || act === "checkout"
        ? "salon_reveal"
        : "salon_serving",
    { fallbackToDefault: false, prefsScope: "salon" },
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
      if (!started) return;
      setFallbackNotice(Boolean(started.request?.sensitive_fallback));
      setAct(initialSalonAct(started.request));
    })();
  }, [activeRun, openRun, runId, startVisit, visitId]);

  // 体験の手番の終わりを見届ける。送信直後はまだ生成中になっていないことがあるので、
  // 一度生成中になったのを見てから、画像が届いたか(成功)どうかで決める
  useEffect(() => {
    if (experience?.status !== "generating") return;
    if (game.isTransforming) {
      experienceSeenRef.current = true;
      return;
    }
    if (!experienceSeenRef.current) return;
    experienceSeenRef.current = false;
    setExperience(
      settleExperience({
        history: game.history,
        baseLength: experienceBaseRef.current,
        baseImage: experienceBaseImageRef.current,
        currentImage: game.currentImage,
        feelingText: game.feelingText,
      }),
    );
  }, [
    experience?.status,
    game.isTransforming,
    game.history,
    game.currentImage,
    game.feelingText,
  ]);

  // 確認ダイアログの返事: 確定なら生成中に、取り消しなら失敗(やり直せる)にする
  const anlasPending = transformRequest.anlasConfirmPending;
  const usagePending = transformRequest.usageWarnPending;
  useEffect(() => {
    if (experience?.status !== "confirming" || anlasPending || usagePending) {
      return;
    }
    if (game.isTransforming) {
      experienceSeenRef.current = true;
      setExperience({ status: "generating", image: null, feeling: "" });
    } else {
      setExperience({ status: "failed", image: null, feeling: "" });
    }
  }, [experience?.status, anlasPending, usagePending, game.isTransforming]);

  // 体験の場面まで済んだ来店に戻ってきたら、お披露目から再開する
  useEffect(() => {
    if (act !== "styling" || !game.request?.sensitive || game.isTransforming) {
      return;
    }
    const latestItem = game.history.at(-1);
    if (!isExperienceTurn(latestItem)) return;
    const styled = lastStyledHistory(game.history);
    setReveal({
      before: game.history[0]?.imageUrl ?? null,
      after: styled?.imageUrl ?? null,
      feeling: styled?.feelingText ?? "",
      emphasizeHints: Boolean(game.request.emphasize_hints),
    });
    setExperience({
      status: "done",
      image: latestItem?.imageUrl ?? null,
      feeling: latestItem?.feelingText ?? "",
    });
    setAct("reveal");
  }, [act, game.request, game.isTransforming, game.history]);

  const backToOffice = () => navigate(getSalonRunPath(runId));
  const visit = activeRun?.visits.find((item) => item.id === visitId) ?? null;
  const customerName = visit?.customer.name ?? "";

  // 会計したら、支払いのチップが HUD の現金に届くところでレジの音を鳴らす
  useEffect(() => {
    if (!celebrate || !checkedOut || checkedOut.payment <= 0) return;
    const timer = window.setTimeout(
      () => playSound("register"),
      reducedMotion ? 0 : RECEIPT_CASH_ARRIVAL_MS,
    );
    return () => window.clearTimeout(timer);
  }, [celebrate, checkedOut, reducedMotion, playSound]);

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
  // 資金で足した施術の手番では、最後のヒント(反応のヒントと心境の中の強調)を出さない
  const extraTurnShown =
    (visit?.extra_cost ?? 0) > 0 &&
    (game.isTransforming || turnsRemaining === 0);
  const emphasizeHints = Boolean(request?.emphasize_hints) && !extraTurnShown;
  const extraPrice = activeRun?.extra_turn_price ?? 0;
  const canBuyExtra =
    activeRun !== null &&
    visit !== null &&
    visit.extra_cost < extraPrice * activeRun.extra_turns_max;
  const extraAffordable = activeRun !== null && activeRun.cash >= extraPrice;
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
  // 施術の幕で1手以上施術したあとだけ見比べられる。比較の一覧は夢の場面と施術の
  // 手番を見分けられないため、夢の場面を描いた後(お披露目以降・その後の再訪)は閉じる
  const canCompare =
    act === "styling" &&
    !game.isTransforming &&
    Boolean(game.sessionId) &&
    game.history.length > 1 &&
    !game.history.some(isExperienceTurn);

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

  /** 願いの姿でしたいことを、行動の手番として1回だけ描く */
  const startExperience = (direction: string) => {
    experienceBaseRef.current = game.history.length;
    experienceBaseImageRef.current = game.currentImage;
    experienceSeenRef.current = false;
    setGameError(null);
    const sent = transformRequest.submitTransform(
      direction,
      "action",
      false,
      `salon-experience-${visitId}-${Date.now()}`,
    );
    setExperience({
      status: sent ? "generating" : "confirming",
      image: null,
      feeling: "",
    });
  };

  const handleReveal = () => {
    const styled = lastStyledHistory(game.history);
    setReveal({
      before: game.history[0]?.imageUrl ?? null,
      after: styled?.imageUrl ?? game.currentImage,
      feeling: styled?.feelingText ?? latest?.feelingText ?? "",
      emphasizeHints,
    });
    setAct("reveal");
    if (request?.sensitive && request.experience) {
      startExperience(request.experience);
    }
  };

  const handleCheckout = async () => {
    // 現金が増える前に立て、HUD の現金をチップが届くまで待たせる
    setCelebrate(true);
    const done = await checkoutVisit(visitId);
    if (done) {
      setCheckedOut(done);
      setAct("checkout");
    } else {
      setCelebrate(false);
    }
  };

  const showPair = (act === "reveal" || act === "checkout") && reveal;
  const actIndex = act ? ACTS.indexOf(act) : -1;
  const experienceBusy =
    experience?.status === "confirming" || experience?.status === "generating";
  const experienceFeeling =
    experience?.status === "generating"
      ? game.feelingText
      : (experience?.feeling ?? "");

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
          {activeRun?.id === runId && (
            <SalonHudCash
              key={activeRun.id}
              cash={activeRun.cash}
              language={language}
              delayMs={celebrate ? RECEIPT_CASH_ARRIVAL_MS : 0}
              deferred={Boolean(request)}
              tileRef={cashTileRef}
            />
          )}
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
          <SalonGenerationSettings
            open={hudPanel === "generation"}
            onOpenChange={setGenerationOpen}
          />
          <SalonBgmControl
            bgm={bgm}
            open={hudPanel === "bgm"}
            onOpenChange={setBgmOpen}
          />
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
              {experience && experience.status !== "failed" && (
                <figure className="salon-stage__experience">
                  {experience.image ? (
                    <img src={experience.image} alt="" />
                  ) : (
                    <span className="salon-stage__experience-wait">
                      <span className="salon-spinner" aria-hidden />
                    </span>
                  )}
                  <figcaption>{t("salon.serving.experience")}</figcaption>
                </figure>
              )}
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
              onClick={() => setCompareOpen(true)}
              disabled={!canCompare}
              title={t("salon.serving.compareHint")}
            >
              {t("salon.serving.compare")}
            </button>
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
              aria-label={t("common.messageWindow.hide")}
              title={t("common.messageWindow.hide")}
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
                {fallbackNotice && (
                  <p className="salon-window__note">
                    {t("salon.serving.sensitiveFallback")}
                  </p>
                )}
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
                {asking && (
                  <div className="salon-qa">
                    <p className="salon-qa__question">{question.trim()}</p>
                    <SalonTyping name={customerName} />
                  </div>
                )}
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
                    streaming={game.isTransforming}
                  />
                ) : game.isTransforming ? (
                  <SalonTyping name={customerName} />
                ) : (
                  <p className="salon-window__note">
                    {t("salon.serving.waiting")}
                  </p>
                )}
                {!game.isTransforming &&
                  turnsUsed > 0 &&
                  request?.hint &&
                  !extraTurnShown && (
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
                {(experienceFeeling || experienceBusy) && (
                  <>
                    <p className="salon-window__label">
                      {t("salon.serving.experience")}
                    </p>
                    {experienceFeeling ? (
                      <p className="salon-window__line">
                        {experienceFeeling}
                        {experience?.status === "generating" &&
                          game.isTransforming && (
                            <span className="salon-caret" aria-hidden />
                          )}
                      </p>
                    ) : (
                      <SalonTyping name={customerName} />
                    )}
                  </>
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
                  <>
                    <p className="salon-window__note">
                      {t("salon.serving.turnsUsed")}
                    </p>
                    {canBuyExtra &&
                      (busy === "extra" ? (
                        <p className="salon-progress" role="status">
                          <span className="salon-spinner" aria-hidden />
                          {t("salon.serving.extraTurnBuying")}
                        </p>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="salon-button"
                            disabled={!extraAffordable || busy !== null}
                            onClick={() => setExtraOpen(true)}
                          >
                            {t("salon.serving.extraTurn", {
                              price: formatYen(extraPrice, language),
                            })}
                          </button>
                          <p className="salon-window__note">
                            {extraAffordable
                              ? t("salon.serving.extraTurnHint")
                              : t("salon.serving.extraTurnNoCash")}
                          </p>
                        </>
                      ))}
                  </>
                ) : (
                  <>
                    <div className="salon-field">
                      <div className="salon-field__head">
                        <label htmlFor={instructionId}>
                          {t("salon.serving.instructionLabel")}
                        </label>
                        <div className="salon-field__actions">
                          <FavoritePromptInsertButton
                            onInsert={insertFavoritePrompt}
                            className="salon-field__favorite"
                            disabled={game.isTransforming}
                          />
                          <button
                            type="button"
                            className="salon-field__range"
                            disabled={game.isTransforming || !game.currentImage}
                            onClick={() => setRangeEditorOpen(true)}
                          >
                            {t("salon.serving.rangeSelect")}
                          </button>
                        </div>
                      </div>
                      {range && (
                        <div className="salon-range-chip">
                          <span>
                            {t("salon.serving.rangeChip", {
                              name:
                                range.name ?? t("salon.serving.rangeHandDrawn"),
                            })}
                          </span>
                          <button
                            type="button"
                            aria-label={t("salon.serving.rangeClear")}
                            title={t("salon.serving.rangeClear")}
                            disabled={game.isTransforming}
                            onClick={() => setRangeState(null)}
                          >
                            ✕
                          </button>
                        </div>
                      )}
                      {!isNovelAI && (
                        <p className="salon-field__hint">
                          {t("salon.serving.rangeNovelaiOnly")}
                        </p>
                      )}
                      <textarea
                        id={instructionId}
                        ref={instructionRef}
                        value={instruction}
                        rows={3}
                        maxLength={INSTRUCTION_MAX_LENGTH}
                        placeholder={t("salon.serving.instructionPlaceholder")}
                        disabled={game.isTransforming}
                        onChange={(event) => setInputText(event.target.value)}
                      />
                    </div>
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
                        {t(
                          activeRange
                            ? "salon.serving.styleRange"
                            : "salon.serving.style",
                          { count: turnsRemaining ?? 0 },
                        )}
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

            {act === "reveal" && experienceBusy && (
              <p className="salon-progress" role="status">
                <span className="salon-spinner" aria-hidden />
                {t("salon.serving.experienceGenerating")}
              </p>
            )}
            {act === "reveal" &&
              experience?.status === "failed" &&
              request?.experience && (
                <>
                  <p className="salon-window__note">
                    {t("salon.serving.experienceFailed")}
                  </p>
                  <button
                    type="button"
                    className="salon-button"
                    disabled={busy !== null}
                    onClick={() =>
                      request.experience && startExperience(request.experience)
                    }
                  >
                    {t("salon.serving.experienceRetry")}
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
                  disabled={experienceBusy}
                  onClick={() => void handleCheckout()}
                >
                  {t("salon.serving.checkout")}
                </button>
              ))}

            {act === "checkout" && checkedOut && (
              <>
                <SalonReceipt
                  visit={checkedOut}
                  language={language}
                  celebrate={celebrate}
                  cashTarget={cashTileRef}
                />
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
            {t("common.messageWindow.show")}
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
                  <span>
                    {t(
                      isExperienceTurn(item)
                        ? "salon.serving.logExperience"
                        : "salon.serving.logInstruction",
                    )}
                  </span>
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

      <ComparisonSliderModal
        isOpen={compareOpen}
        sessionId={game.sessionId}
        initialBasis="prev"
        showPortrait={false}
        onClose={() => setCompareOpen(false)}
      />

      {rangeEditorOpen && game.currentImage && (
        <InpaintModal
          isOpen
          currentImageUrl={game.currentImage}
          initialSettings={settingsState.inpaintSettings}
          initialMaskDataUrl={range?.maskDataUrl ?? null}
          initialMaskId={range?.maskId ?? null}
          onApply={(settings, maskDataUrl, maskId, detail) => {
            // 強さなどの値は ⚙ と同じく通常プレイと共通にする
            setInpaintSettings(settings);
            setRangeState(
              maskDataUrl && !detail.empty
                ? { visitId, maskDataUrl, maskId, name: detail.name }
                : null,
            );
            setRangeEditorOpen(false);
          }}
          onClose={() => setRangeEditorOpen(false)}
        />
      )}

      <ConfirmDialog
        open={extraOpen}
        title={t("salon.serving.extraTurnTitle")}
        confirmLabel={t("salon.serving.extraTurnConfirm")}
        cancelLabel={t("common.cancel")}
        busy={busy === "extra"}
        onConfirm={() => {
          setExtraOpen(false);
          void buyExtraTurn(visitId);
        }}
        onCancel={() => setExtraOpen(false)}
      >
        {t("salon.serving.extraTurnBody", {
          price: formatYen(extraPrice, language),
          cash: formatYen(activeRun?.cash ?? 0, language),
          after: formatYen((activeRun?.cash ?? 0) - extraPrice, language),
        })}
      </ConfirmDialog>

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

/** お客様の言葉を待っている間の「入力中」の表示(止まって見えないように) */
/**
 * HUD の現金。値が変わったら数え上げる(会計ではチップが届くまで delayMs 待つ)。
 * 別のサロンへ移ったときに数え上げないよう、呼び出し側でサロンごとに key を変える
 */
function SalonHudCash({
  cash,
  language,
  delayMs,
  deferred,
  tileRef,
}: {
  cash: number;
  language: string;
  delayMs: number;
  /** 施術の残り回数と並ぶ間。狭い画面では隠す */
  deferred: boolean;
  tileRef: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const shown = useCountUp(cash, { durationMs: 700, delayMs });
  // 数え終えた値。待ち時間の間は光らせず、数字が動いている間だけ光らせる
  const [settled, setSettled] = useState(cash);
  useEffect(() => {
    if (shown === cash) setSettled(cash);
  }, [shown, cash]);
  const counting = shown !== cash && shown !== settled;
  return (
    <div
      ref={tileRef}
      className={`salon-hud__tile salon-hud__cash${deferred ? " salon-hud__cash--deferred" : ""}${counting ? " is-counting" : ""}`}
    >
      <span>{t("salon.office.cash")}</span>
      <strong className={shown < 0 ? "is-negative" : undefined}>
        {formatYen(shown, language)}
      </strong>
    </div>
  );
}

function SalonTyping({ name }: { name: string }) {
  const { t } = useTranslation();
  return (
    <p
      className="salon-typing"
      role="status"
      aria-label={t("salon.serving.typing", { name })}
    >
      <span />
      <span />
      <span />
    </p>
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
  streaming = false,
}: {
  text: string;
  emphasizeHints: boolean;
  className?: string;
  /** 文字が流れている間は文末にキャレットを出す */
  streaming?: boolean;
}) {
  const caret = streaming ? <span className="salon-caret" aria-hidden /> : null;
  if (!emphasizeHints) {
    return (
      <p className={className}>
        {stripHintMarkers(text)}
        {caret}
      </p>
    );
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
      {caret}
    </p>
  );
}
