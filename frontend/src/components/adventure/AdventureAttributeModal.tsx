import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureAttributeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// サーバ側 _MAX_REALITY_RULE_LENGTH と揃える（超過分は黙って切り詰められるため）
const ATTRIBUTE_MAX_LENGTH = 300;

/**
 * romance 専用の属性付与モーダル。入力を「現実改変：〜」へ組み立てて送る
 * 入力補助であり、自由入力欄への手打ち宣言と完全に同一の経路をたどる。
 */
export default function AdventureAttributeModal({
  isOpen,
  onClose,
}: AdventureAttributeModalProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, submitTurn } = useAdventure();
  const [text, setText] = useState("");

  useEffect(() => {
    if (isOpen) setText("");
  }, [isOpen]);

  if (!isOpen) return null;

  const canSubmit =
    text.trim().length > 0 && !streaming && activeRun?.status === "active";

  const handleSubmit = () => {
    if (!canSubmit) return;
    const declaration = `現実改変：${text.trim()}`;
    onClose();
    // サーバは本文の宣言記法から検出するため、種別は昇格後と同じ値を送る
    void submitTurn(declaration, "reality_alter");
  };

  return (
    <div
      className="adventure-prompt-modal"
      role="dialog"
      aria-modal="true"
      aria-label={t("adventure.romance.attribute.title")}
    >
      <button
        type="button"
        className="adventure-prompt-modal__backdrop"
        aria-label={t("adventure.romance.attribute.cancel")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel">
        <h2>{t("adventure.romance.attribute.title")}</h2>
        <p className="adventure-prompt-modal__hint">
          {t("adventure.romance.attribute.hint")}
        </p>

        <label htmlFor="adventure-attribute-text">
          {t("adventure.romance.attribute.label")}
        </label>
        <textarea
          id="adventure-attribute-text"
          rows={3}
          maxLength={ATTRIBUTE_MAX_LENGTH}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={t("adventure.romance.attribute.placeholder")}
        />

        <div className="adventure-prompt-modal__actions">
          <button type="button" onClick={onClose}>
            {t("adventure.romance.attribute.cancel")}
          </button>
          <button
            type="button"
            className="is-primary"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {t("adventure.romance.attribute.submit")}
          </button>
        </div>
      </div>
    </div>
  );
}
