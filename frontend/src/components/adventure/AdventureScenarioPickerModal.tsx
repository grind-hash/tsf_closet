import { useTranslation } from "react-i18next";
import type { AdventureRun, AdventureTemplate } from "../../apis/adventure";

export type AdventureScenarioPickerTab = "authored" | "played";

interface Props {
  isOpen: boolean;
  tab: AdventureScenarioPickerTab;
  onTabChange: (tab: AdventureScenarioPickerTab) => void;
  templates: AdventureTemplate[];
  runs: AdventureRun[];
  selectedTemplateId: string;
  selectedReplayRunId: string;
  onSelectTemplate: (templateId: string) => void;
  onSelectRun: (runId: string) => void;
  onClose: () => void;
}

/** 作品シナリオ／プレイ済みシナリオを選ぶモーダル（Hub のセットアップ画面から開く） */
export default function AdventureScenarioPickerModal({
  isOpen,
  tab,
  onTabChange,
  templates,
  runs,
  selectedTemplateId,
  selectedReplayRunId,
  onSelectTemplate,
  onSelectRun,
  onClose,
}: Props) {
  const { t } = useTranslation();
  if (!isOpen) return null;
  return (
    <div
      className="adventure-scenario-modal"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className="adventure-scenario-modal__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="adventure-scenario-modal-title"
      >
        <header>
          <h2 id="adventure-scenario-modal-title">
            {t("adventure.selectScenario")}
          </h2>
          <button
            type="button"
            className="adventure-scenario-modal__close"
            aria-label={t("adventure.closeScenarioPicker")}
            onClick={() => onClose()}
          >
            ×
          </button>
        </header>
        <div className="adventure-scenario-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "played"}
            className={tab === "played" ? "is-active" : ""}
            onClick={() => onTabChange("played")}
          >
            {t("adventure.scenarioTabs.played")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "authored"}
            className={tab === "authored" ? "is-active" : ""}
            onClick={() => onTabChange("authored")}
          >
            {t("adventure.scenarioTabs.authored")}
          </button>
        </div>
        <div className="adventure-scenario-modal__list">
          {tab === "authored" ? (
            templates.length === 0 ? (
              <p className="adventure-empty">{t("adventure.noTemplates")}</p>
            ) : (
              templates.map((template) => (
                <button
                  type="button"
                  key={template.id}
                  className={
                    selectedTemplateId === template.id && !selectedReplayRunId
                      ? "is-selected"
                      : ""
                  }
                  onClick={() => onSelectTemplate(template.id)}
                >
                  <span className="adventure-template-item__title">
                    <strong>{template.title}</strong>
                    {template.content_rating === "mature" && (
                      <small>{t("adventure.matureScenario")}</small>
                    )}
                  </span>
                  <span>{template.synopsis}</span>
                  <span className="adventure-scenario-option__meta">
                    {t("adventure.templateMeta", {
                      turns: template.max_turns,
                      preset: t(`adventure.presets.${template.preset}`),
                    })}
                  </span>
                  <span className="adventure-scenario-option__detail">
                    <b>{t("adventure.goal")}</b>
                    <span>{template.objective}</span>
                  </span>
                  <span className="adventure-scenario-option__detail">
                    <b>{t("adventure.constraints")}</b>
                    <span>{template.constraints.join(" / ")}</span>
                  </span>
                </button>
              ))
            )
          ) : runs.length === 0 ? (
            <p className="adventure-empty">
              {t("adventure.noPlayedScenarios")}
            </p>
          ) : (
            runs.map((run) => (
              <button
                type="button"
                key={run.id}
                className={selectedReplayRunId === run.id ? "is-selected" : ""}
                onClick={() => onSelectRun(run.id)}
              >
                <span className="adventure-template-item__title">
                  <strong>{run.title}</strong>
                  <small>{t(`adventure.status.${run.status}`)}</small>
                </span>
                <span>{run.objective}</span>
                <span className="adventure-scenario-option__meta">
                  {t("adventure.playedScenarioMeta", {
                    turns: run.turn_count,
                    maxTurns: run.max_turns,
                  })}
                </span>
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
