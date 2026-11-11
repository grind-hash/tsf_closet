import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type { SalonRun, SalonVisit } from "../../apis/salon";
import { SALON_DECLINE_PENALTY } from "../../constants/salon";
import { useSalon } from "../../contexts/SalonContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { usePersistedState } from "../../hooks/usePersistedState";
import { getSalonVisitPath, ROUTES } from "../../routes";
import {
  buildOpeningCutscene,
  buildWeekCutscene,
  formatSignedNumber,
  formatSignedYen,
  formatYen,
  SALON_CUTSCENE_MODES,
  type SalonCutsceneMode,
  type SalonCutsceneScene,
  salonCashSeries,
  salonReviews,
  thisWeekVisits,
} from "../../utils/salonView";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import SalonBgmControl from "./SalonBgmControl";
import SalonCashChart from "./SalonCashChart";
import SalonCustomerTypeFields from "./SalonCustomerTypeFields";
import SalonCutscene from "./SalonCutscene";

/** 開業・週の締めの演出の設定。端末ごとの好みなのでブラウザに保存する */
const SALON_CUTSCENE_KEY = "salon_week_cutscene";

function parseCutsceneMode(raw: string): SalonCutsceneMode {
  const value: unknown = JSON.parse(raw);
  if (!SALON_CUTSCENE_MODES.includes(value as SalonCutsceneMode)) {
    throw new Error("invalid");
  }
  return value as SalonCutsceneMode;
}

/** 一覧で開店した直後にオーナー室へ渡す router state。開業の演出を一度だけ見せる */
export interface SalonOfficeLocationState {
  grandOpening?: boolean;
}

/** サロンのオーナー室(/salon/:runId)。予約帳・週の締め・帳簿・口コミ・決算 */
export default function SalonOffice({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { state: settingsState } = useSettings();
  const {
    activeRun,
    busy,
    error,
    openRun,
    updateRunSettings,
    declineVisit,
    closeWeek,
    announceAchievements,
  } = useSalon();
  const [declineTarget, setDeclineTarget] = useState<SalonVisit | null>(null);
  const [closeOpen, setCloseOpen] = useState(false);
  const [cutsceneMode, setCutsceneMode] = usePersistedState<SalonCutsceneMode>(
    SALON_CUTSCENE_KEY,
    "full",
    { deserialize: parseCutsceneMode },
  );
  const [cutscene, setCutscene] = useState<SalonCutsceneScene | null>(null);
  const cutsceneLabelId = useId();
  const language = settingsState.language;

  useEffect(() => {
    void openRun(runId);
  }, [openRun, runId]);

  // オーナー室の BGM。曲がまだ置かれていなければ鳴らさない(シナリオの曲へは倒さない)
  const bgm = useAdventureBgm("salon_office", {
    fallbackToDefault: false,
    prefsScope: "salon",
  });

  const run = activeRun?.id === runId ? activeRun : null;
  const grandOpening =
    (location.state as SalonOfficeLocationState | null)?.grandOpening === true;
  // 開店した直後だけ開業の演出を見せる。再読み込みや「戻る」で繰り返さないよう state は消す
  useEffect(() => {
    if (!grandOpening || !run) return;
    navigate(location.pathname, { replace: true, state: null });
    if (cutsceneMode !== "none") setCutscene(buildOpeningCutscene(run));
  }, [grandOpening, run, cutsceneMode, navigate, location.pathname]);

  if (!run) {
    return (
      <MainLayout variant="salon">
        <div className="salon-page">
          {error ? (
            <p className="salon-error" role="alert">
              {error}
            </p>
          ) : (
            <p className="salon-progress" role="status">
              <span className="salon-spinner" aria-hidden />
              {t("salon.loading")}
            </p>
          )}
          <button
            type="button"
            className="salon-button"
            onClick={() => navigate(ROUTES.SALON)}
          >
            {t("salon.office.back")}
          </button>
        </div>
      </MainLayout>
    );
  }

  const visits = thisWeekVisits(run);
  const pending = visits.filter((visit) => visit.status === "booked");
  const serving = visits.find((visit) => visit.status === "serving") ?? null;
  const season = run.season ?? 1;
  const reviews = salonReviews(run);
  const isActive = run.status === "active";
  const isFinalWeek = run.week >= run.total_weeks;

  const handleDecline = async () => {
    if (!declineTarget) return;
    await declineVisit(declineTarget.id);
    setDeclineTarget(null);
  };

  const handleCloseWeek = async () => {
    const before = run;
    const result = await closeWeek({ announce: cutsceneMode === "none" });
    setCloseOpen(false);
    if (!result || cutsceneMode === "none") return;
    const scene = buildWeekCutscene(before, result);
    if (scene) {
      setCutscene(scene);
    } else {
      announceAchievements(result.achievements);
    }
  };

  const handleCutsceneClose = (sawAchievements: boolean) => {
    // 実績を見せる前に飛ばしたら、通知で知らせる(飛ばしても情報は落とさない)
    if (cutscene?.kind === "week" && !sawAchievements) {
      announceAchievements(cutscene.achievements);
    }
    setCutscene(null);
  };

  return (
    <MainLayout variant="salon">
      <div className="salon-page">
        <header className="salon-office__header">
          <button
            type="button"
            className="salon-back"
            aria-label={t("salon.office.back")}
            title={t("salon.office.back")}
            onClick={() => navigate(ROUTES.SALON)}
          >
            ←
          </button>
          <div className="salon-office__title">
            <p className="salon-eyebrow">{t("salon.title")}</p>
            <h1>{run.name}</h1>
          </div>
          <span className={`salon-chip salon-chip--${run.difficulty}`}>
            {t(`salon.open.difficulty.${run.difficulty}`)}
          </span>
          <SalonBgmControl bgm={bgm} />
        </header>

        {error && (
          <p className="salon-error" role="alert">
            {error}
          </p>
        )}

        <SalonResultBanner run={run} language={language} />

        <div className="salon-tiles">
          <div className="salon-tile">
            <span>{t("salon.office.weekLabel")}</span>
            <strong>
              {run.week}
              <small>
                {t("salon.office.weekOf", { total: run.total_weeks })}
              </small>
            </strong>
            {season > 1 && (
              <span className="salon-tile__note">
                {t("salon.office.seasonOf", {
                  season,
                  start: run.season_start_week,
                  end: run.total_weeks,
                })}
              </span>
            )}
          </div>
          <div className="salon-tile">
            <span>{t("salon.office.cash")}</span>
            <strong className={run.cash < 0 ? "is-negative" : undefined}>
              {formatYen(run.cash, language)}
            </strong>
          </div>
          <div className="salon-tile">
            <span>{t("salon.office.reputation")}</span>
            <strong>
              {run.reputation}
              <small>/ 100</small>
            </strong>
            <span className="salon-meter" aria-hidden>
              <span style={{ width: `${run.reputation}%` }} />
            </span>
          </div>
          <div className="salon-tile">
            <span>{t("salon.office.weeklyBalance")}</span>
            <strong className="salon-tile__small">
              {t("salon.office.weeklyBalanceValue", {
                salary: formatYen(run.weekly_salary, language),
                fixed: formatYen(run.weekly_fixed_cost, language),
              })}
            </strong>
          </div>
        </div>

        {isActive && (
          <section className="salon-card salon-office__settings">
            <label className="salon-toggle">
              <span className="salon-toggle__info">
                <strong>{t("salon.office.sensitive")}</strong>
                <small>{t("salon.office.sensitiveHint")}</small>
                {!settingsState.nsfwMode && (
                  <small className="salon-office__settings-note">
                    {t("salon.office.sensitiveNsfwOff")}{" "}
                    <Link to={ROUTES.SETTINGS}>
                      {t("salon.office.sensitiveOpenSettings")}
                    </Link>
                  </small>
                )}
              </span>
              <input
                type="checkbox"
                className="salon-toggle__input"
                checked={run.sensitive}
                disabled={busy !== null}
                onChange={(event) =>
                  void updateRunSettings({ sensitive: event.target.checked })
                }
              />
              <span className="salon-toggle__switch" aria-hidden />
            </label>
            <SalonCustomerTypeFields
              variant="office"
              value={{
                customer_gender: run.customer_gender,
                desired_body: run.desired_body,
              }}
              disabled={busy !== null}
              onChange={(change) => void updateRunSettings(change)}
            />
            <div className="salon-office__setting">
              <span className="salon-toggle__info">
                <strong id={cutsceneLabelId}>
                  {t("salon.office.cutscene")}
                </strong>
                <small>{t("salon.office.cutsceneHint")}</small>
              </span>
              <div
                className="salon-segments"
                role="group"
                aria-labelledby={cutsceneLabelId}
              >
                {SALON_CUTSCENE_MODES.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={cutsceneMode === value ? "is-active" : undefined}
                    aria-pressed={cutsceneMode === value}
                    onClick={() => setCutsceneMode(value)}
                  >
                    {t(`salon.office.cutsceneModes.${value}`)}
                  </button>
                ))}
              </div>
            </div>
          </section>
        )}

        {isActive && (
          <section className="salon-section">
            <h2>{t("salon.office.bookings")}</h2>
            <p className="salon-section__hint">
              {t("salon.office.bookingsHint")}
            </p>
            {visits.length === 0 ? (
              <p className="salon-empty">{t("salon.office.bookingsEmpty")}</p>
            ) : (
              <ul className="salon-visit-list">
                {visits.map((visit) => (
                  <SalonVisitCard
                    key={visit.id}
                    visit={visit}
                    language={language}
                    busy={busy !== null}
                    onServe={() =>
                      navigate(getSalonVisitPath(run.id, visit.id))
                    }
                    onDecline={() => setDeclineTarget(visit)}
                  />
                ))}
              </ul>
            )}
            <div className="salon-close-week">
              <button
                type="button"
                className="salon-button salon-button--primary"
                disabled={busy !== null}
                onClick={() => setCloseOpen(true)}
              >
                {busy === "close" && (
                  <span className="salon-spinner" aria-hidden />
                )}
                {t(
                  isFinalWeek
                    ? "salon.office.closeWeekFinal"
                    : "salon.office.closeWeek",
                )}
              </button>
              <p className="salon-section__hint">
                {serving
                  ? t("salon.office.closeWeekServing", {
                      name: serving.customer.name,
                      penalty: SALON_DECLINE_PENALTY,
                    })
                  : t("salon.office.closeWeekHint", {
                      salary: formatYen(run.weekly_salary, language),
                      fixed: formatYen(run.weekly_fixed_cost, language),
                    })}
              </p>
            </div>
          </section>
        )}

        <section className="salon-section">
          <h2>{t("salon.office.ledger")}</h2>
          {run.weeks.length === 0 ? (
            <p className="salon-empty">{t("salon.office.ledgerEmpty")}</p>
          ) : (
            <>
              <SalonCashChart
                points={salonCashSeries(run)}
                initialCash={run.initial_cash}
                goalCash={season > 1 ? run.season_start_cash : undefined}
                totalWeeks={run.total_weeks}
                language={language}
              />
              <div className="salon-ledger">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.week")}
                      </th>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.revenue")}
                      </th>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.balance")}
                      </th>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.served")}
                      </th>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.cashEnd")}
                      </th>
                      <th scope="col">
                        {t("salon.office.ledgerColumns.reputation")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.weeks.map((week) => (
                      <tr key={week.week}>
                        <th scope="row">{week.week}</th>
                        <td>
                          {formatYen(week.revenue, language)}
                          {(week.extra_cost ?? 0) > 0 && (
                            <small className="salon-ledger__sub">
                              {t("salon.office.ledgerExtraCost", {
                                amount: formatSignedYen(
                                  -(week.extra_cost ?? 0),
                                  language,
                                ),
                              })}
                            </small>
                          )}
                        </td>
                        <td>
                          {formatSignedYen(
                            week.salary - week.fixed_cost,
                            language,
                          )}
                        </td>
                        <td>
                          {week.served} / {week.declined}
                        </td>
                        <td
                          className={
                            week.cash_end < 0 ? "is-negative" : undefined
                          }
                        >
                          {formatYen(week.cash_end, language)}
                        </td>
                        <td>{week.reputation_end}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section className="salon-section">
          <h2>{t("salon.office.reviews")}</h2>
          {reviews.length === 0 ? (
            <p className="salon-empty">{t("salon.office.reviewsEmpty")}</p>
          ) : (
            <ul className="salon-review-list">
              {reviews.map((visit) => (
                <li key={visit.id}>
                  <p className="salon-review-list__text">「{visit.review}」</p>
                  <p className="salon-review-list__meta">
                    {t("salon.office.reviewMeta", {
                      week: visit.week,
                      name: visit.customer.name,
                      satisfaction: visit.satisfaction ?? 0,
                    })}
                    {visit.fulfilled && (
                      <span className="salon-chip salon-chip--success">
                        {t("salon.office.fulfilled")}
                      </span>
                    )}
                    <SalonRecordLink visit={visit} />
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <ConfirmDialog
        open={declineTarget !== null}
        title={t("salon.office.declineTitle")}
        confirmLabel={t("salon.office.decline")}
        cancelLabel={t("common.cancel")}
        busy={busy === "decline"}
        onConfirm={() => void handleDecline()}
        onCancel={() => setDeclineTarget(null)}
      >
        {t("salon.office.declineBody", {
          name: declineTarget?.customer.name ?? "",
          penalty: SALON_DECLINE_PENALTY,
        })}
      </ConfirmDialog>

      <ConfirmDialog
        open={closeOpen}
        title={t("salon.office.closeWeekTitle", { week: run.week })}
        confirmLabel={t("salon.office.closeWeekConfirm")}
        cancelLabel={t("common.cancel")}
        busy={busy === "close"}
        onConfirm={() => void handleCloseWeek()}
        onCancel={() => setCloseOpen(false)}
      >
        <p>
          {t("salon.office.closeWeekHint", {
            salary: formatYen(run.weekly_salary, language),
            fixed: formatYen(run.weekly_fixed_cost, language),
          })}
        </p>
        {serving && (
          <p>
            {t("salon.office.closeWeekServing", {
              name: serving.customer.name,
              penalty: SALON_DECLINE_PENALTY,
            })}
          </p>
        )}
        {pending.length > 0 && (
          <p>
            {t("salon.office.closeWeekPending", {
              count: pending.length,
              penalty: pending.length * SALON_DECLINE_PENALTY,
            })}
          </p>
        )}
        <p>{t("salon.office.closeWeekBody")}</p>
      </ConfirmDialog>

      {cutscene && cutsceneMode !== "none" && (
        <SalonCutscene
          scene={cutscene}
          mode={cutsceneMode}
          language={language}
          onClose={handleCutsceneClose}
          onPreferShort={() => setCutsceneMode("short")}
        />
      )}
    </MainLayout>
  );
}

function SalonVisitCard({
  visit,
  language,
  busy,
  onServe,
  onDecline,
}: {
  visit: SalonVisit;
  language: string;
  busy: boolean;
  onServe: () => void;
  onDecline: () => void;
}) {
  const { t } = useTranslation();
  return (
    <li className={`salon-visit is-${visit.status}`}>
      <div className="salon-visit__head">
        <strong>{visit.customer.name}</strong>
        <span className="salon-visit__number">
          {visit.visit_number > 1
            ? t("salon.office.visitNumber", { count: visit.visit_number })
            : t("salon.office.visitFirst")}
        </span>
        <span className={`salon-chip salon-chip--status-${visit.status}`}>
          {t(`salon.office.visitStatus.${visit.status}`)}
        </span>
      </div>
      {visit.returning_look && visit.status !== "done" && (
        <p className="salon-visit__note">{t("salon.office.returningLook")}</p>
      )}
      {visit.previous_review && visit.status !== "done" && (
        <p className="salon-visit__review">
          <span>{t("salon.office.previousReview")}</span>「
          {visit.previous_review}」
        </p>
      )}
      {visit.status === "done" && (
        <>
          <p className="salon-visit__summary">
            {t("salon.office.doneSummary", {
              satisfaction: visit.satisfaction ?? 0,
              payment: formatYen(visit.payment, language),
              delta: formatSignedNumber(visit.reputation_delta),
            })}
            {visit.fulfilled && (
              <span className="salon-chip salon-chip--success">
                {t("salon.office.fulfilled")}
              </span>
            )}
            {visit.kept_look && (
              <span className="salon-chip salon-chip--kept">
                {t("salon.office.keptLook")}
              </span>
            )}
          </p>
          {visit.review && (
            <p className="salon-visit__review">「{visit.review}」</p>
          )}
          <SalonRecordLink visit={visit} />
        </>
      )}
      {(visit.status === "booked" || visit.status === "serving") && (
        <div className="salon-visit__actions">
          <button
            type="button"
            className="salon-button salon-button--primary"
            disabled={busy}
            onClick={onServe}
          >
            {t(
              visit.status === "serving"
                ? "salon.office.resume"
                : "salon.office.serve",
            )}
          </button>
          {visit.status === "booked" && (
            <button
              type="button"
              className="salon-button"
              disabled={busy}
              onClick={onDecline}
            >
              {t("salon.office.decline")}
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function SalonResultBanner({
  run,
  language,
}: {
  run: SalonRun;
  language: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { busy, startNextSeason } = useSalon();
  if (!run.result) return null;
  const { outcome, cash, profit } = run.result;
  const season = run.result.season ?? run.season ?? 1;
  const startCash = run.result.start_cash ?? run.initial_cash;
  const canContinue = run.status === "completed";
  return (
    <section className={`salon-result salon-result--${outcome}`}>
      {(run.seasons?.length ?? 0) > 1 && (
        <p className="salon-eyebrow">
          {t("salon.office.resultSeason", { season })}
        </p>
      )}
      <h2>{t(`salon.office.result.${outcome}`)}</h2>
      <p>
        {outcome === "bankrupt"
          ? t("salon.office.bankruptDetail", {
              cash: formatYen(cash, language),
            })
          : t("salon.office.resultDetail", {
              cash: formatYen(cash, language),
              start: formatYen(startCash, language),
              profit: formatSignedYen(profit ?? 0, language),
            })}
      </p>
      {canContinue && (
        <p className="salon-result__hint">
          {t("salon.office.nextSeasonHint", {
            season: season + 1,
            weeks: run.season_weeks,
          })}
        </p>
      )}
      <div className="salon-result__actions">
        {canContinue && (
          <button
            type="button"
            className="salon-button salon-button--primary"
            disabled={busy !== null}
            onClick={() => void startNextSeason()}
          >
            {busy === "nextSeason" && (
              <span className="salon-spinner" aria-hidden />
            )}
            {t("salon.office.nextSeason")}
          </button>
        )}
        <button
          type="button"
          className="salon-button"
          onClick={() => navigate(ROUTES.ACHIEVEMENTS)}
        >
          {t("salon.office.achievements")}
        </button>
        <button
          type="button"
          className="salon-button"
          onClick={() => navigate(ROUTES.SALON)}
        >
          {t("salon.office.newSalon")}
        </button>
      </div>
    </section>
  );
}

/** 施術した姿を、ギャラリーのセッション表示で見るリンク。セッションが消えていれば出さない */
function SalonRecordLink({ visit }: { visit: SalonVisit }) {
  const { t } = useTranslation();
  if (!visit.session_id) return null;
  return (
    <Link
      className="salon-record-link"
      to={`${ROUTES.GALLERY}/${visit.session_id}`}
    >
      {t("salon.office.viewRecord")}
    </Link>
  );
}
