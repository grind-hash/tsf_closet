import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { canActOnRun } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureAttributeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// サーバ側 _MAX_REALITY_RULE_LENGTH と揃える（超過分は黙って切り詰められるため）
const ATTRIBUTE_MAX_LENGTH = 300;
// サーバ側 _MAX_REALITY_RULES と揃える
const ATTRIBUTE_MAX_COUNT = 12;

// サーバ側 _normalize_reality_rule と同じ正規化。重複判定を一致させる
function normalizeRule(value: string): string {
  return value.trim().replace(/\s+/g, " ").slice(0, ATTRIBUTE_MAX_LENGTH);
}

/**
 * 現実改変ルール（romance では「属性」）の管理モーダル。
 *
 * 一覧の追加・編集・削除は手番を消費せず PATCH で即時保存する（通常ゲームの
 * 属性付与と同じ操作感）。「付与して行動」だけが従来どおり1手番を使い、
 * 「現実改変：〜」の宣言として物語に演じさせる。
 */
export default function AdventureAttributeModal({
  isOpen,
  onClose,
}: AdventureAttributeModalProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, submitTurn, updateRealityRules } =
    useAdventure();
  const [text, setText] = useState("");
  // 編集対象は添字ではなく元の文字列で持つ。ターン追記やFIFO削除で
  // 一覧がずれても、別のルールを上書きしてしまわないようにする
  const [editingRule, setEditingRule] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setText("");
    setEditingRule(null);
    setSaving(false);
    setLocalError(null);
  }, [isOpen]);

  if (!isOpen) return null;

  // 一覧はローカルへ複製せず activeRun から導出する（保存後の再取得と、
  // ターン追記による更新の両方へそのまま追従させるため）
  const rules = activeRun?.reality_rules ?? [];
  const romance = activeRun?.preset === "romance";
  const title = t(
    romance
      ? "adventure.romance.attribute.title"
      : "adventure.realityRuleManager.title",
  );
  const inputLabel = editingRule
    ? t("adventure.realityRuleManager.editLabel")
    : t(
        romance
          ? "adventure.romance.attribute.label"
          : "adventure.realityRuleManager.label",
      );

  const normalized = normalizeRule(text);
  const actionable = !streaming && !saving && canActOnRun(activeRun);
  const isDuplicate =
    normalized.length > 0 &&
    normalized !== editingRule &&
    rules.includes(normalized);
  const isFull = rules.length >= ATTRIBUTE_MAX_COUNT;
  const canGrant =
    actionable && normalized.length > 0 && !isDuplicate && !isFull;
  const canSaveEdit =
    actionable &&
    normalized.length > 0 &&
    !isDuplicate &&
    normalized !== editingRule;

  const save = async (next: string[]): Promise<boolean> => {
    setSaving(true);
    setLocalError(null);
    try {
      await updateRealityRules(next);
      return true;
    } catch (caught) {
      setLocalError(caught instanceof Error ? caught.message : String(caught));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (rule: string) => {
    if (!actionable) return;
    const ok = await save(rules.filter((item) => item !== rule));
    if (ok && editingRule === rule) {
      setEditingRule(null);
      setText("");
    }
  };

  const handleEdit = (rule: string) => {
    setEditingRule(rule);
    setText(rule);
    setLocalError(null);
    textareaRef.current?.focus();
  };

  const handleCancelEdit = () => {
    setEditingRule(null);
    setText("");
    setLocalError(null);
  };

  const handleSaveEdit = async () => {
    if (!canSaveEdit || editingRule === null) return;
    // 編集中に一覧から消えていた場合は、意図どおり存在させるため末尾へ足す
    const next = rules.includes(editingRule)
      ? rules.map((item) => (item === editingRule ? normalized : item))
      : [...rules, normalized];
    if (await save(next)) {
      setEditingRule(null);
      setText("");
    }
  };

  const handleGrant = async () => {
    if (!canGrant) return;
    // 保存の完了を待ってから入力を消す。閉じないのは、一覧に増えたことが
    // 確認になり、続けて複数付与できるため
    if (await save([...rules, normalized])) setText("");
  };

  const handleGrantAndAct = () => {
    if (!canGrant) return;
    onClose();
    // サーバは本文の宣言記法から検出するため、種別は昇格後と同じ値を送る
    void submitTurn(`現実改変：${normalized}`, "reality_alter");
  };

  const hint = isDuplicate
    ? t("adventure.realityRuleManager.duplicate")
    : isFull
      ? t("adventure.realityRuleManager.limitReached", {
          max: ATTRIBUTE_MAX_COUNT,
        })
      : null;

  return (
    <div
      className="adventure-prompt-modal"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        className="adventure-prompt-modal__backdrop"
        aria-label={t("adventure.realityRuleManager.close")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel">
        <h2>{title}</h2>
        <p className="adventure-prompt-modal__hint">
          {t(
            romance
              ? "adventure.romance.attribute.hint"
              : "adventure.realityRuleManager.hint",
          )}
        </p>

        <span id="adventure-attribute-list-label">
          {t("adventure.realityRuleManager.listLabel", {
            count: rules.length,
            max: ATTRIBUTE_MAX_COUNT,
          })}
        </span>
        {rules.length === 0 ? (
          <p className="adventure-attribute-list__empty">
            {t("adventure.realityRuleManager.listEmpty")}
          </p>
        ) : (
          <ul
            className="adventure-attribute-list"
            aria-labelledby="adventure-attribute-list-label"
          >
            {/* サーバ側で重複排除済みのため、本文をそのままキーにできる */}
            {rules.map((rule) => (
              <li
                key={rule}
                className={editingRule === rule ? "is-editing" : undefined}
              >
                <span className="adventure-attribute-list__text">{rule}</span>
                <button
                  type="button"
                  className="adventure-attribute-list__action"
                  disabled={!actionable || editingRule === rule}
                  aria-label={t("adventure.realityRuleManager.editAria", {
                    text: rule,
                  })}
                  title={t("common.edit")}
                  onClick={() => handleEdit(rule)}
                >
                  ✎
                </button>
                <button
                  type="button"
                  className="adventure-attribute-list__action"
                  disabled={!actionable}
                  aria-label={t("adventure.realityRuleManager.deleteAria", {
                    text: rule,
                  })}
                  title={t("common.delete")}
                  onClick={() => void handleDelete(rule)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="adventure-prompt-modal__hint">
          {t("adventure.realityRuleManager.removeNote")}
        </p>

        <label htmlFor="adventure-attribute-text">{inputLabel}</label>
        <textarea
          id="adventure-attribute-text"
          ref={textareaRef}
          rows={3}
          maxLength={ATTRIBUTE_MAX_LENGTH}
          value={text}
          disabled={!actionable}
          onChange={(event) => setText(event.target.value)}
          placeholder={t(
            romance
              ? "adventure.romance.attribute.placeholder"
              : "adventure.realityRuleManager.placeholder",
          )}
        />
        {(localError || hint) && (
          <p className="adventure-prompt-modal__error">{localError ?? hint}</p>
        )}

        <div className="adventure-prompt-modal__actions">
          {editingRule !== null ? (
            <>
              <button
                type="button"
                disabled={saving}
                onClick={handleCancelEdit}
              >
                {t("adventure.realityRuleManager.cancelEdit")}
              </button>
              <button
                type="button"
                className="is-primary"
                disabled={!canSaveEdit}
                onClick={() => void handleSaveEdit()}
              >
                {t("adventure.realityRuleManager.saveEdit")}
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={onClose}>
                {t("adventure.realityRuleManager.close")}
              </button>
              <button
                type="button"
                className="is-primary"
                disabled={!canGrant}
                title={t("adventure.realityRuleManager.grantHint")}
                onClick={() => void handleGrant()}
              >
                {t("adventure.realityRuleManager.grant")}
              </button>
              <button
                type="button"
                disabled={!canGrant}
                title={t("adventure.realityRuleManager.grantAndActHint")}
                onClick={handleGrantAndAct}
              >
                {t("adventure.realityRuleManager.grantAndAct")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
