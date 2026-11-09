import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaRuleCard } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";

const MAX_ACTIVE = 3;
const NAME_MAX = 20;
const TEXT_MAX = 200;

/** 掟タブ: 掟の有効化・解除と、自作の掟の作成・編集・削除 */
export default function HakoniwaRulesTab() {
  const { t } = useTranslation();
  const { world, busy, toggleRule, deleteCustomRule, playbackQueue } =
    useHakoniwa();
  const [editing, setEditing] = useState<HakoniwaRuleCard | "new" | null>(null);
  const [deleting, setDeleting] = useState<HakoniwaRuleCard | null>(null);

  if (!world) return null;
  const activeCount = world.rule_cards.filter((card) => card.active).length;
  const locked = busy !== null || playbackQueue.length > 0;

  return (
    <div className="hakoniwa-rules">
      <p className="hakoniwa-note">{t("hakoniwa.rules.note")}</p>
      <p className="hakoniwa-rules__count">
        {t("hakoniwa.rules.activeCount", { count: activeCount })}
      </p>
      <ul className="hakoniwa-rules__list">
        {world.rule_cards.map((card) => (
          <RuleRow
            key={card.id}
            card={card}
            disabled={locked || (!card.active && activeCount >= MAX_ACTIVE)}
            onToggle={(active) => void toggleRule(card.id, active)}
            onEdit={() => setEditing(card)}
            onDelete={() => setDeleting(card)}
          />
        ))}
      </ul>
      <button
        type="button"
        className="hakoniwa-button"
        onClick={() => setEditing("new")}
        disabled={locked}
      >
        {t("hakoniwa.rules.create")}
      </button>
      {editing && (
        <CustomRuleModal
          rule={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        title={t("hakoniwa.rules.deleteTitle")}
        confirmLabel={t("hakoniwa.rules.deleteConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          if (deleting) void deleteCustomRule(deleting.id);
          setDeleting(null);
        }}
      >
        <p>{t("hakoniwa.rules.deleteBody", { name: deleting?.name ?? "" })}</p>
      </ConfirmDialog>
    </div>
  );
}

function RuleRow({
  card,
  disabled,
  onToggle,
  onEdit,
  onDelete,
}: {
  card: HakoniwaRuleCard;
  disabled: boolean;
  onToggle: (active: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  return (
    <li className={`hakoniwa-rule${card.active ? " is-active" : ""}`}>
      <label className="hakoniwa-toggle" htmlFor={inputId}>
        <span className="hakoniwa-rule__text">
          <span className="hakoniwa-rule__name">{card.name}</span>
          <span className="hakoniwa-rule__desc">{card.description}</span>
        </span>
        <input
          id={inputId}
          type="checkbox"
          className="hakoniwa-toggle__input"
          checked={card.active}
          disabled={disabled}
          aria-label={t("hakoniwa.rules.toggleLabel", { name: card.name })}
          onChange={(event) => onToggle(event.target.checked)}
        />
        <span className="hakoniwa-toggle__switch" aria-hidden />
      </label>
      {card.custom && (
        <div className="hakoniwa-rule__actions">
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost"
            onClick={onEdit}
          >
            {t("hakoniwa.rules.edit")}
          </button>
          <button
            type="button"
            className="hakoniwa-button hakoniwa-button--ghost"
            onClick={onDelete}
          >
            {t("hakoniwa.rules.delete")}
          </button>
          <span className="hakoniwa-badge">{t("hakoniwa.rules.custom")}</span>
        </div>
      )}
    </li>
  );
}

function CustomRuleModal({
  rule,
  onClose,
}: {
  rule: HakoniwaRuleCard | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { saveCustomRule, busy } = useHakoniwa();
  const nameId = useId();
  const textId = useId();
  const [name, setName] = useState(rule?.name ?? "");
  const [text, setText] = useState(rule?.description ?? "");

  return (
    <ConfirmDialog
      open
      className="hakoniwa-form-dialog"
      title={
        rule
          ? t("hakoniwa.rules.formTitleEdit")
          : t("hakoniwa.rules.formTitleAdd")
      }
      confirmLabel={t("hakoniwa.residentForm.save")}
      cancelLabel={t("hakoniwa.residentForm.cancel")}
      confirmDisabled={!name.trim() || !text.trim()}
      busy={busy === "rule"}
      onCancel={onClose}
      onConfirm={() => {
        void saveCustomRule(
          { name: name.trim(), text: text.trim() },
          rule?.id,
        ).then((saved) => {
          if (saved) onClose();
        });
      }}
    >
      <div className="hakoniwa-form">
        <label className="hakoniwa-field" htmlFor={nameId}>
          <span>{t("hakoniwa.rules.name")}</span>
          <input
            id={nameId}
            type="text"
            value={name}
            maxLength={NAME_MAX}
            placeholder={t("hakoniwa.rules.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="hakoniwa-field" htmlFor={textId}>
          <span>{t("hakoniwa.rules.text")}</span>
          <textarea
            id={textId}
            rows={3}
            value={text}
            maxLength={TEXT_MAX}
            placeholder={t("hakoniwa.rules.textPlaceholder")}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <p className="hakoniwa-note">{t("hakoniwa.rules.textNote")}</p>
      </div>
    </ConfirmDialog>
  );
}
