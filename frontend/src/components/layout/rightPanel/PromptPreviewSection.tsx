import { useTranslation } from "react-i18next";
import { usePromptPreview } from "../../../hooks/usePromptPreview";

interface PromptPreviewSectionProps {
  onSendWithPromptOverride?: (override: string) => void;
}

/** プロンプトプレビュー(ENABLE_PROMPT_PREVIEW のときだけ表示) */
export default function PromptPreviewSection({
  onSendWithPromptOverride,
}: PromptPreviewSectionProps) {
  const { t } = useTranslation();
  const preview = usePromptPreview(onSendWithPromptOverride);
  return (
    <section className="right-panel__section">
      <h4 className="right-panel__section-title">
        {t("rightPanel.promptPreview")}
      </h4>

      <button
        type="button"
        className="right-panel__btn-primary"
        onClick={preview.generate}
        disabled={preview.loading || !preview.canGenerate}
        style={{ width: "100%", marginBottom: "0.5rem" }}
      >
        {preview.loading
          ? t("rightPanel.loadingDots")
          : t("rightPanel.generatePreview")}
      </button>

      {preview.error && (
        <p
          className="right-panel__hint"
          style={{ color: "var(--color-error, #e74c3c)" }}
        >
          {preview.error}
        </p>
      )}

      {preview.result && (
        <div className="right-panel__preview-result">
          {/* 画像編集プロンプト(編集可能) */}
          <div className="right-panel__form-group">
            <label className="right-panel__label">
              {t("rightPanel.imageEditPrompt")}
            </label>
            <textarea
              className="right-panel__textarea"
              value={preview.editedPrompt}
              onChange={(e) => preview.setEditedPrompt(e.target.value)}
              rows={5}
              style={{ fontSize: "0.8rem" }}
            />
            <small className="right-panel__hint">
              {t("rightPanel.imageEditPromptHint")}
            </small>
          </div>

          {/* 心境プロンプト (折りたたみ) */}
          <button
            type="button"
            className="right-panel__btn-secondary"
            onClick={preview.toggleDetail}
            style={{
              width: "100%",
              marginBottom: "0.5rem",
              fontSize: "0.8rem",
            }}
          >
            {preview.showDetail
              ? t("rightPanel.hideDetail")
              : t("rightPanel.showDetail")}
          </button>

          {preview.showDetail && (
            <>
              <div className="right-panel__form-group">
                <label className="right-panel__label">
                  {t("rightPanel.feelingSystemPrompt")}
                </label>
                <textarea
                  className="right-panel__textarea"
                  value={preview.result.feeling_system_prompt}
                  readOnly
                  rows={4}
                  style={{ fontSize: "0.75rem", opacity: 0.8 }}
                />
              </div>
              <div className="right-panel__form-group">
                <label className="right-panel__label">
                  {t("rightPanel.feelingUserPrompt")}
                </label>
                <textarea
                  className="right-panel__textarea"
                  value={preview.result.feeling_user_prompt}
                  readOnly
                  rows={4}
                  style={{ fontSize: "0.75rem", opacity: 0.8 }}
                />
              </div>
              {preview.result.novelai_tag_prompt && (
                <div className="right-panel__form-group">
                  <label className="right-panel__label">
                    NovelAI Tag System
                  </label>
                  <textarea
                    className="right-panel__textarea"
                    value={preview.result.novelai_tag_prompt}
                    readOnly
                    rows={3}
                    style={{ fontSize: "0.75rem", opacity: 0.8 }}
                  />
                </div>
              )}
              {preview.result.surroundings_system_prompt && (
                <div className="right-panel__form-group">
                  <label className="right-panel__label">
                    {t("rightPanel.surroundingsSystemPrompt")}
                  </label>
                  <textarea
                    className="right-panel__textarea"
                    value={preview.result.surroundings_system_prompt}
                    readOnly
                    rows={4}
                    style={{ fontSize: "0.75rem", opacity: 0.8 }}
                  />
                </div>
              )}
              {preview.result.surroundings_user_prompt && (
                <div className="right-panel__form-group">
                  <label className="right-panel__label">
                    {t("rightPanel.surroundingsUserPrompt")}
                  </label>
                  <textarea
                    className="right-panel__textarea"
                    value={preview.result.surroundings_user_prompt}
                    readOnly
                    rows={4}
                    style={{ fontSize: "0.75rem", opacity: 0.8 }}
                  />
                </div>
              )}
            </>
          )}

          {/* 送信ボタン */}
          {onSendWithPromptOverride && (
            <button
              type="button"
              className="right-panel__btn-primary"
              onClick={preview.sendWithOverride}
              disabled={!preview.editedPrompt.trim()}
              style={{ width: "100%", marginTop: "0.3rem" }}
            >
              {t("rightPanel.sendWithPrompt")}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
