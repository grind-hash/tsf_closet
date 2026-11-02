import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { SalonWeek } from "../../apis/salon";
import { useSalon } from "../../contexts/SalonContext";
import { useCountUp } from "../../hooks/useCountUp";
import type { SalonSoundName } from "../../hooks/useSalonSoundEffects";
import {
  formatSignedNumber,
  formatSignedYen,
  formatYen,
  type SalonOpeningCutscene as OpeningScene,
  type SalonCutsceneScene,
  type SalonWeekCutscene as Scene,
} from "../../utils/salonView";

/** 開業は founding → funds → finale、週の締めは closing → ledger → (events) → finale */
type Stage = "founding" | "funds" | "closing" | "ledger" | "events" | "finale";

/** 帳簿の行を1行ずつ書き込む間隔(CSS の --row と合わせる) */
const LEDGER_ROW_MS = 280;
const CONFETTI_COUNT = 24;

interface LedgerRow {
  key:
    | "revenue"
    | "extraCost"
    | "salary"
    | "fixedCost"
    | "weeklySalary"
    | "weeklyFixedCost";
  amount: number;
}

function ledgerRows(week: SalonWeek): LedgerRow[] {
  const extraCost = week.extra_cost ?? 0;
  return [
    { key: "revenue", amount: week.revenue },
    ...(extraCost > 0
      ? [{ key: "extraCost" as const, amount: -extraCost }]
      : []),
    { key: "salary", amount: week.salary },
    { key: "fixedCost", amount: -week.fixed_cost },
  ];
}

function openingRows(scene: OpeningScene): LedgerRow[] {
  return [
    { key: "weeklySalary", amount: scene.weeklySalary },
    { key: "weeklyFixedCost", amount: -scene.weeklyFixedCost },
  ];
}

function rowStyle(row: number): CSSProperties {
  return { "--row": row } as CSSProperties;
}

function signClass(value: number): string | undefined {
  if (value === 0) return undefined;
  return value < 0 ? "is-negative" : "is-positive";
}

interface SalonCutsceneProps {
  scene: SalonCutsceneScene;
  mode: "full" | "short";
  language: string;
  /** 閉じたとき。sawAchievements が false なら実績を見せる前に閉じた(通知で補う) */
  onClose: (sawAchievements: boolean) => void;
  /** 「次から短くする」 */
  onPreferShort: () => void;
}

/**
 * サロンのカットシーン。開業(開業 → 開業の帳簿 → 開店)と、
 * 週の締め(閉店 → 帳簿 → 出来事 → 開店/決算)の2種類。
 * 自動では進まず、クリック・Space・Enter・「次へ」で1幕ずつ進む(短い版は1枚で閉じる)。
 * Esc とスキップは、残りの幕を飛ばしてすぐ閉じる。
 * 見せる数字はオーナー室の帳簿・予約・決算の表示にも残るので、飛ばしても情報は落ちない。
 */
export default function SalonCutscene({
  scene,
  mode,
  language,
  onClose,
  onPreferShort,
}: SalonCutsceneProps) {
  const { t } = useTranslation();
  const achievements = scene.kind === "week" ? scene.achievements : [];
  const result = scene.kind === "week" ? scene.result : null;
  const stages = useMemo<Stage[]>(
    () =>
      scene.kind === "opening"
        ? ["founding", "funds", "finale"]
        : [
            "closing",
            "ledger",
            ...(scene.regulars.length > 0 || scene.achievements.length > 0
              ? (["events"] as const)
              : []),
            "finale",
          ],
    [scene],
  );
  const [index, setIndex] = useState(0);
  const stage = stages[index];
  const closedRef = useRef(false);
  const nextRef = useRef<HTMLButtonElement>(null);
  const isLast = mode === "short" || index >= stages.length - 1;

  // 帳簿の幕では帳簿をめくる音、開店の幕ではドアベル。短い版は帳簿の音だけ
  const { soundEffects } = useSalon();
  const playSound = soundEffects.play;
  const stageSound: SalonSoundName | null =
    mode === "short" || stage === "funds" || stage === "ledger"
      ? "ledger"
      : stage === "finale" && !result
        ? "doorbell"
        : null;
  // 開発時の StrictMode で effect が2回走っても、1幕につき1回だけ鳴らす
  const soundedIndexRef = useRef<number | null>(null);
  useEffect(() => {
    if (!stageSound || soundedIndexRef.current === index) return;
    soundedIndexRef.current = index;
    playSound(stageSound);
  }, [stageSound, index, playSound]);

  const eventsIndex = stages.indexOf("events");
  const sawAchievements =
    achievements.length === 0 ||
    mode === "short" ||
    (eventsIndex >= 0 && index >= eventsIndex);
  const sawRef = useRef(sawAchievements);
  sawRef.current = sawAchievements;

  const close = useCallback(
    (saw: boolean) => {
      if (closedRef.current) return;
      closedRef.current = true;
      onClose(saw);
    },
    [onClose],
  );
  const skip = useCallback(() => close(sawRef.current), [close]);
  const advance = useCallback(() => {
    if (isLast) {
      close(true);
      return;
    }
    setIndex(index + 1);
    // 画面をクリックして進めたあとも、Space / Enter で続けて進められるようにする
    nextRef.current?.focus();
  }, [isLast, index, close]);

  useEffect(() => {
    nextRef.current?.focus();
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      skip();
      return;
    }
    // ボタンにフォーカスがあるときの Space / Enter は、そのボタンの操作に任せる
    const onButton = event.target instanceof HTMLButtonElement;
    if (!onButton && (event.key === " " || event.key === "Enter")) {
      event.preventDefault();
      advance();
    }
  };

  const handleNextClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    advance();
  };

  const handleSkipClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    skip();
  };

  const handlePreferShort = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onPreferShort();
    skip();
  };

  return (
    <div
      className={`salon-cutscene salon-cutscene--${mode}`}
      role="dialog"
      aria-modal="true"
      // 画面をクリックしてもフォーカスがダイアログの外へ出ず、キー操作を受け続ける
      tabIndex={-1}
      aria-label={
        scene.kind === "opening"
          ? t("salon.cutscene.founded")
          : t("salon.cutscene.label")
      }
      onClick={advance}
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        className="salon-cutscene__skip"
        onClick={handleSkipClick}
      >
        {t("salon.cutscene.skip")}
      </button>

      {/* 幕と紙吹雪は画面全体に広げるため、動きの付いた幕の外に置く */}
      {mode === "full" && stage === "finale" && !result && (
        <span className="salon-cutscene__curtain" aria-hidden />
      )}
      {mode === "full" &&
        stage === "finale" &&
        result?.outcome === "success" && <Confetti />}

      {mode === "short" ? (
        scene.kind === "opening" ? (
          <OpeningCard scene={scene} language={language} />
        ) : (
          <ShortCard scene={scene} language={language} />
        )
      ) : (
        <div
          key={stage}
          className={`salon-cutscene__stage salon-cutscene__stage--${stage}`}
          aria-live="polite"
        >
          {scene.kind === "opening" ? (
            <>
              {stage === "founding" && <FoundingStage scene={scene} />}
              {stage === "funds" && (
                <FundsStage scene={scene} language={language} />
              )}
              {stage === "finale" && (
                <OpeningNotice week={scene.week} bookings={scene.bookings} />
              )}
            </>
          ) : (
            <>
              {stage === "closing" && (
                <>
                  <p className="salon-cutscene__week">
                    {t("salon.cutscene.week", { week: scene.week.week })}
                  </p>
                  <span className="salon-cutscene__rule" aria-hidden />
                  <p className="salon-cutscene__headline">
                    {t("salon.cutscene.closed")}
                  </p>
                </>
              )}
              {stage === "ledger" && (
                <LedgerStage scene={scene} language={language} />
              )}
              {stage === "events" && <EventsStage scene={scene} />}
              {stage === "finale" && (
                <FinaleStage scene={scene} language={language} />
              )}
            </>
          )}
        </div>
      )}

      {mode === "full" && (
        <button
          type="button"
          className="salon-cutscene__prefer-short"
          onClick={handlePreferShort}
        >
          {t("salon.cutscene.preferShort")}
        </button>
      )}

      <button
        ref={nextRef}
        type="button"
        className="salon-cutscene__next"
        onClick={handleNextClick}
      >
        {isLast ? t("salon.cutscene.close") : t("salon.cutscene.next")}
        {!isLast && <span aria-hidden>▼</span>}
      </button>
    </div>
  );
}

function LedgerStage({ scene, language }: { scene: Scene; language: string }) {
  const { t } = useTranslation();
  const rows = ledgerRows(scene.week);
  const cash = useCountUp(scene.week.cash_end, {
    from: scene.cashStart,
    durationMs: 1000,
    delayMs: rows.length * LEDGER_ROW_MS + 200,
  });
  const reputationEnd = scene.week.reputation_end;
  return (
    <>
      <h2 className="salon-cutscene__title">
        {t("salon.cutscene.ledgerTitle", { week: scene.week.week })}
      </h2>
      <p className="salon-cutscene__sub">
        {t("salon.cutscene.served", {
          served: scene.week.served,
          declined: scene.week.declined,
        })}
      </p>
      <dl className="salon-cutscene__ledger">
        {rows.map((row, rowIndex) => (
          <div key={row.key} style={rowStyle(rowIndex)}>
            <dt>{t(`salon.cutscene.${row.key}`)}</dt>
            <dd className={signClass(row.amount)}>
              {formatSignedYen(row.amount, language)}
            </dd>
          </div>
        ))}
      </dl>
      <div className="salon-cutscene__total" style={rowStyle(rows.length)}>
        <span>{t("salon.cutscene.cashEnd")}</span>
        <strong className={cash < 0 ? "is-negative" : undefined}>
          {formatYen(cash, language)}
        </strong>
        <em className={signClass(scene.cashDelta)}>
          {formatSignedYen(scene.cashDelta, language)}
        </em>
      </div>
      <div
        className="salon-cutscene__reputation"
        style={rowStyle(rows.length + 1)}
      >
        <span>{t("salon.cutscene.reputation")}</span>
        <strong>
          {reputationEnd}
          <small>/ 100</small>
        </strong>
        <em className={signClass(reputationEnd - scene.reputationStart)}>
          {formatSignedNumber(reputationEnd - scene.reputationStart)}
        </em>
        <span
          className="salon-cutscene__meter"
          style={
            {
              "--from": `${scene.reputationStart}%`,
              "--to": `${reputationEnd}%`,
            } as CSSProperties
          }
          aria-hidden
        >
          <span />
        </span>
      </div>
    </>
  );
}

function EventsStage({ scene }: { scene: Scene }) {
  const { t } = useTranslation();
  return (
    <ul className="salon-cutscene__events">
      {scene.regulars.map((name, rowIndex) => (
        <li key={`regular-${name}`} style={rowStyle(rowIndex)}>
          {t("salon.cutscene.regular", { name })}
        </li>
      ))}
      {scene.achievements.map((achievement, rowIndex) => (
        <li
          key={achievement.achievement_id}
          className="salon-cutscene__achievement"
          style={rowStyle(scene.regulars.length + rowIndex)}
        >
          <span aria-hidden>{achievement.icon}</span>
          <span>
            <small>{t("salon.cutscene.achievement")}</small>
            <strong>{achievement.name}</strong>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 開業: サロンの名前と「開業」、経営の期間 */
function FoundingStage({ scene }: { scene: OpeningScene }) {
  const { t } = useTranslation();
  return (
    <>
      <p className="salon-cutscene__week salon-cutscene__name">{scene.name}</p>
      <span className="salon-cutscene__rule" aria-hidden />
      <p className="salon-cutscene__headline">{t("salon.cutscene.founded")}</p>
      <p className="salon-cutscene__sub">
        {t("salon.cutscene.term", { weeks: scene.totalWeeks })}
      </p>
    </>
  );
}

/** 開業の帳簿: 開業資金を数え上げ、毎週の収支・評判・成功の条件を書き込む */
function FundsStage({
  scene,
  language,
}: {
  scene: OpeningScene;
  language: string;
}) {
  const { t } = useTranslation();
  const rows = openingRows(scene);
  const cash = useCountUp(scene.initialCash, {
    from: 0,
    durationMs: 1000,
    delayMs: 300,
  });
  return (
    <>
      <h2 className="salon-cutscene__title">
        {t("salon.cutscene.openingLedgerTitle")}
      </h2>
      <div className="salon-cutscene__total" style={rowStyle(0)}>
        <span>{t("salon.cutscene.initialCash")}</span>
        <strong>{formatYen(cash, language)}</strong>
      </div>
      <dl className="salon-cutscene__ledger">
        {rows.map((row, rowIndex) => (
          <div key={row.key} style={rowStyle(rowIndex + 1)}>
            <dt>{t(`salon.cutscene.${row.key}`)}</dt>
            <dd className={signClass(row.amount)}>
              {formatSignedYen(row.amount, language)}
            </dd>
          </div>
        ))}
      </dl>
      <div
        className="salon-cutscene__reputation"
        style={rowStyle(rows.length + 1)}
      >
        <span>{t("salon.cutscene.reputation")}</span>
        <strong>
          {scene.reputation}
          <small>/ 100</small>
        </strong>
        <span
          className="salon-cutscene__meter"
          style={
            {
              "--from": "0%",
              "--to": `${scene.reputation}%`,
            } as CSSProperties
          }
          aria-hidden
        >
          <span />
        </span>
      </div>
      <p
        className="salon-cutscene__sub salon-cutscene__goal"
        style={rowStyle(rows.length + 2)}
      >
        {t("salon.cutscene.goal", { weeks: scene.totalWeeks })}
      </p>
    </>
  );
}

/** 開店の幕(第N週・開店・予約数)。開業と、営業を続ける週の締めで共通 */
function OpeningNotice({ week, bookings }: { week: number; bookings: number }) {
  const { t } = useTranslation();
  return (
    <div className="salon-cutscene__opening">
      <p className="salon-cutscene__week">
        {t("salon.cutscene.week", { week })}
      </p>
      <span className="salon-cutscene__rule" aria-hidden />
      <p className="salon-cutscene__headline">{t("salon.cutscene.opened")}</p>
      <p className="salon-cutscene__sub">
        {bookings > 0
          ? t("salon.cutscene.bookings", { count: bookings })
          : t("salon.cutscene.bookingsNone")}
      </p>
    </div>
  );
}

function FinaleStage({ scene, language }: { scene: Scene; language: string }) {
  const { t } = useTranslation();
  if (!scene.result) {
    return (
      <OpeningNotice week={scene.nextWeek ?? 0} bookings={scene.bookings} />
    );
  }
  const { outcome } = scene.result;
  return (
    <div className={`salon-cutscene__result is-${outcome}`}>
      <h2 className="salon-cutscene__title">
        {t(`salon.office.result.${outcome}`)}
      </h2>
      <ResultDetail scene={scene} language={language} />
      {outcome === "bankrupt" && (
        <span className="salon-cutscene__stamp" aria-hidden>
          {t("salon.cutscene.seized")}
        </span>
      )}
    </div>
  );
}

function Confetti() {
  return (
    <span className="salon-cutscene__confetti" aria-hidden>
      {Array.from({ length: CONFETTI_COUNT }, (_, piece) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: 固定長の装飾
          key={piece}
          style={
            {
              "--x": `${(piece * 37) % 100}%`,
              // 横位置が近い紙片どうしで落ち始めをずらす
              "--delay": `${((piece * 5) % 12) * 0.11}s`,
              "--drift": `${((piece * 53) % 60) - 30}px`,
            } as CSSProperties
          }
        />
      ))}
    </span>
  );
}

function ResultDetail({ scene, language }: { scene: Scene; language: string }) {
  const { t } = useTranslation();
  if (!scene.result) return null;
  const { outcome, cash, profit } = scene.result;
  return (
    <p className="salon-cutscene__sub">
      {outcome === "bankrupt"
        ? t("salon.office.bankruptDetail", { cash: formatYen(cash, language) })
        : t("salon.office.resultDetail", {
            cash: formatYen(cash, language),
            profit: formatSignedYen(profit ?? 0, language),
          })}
    </p>
  );
}

/** 開業の短い版。開業資金・毎週の収支・評判・成功の条件と、開業した週の予約を1枚にまとめる */
function OpeningCard({
  scene,
  language,
}: {
  scene: OpeningScene;
  language: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="salon-cutscene__card" aria-live="polite">
      <p className="salon-cutscene__card-head">
        <span className="salon-cutscene__name">{scene.name}</span>
        <span>{t("salon.cutscene.founded")}</span>
      </p>
      <dl className="salon-cutscene__ledger">
        <div className="salon-cutscene__card-total">
          <dt>{t("salon.cutscene.initialCash")}</dt>
          <dd>{formatYen(scene.initialCash, language)}</dd>
        </div>
        {openingRows(scene).map((row) => (
          <div key={row.key}>
            <dt>{t(`salon.cutscene.${row.key}`)}</dt>
            <dd className={signClass(row.amount)}>
              {formatSignedYen(row.amount, language)}
            </dd>
          </div>
        ))}
        <div>
          <dt>{t("salon.cutscene.reputation")}</dt>
          <dd>{scene.reputation}</dd>
        </div>
      </dl>
      <p className="salon-cutscene__card-note">
        {t("salon.cutscene.goal", { weeks: scene.totalWeeks })}
      </p>
      <p className="salon-cutscene__card-next">
        {t("salon.cutscene.week", { week: scene.week })}
        {" · "}
        {scene.bookings > 0
          ? t("salon.cutscene.bookings", { count: scene.bookings })
          : t("salon.cutscene.bookingsNone")}
      </p>
    </div>
  );
}

/** 短い版。動きを付けず、締めた週の数字と次の週(または決算)を1枚にまとめる */
function ShortCard({ scene, language }: { scene: Scene; language: string }) {
  const { t } = useTranslation();
  const reputationEnd = scene.week.reputation_end;
  return (
    <div className="salon-cutscene__card" aria-live="polite">
      <p className="salon-cutscene__card-head">
        {t("salon.cutscene.week", { week: scene.week.week })}
        <span>{t("salon.cutscene.closed")}</span>
      </p>
      <dl className="salon-cutscene__ledger">
        {ledgerRows(scene.week).map((row) => (
          <div key={row.key}>
            <dt>{t(`salon.cutscene.${row.key}`)}</dt>
            <dd className={signClass(row.amount)}>
              {formatSignedYen(row.amount, language)}
            </dd>
          </div>
        ))}
        <div className="salon-cutscene__card-total">
          <dt>{t("salon.cutscene.cashEnd")}</dt>
          <dd className={scene.week.cash_end < 0 ? "is-negative" : undefined}>
            {formatYen(scene.week.cash_end, language)}
            <em className={signClass(scene.cashDelta)}>
              {formatSignedYen(scene.cashDelta, language)}
            </em>
          </dd>
        </div>
        <div>
          <dt>{t("salon.cutscene.reputation")}</dt>
          <dd>
            {reputationEnd}
            <em className={signClass(reputationEnd - scene.reputationStart)}>
              {formatSignedNumber(reputationEnd - scene.reputationStart)}
            </em>
          </dd>
        </div>
      </dl>
      {scene.regulars.map((name) => (
        <p key={`regular-${name}`} className="salon-cutscene__card-note">
          {t("salon.cutscene.regular", { name })}
        </p>
      ))}
      {scene.achievements.map((achievement) => (
        <p
          key={achievement.achievement_id}
          className="salon-cutscene__card-note"
        >
          {t("salon.cutscene.achievement")}: {achievement.name}
        </p>
      ))}
      {scene.result ? (
        <div
          className={`salon-cutscene__card-result is-${scene.result.outcome}`}
        >
          <strong>{t(`salon.office.result.${scene.result.outcome}`)}</strong>
          <ResultDetail scene={scene} language={language} />
        </div>
      ) : (
        <p className="salon-cutscene__card-next">
          {t("salon.cutscene.week", { week: scene.nextWeek ?? 0 })}
          {" · "}
          {scene.bookings > 0
            ? t("salon.cutscene.bookings", { count: scene.bookings })
            : t("salon.cutscene.bookingsNone")}
        </p>
      )}
    </div>
  );
}
