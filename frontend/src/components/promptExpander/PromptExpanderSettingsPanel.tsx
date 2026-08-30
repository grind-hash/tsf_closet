/**
 * PromptExpanderSettingsPanel - Prompt Expander の設定パネル（MainLayout の右サイドパネル）
 *
 * テキストモデル、「欄へ復元」で seed も戻すかの切替、
 * PE ローカルメモリ（テキスト + 使う/使わない + グローバルメモリの取り込み）を扱う。
 * 画像モデル / サイズ / seed / i2i 強度・ノイズ / 参照元プロンプトの引き継ぎは
 * 同じ設定だがコンポーザ側に置き、重複させない。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PROMPT_EXPANDER_MEMORY_MAX_LENGTH } from "../../constants/promptExpander";
import { useNotification } from "../../contexts/NotificationContext";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import PromptExpanderSwitch from "./PromptExpanderSwitch";
import "./PromptExpanderShared.css";
import "./PromptExpanderSettingsPanel.css";

export const PROMPT_EXPANDER_SETTINGS_PANEL_ID =
  "prompt-expander-settings-panel";

interface PromptExpanderSettingsPanelProps {
  onClose: () => void;
}

export default function PromptExpanderSettingsPanel({
  onClose,
}: PromptExpanderSettingsPanelProps) {
  const { t } = useTranslation();
  const { showNotification } = useNotification();
  const {
    settings,
    options,
    updateSettings,
    updateSettingsDebounced,
    importGlobalMemory,
  } = usePromptExpander();
  const [memoryDraft, setMemoryDraft] = useState(settings.memory_text);
  const [importing, setImporting] = useState(false);

  // サーバ側で更新された値（取り込み等）を編集欄へ反映する
  useEffect(() => {
    setMemoryDraft(settings.memory_text);
  }, [settings.memory_text]);

  const handleMemoryChange = (value: string) => {
    const next = value.slice(0, PROMPT_EXPANDER_MEMORY_MAX_LENGTH);
    setMemoryDraft(next);
    updateSettingsDebounced({ memory_text: next });
  };

  const handleImport = async () => {
    if (
      settings.memory_text.trim() &&
      !window.confirm(t("promptExpander.settings.importConfirm"))
    ) {
      return;
    }
    setImporting(true);
    const imported = await importGlobalMemory();
    setImporting(false);
    if (imported) {
      showNotification(
        "success",
        t("promptExpander.header.title"),
        t("promptExpander.settings.importDone"),
      );
    } else {
      showNotification(
        "warning",
        t("promptExpander.header.title"),
        t("promptExpander.settings.importEmpty"),
      );
    }
  };

  return (
    <section
      id={PROMPT_EXPANDER_SETTINGS_PANEL_ID}
      className="prompt-expander__settings"
      aria-label={t("promptExpander.settings.title")}
    >
      <div className="prompt-expander__settings-head">
        <h2 className="prompt-expander__settings-title">
          {t("promptExpander.settings.title")}
        </h2>
        <button
          type="button"
          className="prompt-expander__settings-close"
          onClick={onClose}
          aria-label={t("promptExpander.header.settingsClose")}
          title={t("promptExpander.header.settingsClose")}
        >
          ✕
        </button>
      </div>

      <div className="prompt-expander__settings-body">
        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-text-model"
          >
            {t("promptExpander.settings.textModel")}
          </label>
          <select
            id="prompt-expander-text-model"
            className="prompt-expander__select"
            value={settings.text_model}
            onChange={(e) =>
              void updateSettings({ text_model: e.target.value })
            }
          >
            {options.textModelOptions.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
          <span className="prompt-expander__hint">
            {t("promptExpander.settings.textModelHint")}
          </span>
        </div>

        <div className="prompt-expander__field">
          <PromptExpanderSwitch
            checked={settings.restore_seed}
            onChange={(checked) =>
              void updateSettings({ restore_seed: checked })
            }
            label={t("promptExpander.settings.restoreSeed")}
          />
          <span className="prompt-expander__hint">
            {t("promptExpander.settings.restoreSeedDesc")}
          </span>
        </div>

        <div className="prompt-expander__field">
          <label
            className="prompt-expander__label"
            htmlFor="prompt-expander-memory"
          >
            {t("promptExpander.settings.memory")}
          </label>
          <PromptExpanderSwitch
            checked={settings.use_memory}
            onChange={(checked) => void updateSettings({ use_memory: checked })}
            label={t("promptExpander.settings.useMemory")}
          />
          <span className="prompt-expander__hint">
            {t("promptExpander.settings.useMemoryDesc")}
          </span>
          <textarea
            id="prompt-expander-memory"
            className="prompt-expander__textarea prompt-expander__settings-memory"
            rows={10}
            value={memoryDraft}
            maxLength={PROMPT_EXPANDER_MEMORY_MAX_LENGTH}
            onChange={(e) => handleMemoryChange(e.target.value)}
            placeholder={t("promptExpander.settings.memoryPlaceholder")}
          />
          <div className="prompt-expander__settings-memory-foot">
            <span className="prompt-expander__hint">
              {t("promptExpander.settings.memoryCount", {
                count: memoryDraft.length,
                max: PROMPT_EXPANDER_MEMORY_MAX_LENGTH,
              })}
            </span>
            <button
              type="button"
              className="prompt-expander__btn prompt-expander__btn--sm"
              onClick={handleImport}
              disabled={importing}
            >
              {importing
                ? t("promptExpander.settings.importing")
                : t("promptExpander.settings.importMemory")}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
