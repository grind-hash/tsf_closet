import { useTranslation } from "react-i18next";
import { useChat } from "../../../contexts/ChatContext";
import {
  composePromptBuilderText,
  type PromptBuilderFields,
  usePromptBuilder,
} from "../../../hooks/usePromptBuilder";

// i18n キーはリテラル型のまま持ち、typed t() に渡す
const FIELD_KEYS = [
  {
    key: "who",
    label: "rightPanel.promptBuilderWho",
    placeholder: "rightPanel.promptBuilderWhoPlaceholder",
  },
  {
    key: "location",
    label: "rightPanel.promptBuilderLocation",
    placeholder: "rightPanel.promptBuilderLocationPlaceholder",
  },
  {
    key: "outfit",
    label: "rightPanel.promptBuilderOutfit",
    placeholder: "rightPanel.promptBuilderOutfitPlaceholder",
  },
  {
    key: "target",
    label: "rightPanel.promptBuilderTarget",
    placeholder: "rightPanel.promptBuilderTargetPlaceholder",
  },
  {
    key: "action",
    label: "rightPanel.promptBuilderAction",
    placeholder: "rightPanel.promptBuilderActionPlaceholder",
  },
] as const satisfies ReadonlyArray<{
  key: keyof PromptBuilderFields;
  label: string;
  placeholder: string;
}>;

/**
 * プロンプトビルダー(服の色の一貫性 ON のとき)。「誰が・どの衣装で・どこで・
 * 何を・どうする」の項目、または自由入力から指示文を組み立てて入力欄へ入れる。
 */
export default function PromptBuilderPanel() {
  const { t } = useTranslation();
  const { setInputText } = useChat();
  const builder = usePromptBuilder();

  const apply = () => {
    if (builder.mode === "textarea") {
      const text =
        builder.freeform.trim() ||
        t("rightPanel.promptBuilderFreeformPlaceholder");
      setInputText(text);
      return;
    }
    const composed = composePromptBuilderText(builder.fields);
    if (composed) {
      setInputText(composed);
      return;
    }
    // 全項目が空ならプレースホルダを並べた雛形を入れる
    setInputText(
      `${t("rightPanel.promptBuilderWhoPlaceholder")}、${t("rightPanel.promptBuilderOutfitPlaceholder")}で、${t("rightPanel.promptBuilderLocationPlaceholder")}にて、${t("rightPanel.promptBuilderTargetPlaceholder")}を、${t("rightPanel.promptBuilderActionPlaceholder")}`,
    );
  };

  return (
    <div className="right-panel__form-group">
      <h4 className="right-panel__section-title">
        {t("rightPanel.sectionPromptBuilder")}
      </h4>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: "0.3rem",
        }}
      >
        <button
          type="button"
          className="right-panel__btn-secondary"
          style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }}
          onClick={builder.toggleMode}
        >
          {builder.mode === "fields"
            ? t("rightPanel.promptBuilderSwitchToTextarea")
            : t("rightPanel.promptBuilderSwitchToFields")}
        </button>
      </div>
      {builder.mode === "fields" ? (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}
        >
          {FIELD_KEYS.map((field) => (
            <label key={field.key} className="right-panel__mini-label">
              {t(field.label)}
              <input
                type="text"
                className="right-panel__input"
                value={builder.fields[field.key]}
                onChange={(e) => builder.setField(field.key, e.target.value)}
                placeholder={t(field.placeholder)}
              />
            </label>
          ))}
        </div>
      ) : (
        <div>
          <textarea
            className="right-panel__textarea"
            rows={4}
            value={builder.freeform}
            onChange={(e) => builder.setFreeform(e.target.value)}
            placeholder={t("rightPanel.promptBuilderFreeformPlaceholder")}
          />
        </div>
      )}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
        <button
          type="button"
          className="right-panel__btn-primary"
          onClick={apply}
        >
          {t("rightPanel.promptBuilderApply")}
        </button>
        <button
          type="button"
          className="right-panel__btn-secondary"
          onClick={builder.reset}
        >
          {t("rightPanel.promptBuilderReset")}
        </button>
      </div>
    </div>
  );
}
