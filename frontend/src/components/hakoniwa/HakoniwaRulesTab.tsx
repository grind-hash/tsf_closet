import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { HakoniwaLookStatus, HakoniwaRuleCard } from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaLookFields from "./HakoniwaLookFields";

const MAX_ACTIVE = 3;
const NAME_MAX = 20;
const TEXT_MAX = 200;
const APPEARANCE_MAX = 300;
const COMBO = "combo";
/** 掟の姿の体の性別の選択肢。keep は住民それぞれの性別のまま */
const BODY_OPTIONS = ["keep", "female", "male"] as const;
type BodyOption = (typeof BODY_OPTIONS)[number];

/** 生成の確認に使う、これから生成する人数と描き直すかどうか */
interface LookRequest {
  target: string;
  label: string;
  count: number;
  regenerate: boolean;
}

/** まだの住民だけ生成するか、全員ぶんを描き直すか */
function lookRequest(
  target: string,
  label: string,
  status: HakoniwaLookStatus,
): LookRequest {
  const missing = status.total - status.ready;
  return missing > 0
    ? { target, label, count: missing, regenerate: false }
    : { target, label, count: status.total, regenerate: true };
}

/** 掟タブ: 掟の有効化・解除、自作の掟の作成・編集・削除、掟の姿・複合の姿の生成 */
export default function HakoniwaRulesTab() {
  const { t } = useTranslation();
  const {
    world,
    busy,
    toggleRule,
    deleteCustomRule,
    playbackQueue,
    generateLook,
  } = useHakoniwa();
  const [editing, setEditing] = useState<HakoniwaRuleCard | "new" | null>(null);
  const [deleting, setDeleting] = useState<HakoniwaRuleCard | null>(null);
  const [confirmLook, setConfirmLook] = useState<LookRequest | null>(null);

  if (!world) return null;
  const activeCount = world.rule_cards.filter((card) => card.active).length;
  const locked = busy !== null || playbackQueue.length > 0;
  const combo = world.combo_look;
  const comboNames = combo
    ? [
        ...combo.names,
        ...(combo.includes_dress
          ? [world.rule_cards.find((card) => card.id === "dress")?.name ?? ""]
          : []),
      ].join(t("hakoniwa.rules.comboJoin"))
    : "";

  return (
    <div className="hakoniwa-rules">
      <p className="hakoniwa-note">{t("hakoniwa.rules.note")}</p>
      <p className="hakoniwa-rules__count">
        {t("hakoniwa.rules.activeCount", { count: activeCount })}
      </p>
      {combo && (
        <section className="hakoniwa-rules__combo">
          <strong>{t("hakoniwa.rules.comboHeading")}</strong>
          <p className="hakoniwa-rules__combo-names">{comboNames}</p>
          <LookControls
            status={combo}
            target={COMBO}
            disabled={locked}
            onRequest={() =>
              setConfirmLook(
                lookRequest(
                  COMBO,
                  t("hakoniwa.rules.comboLabel", { names: comboNames }),
                  combo,
                ),
              )
            }
          />
        </section>
      )}
      <ul className="hakoniwa-rules__list">
        {world.rule_cards.map((card) => (
          <RuleRow
            key={card.id}
            card={card}
            nameOf={(id) =>
              world.rule_cards.find((item) => item.id === id)?.name ?? id
            }
            disabled={locked || (!card.active && activeCount >= MAX_ACTIVE)}
            lookDisabled={locked}
            onToggle={(active) => void toggleRule(card.id, active)}
            onEdit={() => setEditing(card)}
            onDelete={() => setDeleting(card)}
            onLook={(status) =>
              setConfirmLook(
                lookRequest(
                  card.id,
                  t("hakoniwa.rules.lookLabel", { name: card.name }),
                  status,
                ),
              )
            }
          />
        ))}
      </ul>
      <ConfirmDialog
        open={confirmLook !== null}
        title={t("hakoniwa.rules.lookConfirmTitle")}
        confirmLabel={t("hakoniwa.rules.lookConfirm", {
          count: confirmLook?.count ?? 0,
        })}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmLook(null)}
        onConfirm={() => {
          if (confirmLook) {
            generateLook(confirmLook.target, confirmLook.regenerate);
          }
          setConfirmLook(null);
        }}
      >
        <p>
          {t(
            confirmLook?.regenerate
              ? "hakoniwa.rules.lookConfirmRedraw"
              : "hakoniwa.rules.lookConfirmBody",
            { label: confirmLook?.label ?? "", count: confirmLook?.count ?? 0 },
          )}
        </p>
      </ConfirmDialog>
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

/** 掟の姿・複合の姿の生成状況と、生成(まだの住民だけ)/描き直しのボタン */
function LookControls({
  status,
  target,
  disabled,
  onRequest,
}: {
  status: HakoniwaLookStatus;
  target: string;
  disabled: boolean;
  onRequest: () => void;
}) {
  const { t } = useTranslation();
  const { lookTarget } = useHakoniwa();
  const missing = status.total - status.ready;
  const generating = lookTarget === target;
  return (
    <div className="hakoniwa-rule__look">
      <span className="hakoniwa-rule__look-status">
        {missing > 0
          ? t("hakoniwa.rules.lookStatus", {
              ready: status.ready,
              total: status.total,
            })
          : t("hakoniwa.rules.lookReady")}
        {status.stale > 0 &&
          ` ${t("hakoniwa.rules.lookStale", { count: status.stale })}`}
      </span>
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--ghost"
        onClick={onRequest}
        disabled={disabled}
      >
        {generating ? (
          <>
            <span className="hakoniwa-spinner" aria-hidden />
            {t("hakoniwa.rules.lookGenerating")}
          </>
        ) : missing > 0 ? (
          t("hakoniwa.rules.lookGenerate", { count: missing })
        ) : (
          t("hakoniwa.rules.lookRedraw", { count: status.total })
        )}
      </button>
    </div>
  );
}

function RuleRow({
  card,
  nameOf,
  disabled,
  lookDisabled,
  onToggle,
  onEdit,
  onDelete,
  onLook,
}: {
  card: HakoniwaRuleCard;
  nameOf: (id: string) => string;
  disabled: boolean;
  lookDisabled: boolean;
  onToggle: (active: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
  onLook: (status: HakoniwaLookStatus) => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  // 見た目のタグも体の性別も無い自作の掟は、見た目を変えない
  const changesLook = Boolean(card.appearance_tags?.trim() || card.body_gender);
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
      {card.synergies && card.synergies.length > 0 && (
        <ul className="hakoniwa-rule__synergies">
          {card.synergies.map((synergy) => (
            <li
              key={synergy.with_id}
              className={synergy.active ? "is-active" : undefined}
            >
              <span className="hakoniwa-rule__synergy-text">
                {t("hakoniwa.rules.synergy", {
                  name: nameOf(synergy.with_id),
                  label: synergy.label,
                  hint: synergy.hint,
                })}
              </span>
              {synergy.active && (
                <span className="hakoniwa-badge hakoniwa-badge--accent">
                  {t("hakoniwa.rules.synergyActive")}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {card.custom && card.look && !changesLook && (
        <div className="hakoniwa-rule__appearance">
          <span className="hakoniwa-rule__appearance-text">
            {t("hakoniwa.rules.appearanceNone")}
          </span>
        </div>
      )}
      {card.custom && card.look && changesLook && (
        <div className="hakoniwa-rule__appearance">
          {card.appearance_text && (
            <span className="hakoniwa-rule__appearance-text">
              {t("hakoniwa.rules.appearanceShown", {
                text: card.appearance_text,
              })}
            </span>
          )}
          {card.body_gender && (
            <span className="hakoniwa-rule__appearance-text">
              {t("hakoniwa.rules.bodyShown", {
                gender: t(`hakoniwa.gender.${card.body_gender}`),
              })}
            </span>
          )}
          {card.appearance_tags && (
            <code className="hakoniwa-rule__appearance-tags">
              {card.appearance_tags}
            </code>
          )}
          <LookControls
            status={card.look}
            target={card.id}
            disabled={lookDisabled}
            onRequest={() => card.look && onLook(card.look)}
          />
        </div>
      )}
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
  const { saveCustomRule, makeRuleLookTags, busy } = useHakoniwa();
  const nameId = useId();
  const textId = useId();
  const bodyId = useId();
  const [name, setName] = useState(rule?.name ?? "");
  const [text, setText] = useState(rule?.description ?? "");
  const [appearance, setAppearance] = useState(rule?.appearance_text ?? "");
  const [lookTags, setLookTags] = useState(rule?.appearance_tags ?? "");
  const [body, setBody] = useState<BodyOption>(rule?.body_gender ?? "keep");
  const [makingTags, setMakingTags] = useState(false);

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
      confirmDisabled={!name.trim() || !text.trim() || makingTags}
      busy={busy === "rule"}
      onCancel={onClose}
      onConfirm={() => {
        void saveCustomRule(
          {
            name: name.trim(),
            text: text.trim(),
            appearance_text: appearance.trim(),
            appearance_tags: lookTags.trim(),
            body_gender: body === "keep" ? null : body,
          },
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
        <HakoniwaLookFields
          descriptionLabel={t("hakoniwa.rules.appearance")}
          description={appearance}
          onDescriptionChange={setAppearance}
          descriptionPlaceholder={t("hakoniwa.rules.appearancePlaceholder")}
          descriptionMax={APPEARANCE_MAX}
          note={t("hakoniwa.rules.appearanceNote")}
          tagsLabel={t("hakoniwa.rules.appearanceTags")}
          tags={lookTags}
          onTagsChange={setLookTags}
          tagsPlaceholder={t("hakoniwa.rules.appearanceTagsPlaceholder")}
          canMake={Boolean(text.trim() || appearance.trim())}
          onMake={() =>
            makeRuleLookTags({
              name: name.trim(),
              text: text.trim(),
              appearance_text: appearance.trim(),
            })
          }
          onMakingChange={setMakingTags}
        />
        <div className="hakoniwa-field">
          <span id={bodyId}>{t("hakoniwa.rules.body")}</span>
          <div
            className="hakoniwa-segments"
            role="group"
            aria-labelledby={bodyId}
          >
            {BODY_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={body === option ? "is-active" : undefined}
                aria-pressed={body === option}
                onClick={() => setBody(option)}
              >
                {t(`hakoniwa.rules.bodyOption.${option}`)}
              </button>
            ))}
          </div>
        </div>
        <p className="hakoniwa-note">{t("hakoniwa.rules.bodyNote")}</p>
      </div>
    </ConfirmDialog>
  );
}
