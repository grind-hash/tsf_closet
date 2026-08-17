import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AdventureSpeechStyle, canActOnRun } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventureSpeechStyleModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// backend/gateway/consts/adventure_speech.py と揃える
const SPEECH_STYLES: AdventureSpeechStyle[] = [
  "polite",
  "casual",
  "formal",
  "custom",
];
const SPEECH_CUSTOM_MAX_LENGTH = 120;
const PARTNER_SPEECH_STYLE_MAX_LENGTH = 200;

/**
 * プレイ中の口調変更モーダル。
 *
 * 口調はプロンプト注入だけの設定なので、現実改変ルールの管理と同じく手番を
 * 消費せず PATCH で保存し、次の手番から反映される。画像設定は必須項目なので
 * run の現在値をそのまま添えて送り、意図せず切り替わらないようにする。
 */
export default function AdventureSpeechStyleModal({
  isOpen,
  onClose,
}: AdventureSpeechStyleModalProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, updateSettings } = useAdventure();
  const [style, setStyle] = useState<AdventureSpeechStyle>("polite");
  const [custom, setCustom] = useState("");
  const [partner, setPartner] = useState("");
  const [saving, setSaving] = useState(false);

  // 開くたびに run の現在値へ戻す。未保存の編集状態を持ち越さない
  useEffect(() => {
    if (!isOpen || !activeRun) return;
    setStyle(activeRun.player_speech_style ?? "polite");
    setCustom(activeRun.player_speech_custom ?? "");
    setPartner(activeRun.sim?.partner_speech_style ?? "");
    setSaving(false);
  }, [isOpen, activeRun]);

  if (!isOpen || !activeRun) return null;

  const romance = activeRun.preset === "romance";
  const title = t("adventure.speechStyleManager.title");
  const actionable = !streaming && !saving && canActOnRun(activeRun);

  const handleSave = async () => {
    if (!actionable) return;
    setSaving(true);
    try {
      await updateSettings({
        // 画像設定は必須項目。現在値を添えて意図しない変更を防ぐ
        use_precise_reference: activeRun.use_precise_reference,
        enable_composite_scene: activeRun.enable_composite_scene,
        player_speech_style: style,
        player_speech_custom: custom.trim(),
        partner_speech_style: romance ? partner.trim() : undefined,
      });
      onClose();
    } catch {
      // エラーは AdventureContext が保持し、画面上部に表示される
    } finally {
      setSaving(false);
    }
  };

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
        aria-label={t("adventure.speechStyleManager.close")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel">
        <h2>{title}</h2>
        <p className="adventure-prompt-modal__hint">
          {t("adventure.speechStyleManager.hint")}
        </p>

        <fieldset className="adventure-speech-style">
          <legend>{t("adventure.speechStyle")}</legend>
          <div className="adventure-speech-style__cards">
            {SPEECH_STYLES.map((value) => (
              <button
                type="button"
                key={value}
                disabled={!actionable}
                className={style === value ? "is-active" : ""}
                aria-pressed={style === value}
                onClick={() => setStyle(value)}
              >
                <strong>{t(`adventure.speechStyles.${value}`)}</strong>
                <small>{t(`adventure.speechStyleExamples.${value}`)}</small>
              </button>
            ))}
          </div>
        </fieldset>
        {style === "custom" && (
          <label className="adventure-speech-style__custom">
            <span>{t("adventure.speechStyleCustom")}</span>
            <input
              type="text"
              maxLength={SPEECH_CUSTOM_MAX_LENGTH}
              value={custom}
              disabled={!actionable}
              placeholder={t("adventure.speechStyleCustomPlaceholder")}
              onChange={(event) => setCustom(event.target.value)}
            />
          </label>
        )}
        {romance && (
          <label className="adventure-speech-style__partner">
            <span>{t("adventure.romance.partnerSpeechStyle")}</span>
            <input
              type="text"
              maxLength={PARTNER_SPEECH_STYLE_MAX_LENGTH}
              value={partner}
              disabled={!actionable}
              placeholder={t("adventure.romance.partnerSpeechStylePlaceholder")}
              onChange={(event) => setPartner(event.target.value)}
            />
            <small>{t("adventure.romance.partnerSpeechStyleHint")}</small>
          </label>
        )}

        <div className="adventure-prompt-modal__actions">
          <button type="button" onClick={onClose}>
            {t("adventure.speechStyleManager.close")}
          </button>
          <button
            type="button"
            className="is-primary"
            disabled={!actionable}
            onClick={() => void handleSave()}
          >
            {t("adventure.speechStyleManager.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
