import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { SalonRun, SalonVisit } from "../../apis/salon";
import { SALON_DECLINE_PENALTY } from "../../constants/salon";
import { useSalon } from "../../contexts/SalonContext";
import { useSettings } from "../../contexts/SettingsContext";
import { useAdventureBgm } from "../../hooks/useAdventureBgm";
import { getSalonVisitPath, ROUTES } from "../../routes";
import {
  formatSignedNumber,
  formatSignedYen,
  formatYen,
  salonCashSeries,
  salonReviews,
  thisWeekVisits,
} from "../../utils/salonView";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import SalonBgmControl from "./SalonBgmControl";
import SalonCashChart from "./SalonCashChart";

/** サロンのオーナー室(/salon/:runId)。予約帳・週の締め・帳簿・口コミ・決算 */
export default function SalonOffice({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const {
    activeRun,
    busy,
    error,
    openRun,
    updateRunSettings,
    declineVisit,
    closeWeek,
  } = useSalon();
  const [declineTarget, setDeclineTarget] = useState<SalonVisit | null>(null);
  const [closeOpen, setCloseOpen] = useState(false);
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
  const serving = visits.some((visit) => visit.status === "serving");
  const reviews = salonReviews(run);
  const isActive = run.status === "active";
  const isFinalWeek = run.week >= run.total_weeks;

  const handleDecline = async () => {
    if (!declineTarget) return;
    await declineVisit(declineTarget.id);
    setDeclineTarget(null);
  };

  const handleCloseWeek = async () => {
    await closeWeek();
    setCloseOpen(false);
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
                disabled={serving || busy !== null}
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
                  ? t("salon.office.closeWeekServing")
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
  if (!run.result) return null;
  const { outcome, cash, profit } = run.result;
  return (
    <section className={`salon-result salon-result--${outcome}`}>
      <h2>{t(`salon.office.result.${outcome}`)}</h2>
      <p>
        {outcome === "bankrupt"
          ? t("salon.office.bankruptDetail", {
              cash: formatYen(cash, language),
            })
          : t("salon.office.resultDetail", {
              cash: formatYen(cash, language),
              profit: formatSignedYen(profit ?? 0, language),
            })}
      </p>
      <div className="salon-result__actions">
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
