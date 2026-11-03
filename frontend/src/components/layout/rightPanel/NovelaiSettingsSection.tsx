import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSettings } from "../../../contexts/SettingsContext";
import {
  NovelaiImageModelFields,
  NovelaiPromptFields,
  NovelaiTextModelField,
} from "./NovelaiGenerationFields";
import PreciseReferencesPanel from "./PreciseReferencesPanel";
import PromptBuilderPanel from "./PromptBuilderPanel";

interface NovelaiSettingsSectionProps {
  onOpenInpaintModal?: () => void;
}

/** 実験的機能のチップ(バージョン付き) */
function ExperimentalChip({ version }: { version: string }) {
  return (
    <div style={{ marginTop: "0.25rem" }}>
      <span
        className="feature-chip-experimental"
        data-feature-version={version}
      >
        Experimental
      </span>
    </div>
  );
}

/** トグルスイッチ + 実験チップ + 説明の 1 グループ */
function ToggleGroup({
  label,
  checked,
  onChange,
  version,
  hint,
  children,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  version: string;
  hint: string;
  children?: ReactNode;
}) {
  return (
    <div className="right-panel__form-group">
      <label className="right-panel__toggle">
        <span className="right-panel__toggle-label">{label}</span>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="right-panel__toggle-input"
        />
        <span className="right-panel__toggle-switch" />
      </label>
      <ExperimentalChip version={version} />
      <small className="right-panel__hint">{hint}</small>
      {children}
    </div>
  );
}

/**
 * NovelAI 画像設定(NovelAI 選択時のみ)。直接/ネガティブプロンプト、i2i 強度、
 * ノイズ、Seed、周囲画像・服の色・複数人のトグル、モデル選択、プロンプトビルダー、
 * マスク設定、精密参照画像。
 */
export default function NovelaiSettingsSection({
  onOpenInpaintModal,
}: NovelaiSettingsSectionProps) {
  const { t } = useTranslation();
  const {
    state: settingsState,
    setSeed,
    setEnableSurroundingsImage,
    setSurroundingsIncludePeople,
    setClothingColorConsistency,
    setEnableMultiplePeople,
  } = useSettings();

  return (
    <section className="right-panel__section">
      <h4 className="right-panel__section-title">
        {t("rightPanel.novelaiImageSettings")}
      </h4>

      <NovelaiPromptFields />

      {/* US4: Seed input */}
      <div className="right-panel__form-group">
        <label className="right-panel__label">
          {t("rightPanel.seedLabel", "Seed")}
        </label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="number"
            className="right-panel__input"
            min={0}
            max={999999999}
            step={1}
            value={settingsState.seed ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") {
                setSeed(null);
                return;
              }
              const num = parseInt(raw, 10);
              if (!Number.isNaN(num) && num >= 0 && num <= 999999999) {
                setSeed(num);
              }
            }}
            placeholder={t("rightPanel.seedPlaceholder", "Random")}
            style={{ flex: 1, minWidth: 0 }}
          />
          {settingsState.seed !== null && (
            <button
              type="button"
              className="right-panel__btn-secondary"
              onClick={() => setSeed(null)}
              style={{ flexShrink: 0, padding: "0.25rem 0.5rem" }}
              title={t("rightPanel.seedClear", "Clear seed")}
            >
              ✕
            </button>
          )}
        </div>
        <small className="right-panel__hint">
          {t(
            "rightPanel.seedHint",
            "Empty = random. Set a value to reproduce the same image.",
          )}
        </small>
      </div>

      {/* US3: 周囲状況画像生成トグル */}
      <ToggleGroup
        label={t(
          "rightPanel.enableSurroundingsImage",
          "Generate surroundings image",
        )}
        checked={settingsState.enableSurroundingsImage}
        onChange={setEnableSurroundingsImage}
        version="v0.3.0"
        hint={t(
          "rightPanel.enableSurroundingsImageHint",
          "Generate an additional image showing the surrounding environment after action instructions. Uses extra Anlas on non-Opus plans.",
        )}
      />

      {/* Surroundings: include reactive bystanders */}
      {settingsState.enableSurroundingsImage && (
        <ToggleGroup
          label={t(
            "rightPanel.surroundingsIncludePeople",
            "Include bystanders in surroundings",
          )}
          checked={settingsState.surroundingsIncludePeople}
          onChange={setSurroundingsIncludePeople}
          version="v0.3.0"
          hint={t(
            "rightPanel.surroundingsIncludePeopleHint",
            "Include 2-3 reactive bystanders in the surroundings image.",
          )}
        />
      )}

      {/* Clothing color consistency toggle */}
      <ToggleGroup
        label={t(
          "rightPanel.clothingColorConsistency",
          "Clothing Color Consistency",
        )}
        checked={settingsState.clothingColorConsistency}
        onChange={setClothingColorConsistency}
        version="v0.3.0"
        hint={t(
          "rightPanel.clothingColorConsistencyHint",
          "When enabled, adds rules to prompt generation to maintain clothing color consistency.",
        )}
      >
        {settingsState.clothingColorConsistency && (
          <small
            className="right-panel__hint"
            style={{
              marginTop: "0.25rem",
              color: "var(--text-warning, #e0a050)",
            }}
          >
            {t("rightPanel.clothingColorConsistencyTradeoff")}
          </small>
        )}
      </ToggleGroup>

      {/* Multiple people toggle */}
      <ToggleGroup
        label={t(
          "rightPanel.enableMultiplePeople",
          "Multiple People (Experimental)",
        )}
        checked={settingsState.enableMultiplePeople}
        onChange={setEnableMultiplePeople}
        version="v0.3.0"
        hint={t(
          "rightPanel.enableMultiplePeopleHint",
          "Allow multiple characters in generated images. When enabled, the LLM determines the number of characters based on your instructions.",
        )}
      />

      {/* NovelAI Text Model Selector (Opus only) */}
      <NovelaiTextModelField />

      {/* NovelAI Image Model Selectors */}
      <NovelaiImageModelFields />

      {/* Prompt Builder */}
      {settingsState.clothingColorConsistency && <PromptBuilderPanel />}

      {/* T024-T025: マスク設定ボタン */}
      {onOpenInpaintModal && (
        <div className="right-panel__form-group" style={{ marginTop: "1rem" }}>
          <button
            type="button"
            className="right-panel__btn-secondary"
            onClick={onOpenInpaintModal}
            style={{ width: "100%" }}
          >
            {t("rightPanel.maskSettings")}
          </button>
          <small className="right-panel__hint">
            {t("rightPanel.maskSettingsHint")}
          </small>
        </div>
      )}

      {/* Precise Reference Images Section */}
      <PreciseReferencesPanel />
    </section>
  );
}
