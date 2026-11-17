import { type ReactNode, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  fetchSalonCustomerCounts,
  type SalonCustomerCounts,
  type SalonCustomerType,
} from "../../apis/salon";
import {
  SALON_CUSTOMER_GENDERS,
  SALON_DESIRED_BODIES,
} from "../../constants/salon";

interface SalonCustomerTypeFieldsProps {
  value: SalonCustomerType;
  onChange: (change: Partial<SalonCustomerType>) => void;
  /** open: 開店画面 / office: オーナー室(効き始める時期も添える) */
  variant: "open" | "office";
  disabled?: boolean;
}

/** 来客の種類(お客様の性別と願う体)。開店画面とオーナー室で同じ選択肢を出す */
export default function SalonCustomerTypeFields({
  value,
  onChange,
  variant,
  disabled = false,
}: SalonCustomerTypeFieldsProps) {
  const { t } = useTranslation();
  const genderLabelId = useId();
  const bodyLabelId = useId();
  const [counts, setCounts] = useState<SalonCustomerCounts | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSalonCustomerCounts()
      .then((result) => {
        if (!cancelled) setCounts(result);
      })
      .catch(() => {
        // 人数は目安の表示だけなので、取れなければ出さない
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const count = counts ? counts[value.customer_gender] : null;
  const countNote =
    count === null ? null : count === 0 ? (
      <span className="salon-office__settings-note">
        {t("salon.customerType.countZero")}
      </span>
    ) : (
      t("salon.customerType.count", { count })
    );
  const bodyNote =
    variant === "office"
      ? `${t("salon.customerType.bodyHint")} ${t("salon.customerType.officeTiming")}`
      : t("salon.customerType.bodyHint");

  const row = (
    labelId: string,
    label: string,
    note: ReactNode,
    control: ReactNode,
  ) =>
    variant === "open" ? (
      <div className="salon-field">
        <span id={labelId}>{label}</span>
        {control}
        {note && <p className="salon-field__hint">{note}</p>}
      </div>
    ) : (
      <div className="salon-office__setting">
        <span className="salon-toggle__info">
          <strong id={labelId}>{label}</strong>
          {note && <small>{note}</small>}
        </span>
        {control}
      </div>
    );

  return (
    <>
      {row(
        genderLabelId,
        t("salon.customerType.genderLabel"),
        countNote,
        <div
          className="salon-segments"
          role="group"
          aria-labelledby={genderLabelId}
        >
          {SALON_CUSTOMER_GENDERS.map((option) => (
            <button
              key={option}
              type="button"
              className={
                value.customer_gender === option ? "is-active" : undefined
              }
              aria-pressed={value.customer_gender === option}
              disabled={disabled}
              onClick={() => onChange({ customer_gender: option })}
            >
              {t(`salon.customerType.gender.${option}`)}
            </button>
          ))}
        </div>,
      )}
      {row(
        bodyLabelId,
        t("salon.customerType.bodyLabel"),
        bodyNote,
        <div
          className="salon-segments"
          role="group"
          aria-labelledby={bodyLabelId}
        >
          {SALON_DESIRED_BODIES.map((option) => (
            <button
              key={option}
              type="button"
              className={
                value.desired_body === option ? "is-active" : undefined
              }
              aria-pressed={value.desired_body === option}
              disabled={disabled}
              onClick={() => onChange({ desired_body: option })}
            >
              {t(`salon.customerType.body.${option}`)}
            </button>
          ))}
        </div>,
      )}
    </>
  );
}
