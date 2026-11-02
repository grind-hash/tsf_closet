import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import type { SalonDifficulty, SalonRun } from "../../apis/salon";
import {
  SALON_DEFAULT_DIFFICULTY,
  SALON_DIFFICULTIES,
  SALON_DIFFICULTY_INITIAL_CASH,
  SALON_NAME_MAX_LENGTH,
  SALON_TOTAL_WEEKS,
  SALON_WEEKLY_NET_COST,
} from "../../constants/salon";
import { useSalon } from "../../contexts/SalonContext";
import { useSettings } from "../../contexts/SettingsContext";
import { getSalonRunPath, ROUTES } from "../../routes";
import { formatYen } from "../../utils/salonView";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import type { SalonOfficeLocationState } from "./SalonOffice";

/** サロン一覧と開店(/salon) */
export default function SalonHub() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const { runs, busy, error, loadRuns, createRun, deleteRun } = useSalon();
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState<SalonDifficulty>(
    SALON_DEFAULT_DIFFICULTY,
  );
  // 過激施術の初期値は、直近に遊んだサロン(一覧の先頭)の設定を引き継ぐ。
  // 一度でも切り替えたら、一覧を読み直しても上書きしない
  const [sensitive, setSensitive] = useState(false);
  const sensitiveTouchedRef = useRef(false);
  const [deleteTarget, setDeleteTarget] = useState<SalonRun | null>(null);
  const nameId = useId();
  const difficultyLabelId = useId();
  const language = settingsState.language;

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const latestSensitive = runs[0]?.sensitive ?? false;
  useEffect(() => {
    if (!sensitiveTouchedRef.current) setSensitive(latestSensitive);
  }, [latestSensitive]);

  const handleOpen = async () => {
    const created = await createRun(name.trim(), difficulty, sensitive);
    if (created) {
      setName("");
      navigate(getSalonRunPath(created.id), {
        state: { grandOpening: true } satisfies SalonOfficeLocationState,
      });
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await deleteRun(deleteTarget.id);
    setDeleteTarget(null);
  };

  return (
    <MainLayout variant="salon">
      <div className="salon-page">
        <header className="salon-page__header">
          <p className="salon-eyebrow">{t("salon.eyebrow")}</p>
          <h1>{t("salon.title")}</h1>
          <p className="salon-page__lead">
            {t("salon.lead", {
              weeks: SALON_TOTAL_WEEKS,
              net: formatYen(SALON_WEEKLY_NET_COST, language),
            })}
          </p>
        </header>

        {error && (
          <p className="salon-error" role="alert">
            {error}
          </p>
        )}

        <section className="salon-card salon-open">
          <h2>{t("salon.open.heading")}</h2>
          <label className="salon-field" htmlFor={nameId}>
            <span>{t("salon.open.nameLabel")}</span>
            <input
              id={nameId}
              type="text"
              value={name}
              maxLength={SALON_NAME_MAX_LENGTH}
              placeholder={t("salon.open.namePlaceholder")}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div className="salon-field">
            <span id={difficultyLabelId}>
              {t("salon.open.difficultyLabel")}
            </span>
            <div
              className="salon-segments"
              role="group"
              aria-labelledby={difficultyLabelId}
            >
              {SALON_DIFFICULTIES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={difficulty === value ? "is-active" : undefined}
                  aria-pressed={difficulty === value}
                  onClick={() => setDifficulty(value)}
                >
                  {t(`salon.open.difficulty.${value}`)}
                </button>
              ))}
            </div>
            <p className="salon-field__hint">
              {t(`salon.open.difficultyDesc.${difficulty}`, {
                cash: formatYen(
                  SALON_DIFFICULTY_INITIAL_CASH[difficulty],
                  language,
                ),
              })}
            </p>
          </div>
          <label className="salon-toggle">
            <span className="salon-toggle__info">
              <strong>{t("salon.office.sensitive")}</strong>
              <small>{t("salon.open.sensitiveHint")}</small>
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
              checked={sensitive}
              onChange={(event) => {
                sensitiveTouchedRef.current = true;
                setSensitive(event.target.checked);
              }}
            />
            <span className="salon-toggle__switch" aria-hidden />
          </label>
          <p className="salon-open__goal">{t("salon.open.goal")}</p>
          <button
            type="button"
            className="salon-button salon-button--primary salon-open__submit"
            disabled={!name.trim() || busy === "create"}
            onClick={() => void handleOpen()}
          >
            {busy === "create" && (
              <span className="salon-spinner" aria-hidden />
            )}
            {t("salon.open.submit")}
          </button>
        </section>

        <section className="salon-section">
          <h2>{t("salon.list.heading")}</h2>
          {busy === "load" && runs.length === 0 ? (
            <p className="salon-progress" role="status">
              <span className="salon-spinner" aria-hidden />
              {t("salon.loading")}
            </p>
          ) : runs.length === 0 ? (
            <p className="salon-empty">{t("salon.list.empty")}</p>
          ) : (
            <ul className="salon-run-list">
              {runs.map((run) => (
                <li key={run.id} className="salon-run-row">
                  <div className="salon-run-row__main">
                    <strong>{run.name}</strong>
                    <span className="salon-run-row__meta">
                      {run.status === "active"
                        ? t("salon.list.week", {
                            week: run.week,
                            total: run.total_weeks,
                          })
                        : t(`salon.list.status.${run.status}`)}
                      {" · "}
                      {t("salon.list.cash", {
                        cash: formatYen(run.cash, language),
                      })}
                    </span>
                  </div>
                  <span className={`salon-chip salon-chip--${run.difficulty}`}>
                    {t(`salon.open.difficulty.${run.difficulty}`)}
                  </span>
                  <button
                    type="button"
                    className="salon-button"
                    onClick={() => navigate(getSalonRunPath(run.id))}
                  >
                    {t("salon.list.open")}
                  </button>
                  <button
                    type="button"
                    className="salon-icon-button salon-icon-button--danger"
                    aria-label={t("salon.list.delete")}
                    title={t("salon.list.delete")}
                    onClick={() => setDeleteTarget(run)}
                  >
                    🗑
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("salon.list.deleteTitle")}
        confirmLabel={t("salon.list.deleteConfirm")}
        cancelLabel={t("common.cancel")}
        busy={busy === "delete"}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
      >
        {t("salon.list.deleteBody", { name: deleteTarget?.name ?? "" })}
      </ConfirmDialog>
    </MainLayout>
  );
}
